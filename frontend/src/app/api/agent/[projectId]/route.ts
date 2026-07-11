import { anthropic } from "@ai-sdk/anthropic";
import { createOpenAI, openai } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
  streamText,
  tool,
} from "ai";
import { headers } from "next/headers";
import { z } from "zod";
import { callBackendTool, roomIdSchema } from "@/lib/agent-backend-tool";
import {
  buildModelChainPlan,
  type ModelChainEntry,
  type ModelChainPlanEntry,
  runModelChain,
} from "@/lib/agent-model-chain";
import { auth } from "@/lib/auth";
import {
  DEFAULT_MODEL_ID,
  DEFAULT_OPENROUTER_MODEL_ID,
  FALLBACK_OPENAI_MODEL_ID,
  getModelProvider,
} from "@/lib/models";

// Fluid Compute allows up to 300s on every Vercel plan; a multi-step tool
// sequence (each backend call capped at 45s) must not be killed mid-stream.
export const maxDuration = 300;

function buildSystemPrompt(layoutState: unknown): string {
  return `You are PlanForge's AI layout assistant. You help users refine their residential floor plans through natural language.

COORDINATE SYSTEM
- Origin (0,0) = plot front-left corner
- X: left → right (metres), Y: front (road) → rear (metres)
- All values 3 decimal places (mm precision)
- EWT = 0.23 m (external wall), IWT = 0.115 m (internal wall)
- Room coordinates are to the INNER face of walls

HARD CONSTRAINTS (violations → reject the change and explain)
  bedroom ≥ 9.5 sqm, width ≥ 2.4 m
  kitchen ≥ 4.5 sqm, width ≥ 1.8 m
  toilet ≥ 2.8 sqm, width ≥ 1.2 m
  staircase width ≥ 0.9 m
  no habitable rooms in stilt or basement
  staircase must align across all floors (same x, y, w, d)

CONSTRAINT RESPONSE PATTERN
When a request is impossible, always:
1. State which constraint is violated and by how much
2. Suggest an alternative (resize differently, remove another room, use another floor)
3. Ask if the user wants to try the alternative

CURRENT LAYOUT STATE
${JSON.stringify(layoutState, null, 2)}

BEHAVIOUR
- Be concise and professional. Use metric units.
- After EVERY successful room modification (move, resize, add, remove, swap, undo),
  ALWAYS call refresh_layout immediately — this re-renders the floor plan for the user.
- Always check compliance after making changes using get_compliance_status.
- If a change creates a violation, undo it and explain why, then call refresh_layout.
- Acknowledge what you did after each successful tool call.
- Keep undo available — remind users they can say "undo" after changes.`;
}

function buildTools(projectId: string, userId: string) {
  return {
    get_room_list: tool({
      description: "List all rooms on a floor or all floors",
      inputSchema: z.object({
        floor: z.enum(["gf", "ff", "sf", "basement", "all"]).describe("Which floor to list"),
      }),
      execute: ({ floor }) => callBackendTool(userId, `projects/${projectId}/rooms?floor=${floor}`),
    }),

    get_room_details: tool({
      description: "Get details for a specific room by ID",
      inputSchema: z.object({ room_id: roomIdSchema }),
      execute: ({ room_id }) =>
        callBackendTool(userId, `projects/${projectId}/rooms/${encodeURIComponent(room_id)}`),
    }),

    get_compliance_status: tool({
      description: "Check current compliance status of the layout",
      inputSchema: z.object({}),
      execute: () => callBackendTool(userId, `projects/${projectId}/compliance`),
    }),

    get_available_space: tool({
      description: "Get available (unoccupied) space on a floor",
      inputSchema: z.object({
        floor: z.enum(["gf", "ff", "sf", "basement"]),
      }),
      execute: ({ floor }) =>
        callBackendTool(userId, `projects/${projectId}/available-space?floor=${floor}`),
    }),

    move_room: tool({
      description: "Move a room to new coordinates. Validates no overlap and setback compliance.",
      inputSchema: z.object({
        room_id: roomIdSchema,
        new_x: z.number().describe("New X position in metres"),
        new_y: z.number().describe("New Y position in metres"),
      }),
      execute: ({ room_id, new_x, new_y }) =>
        callBackendTool(userId, `projects/${projectId}/rooms/${encodeURIComponent(room_id)}/move`, {
          method: "POST",
          body: JSON.stringify({ x: new_x, y: new_y }),
        }),
    }),

    resize_room: tool({
      description: "Resize a room. Validates area minimums and no overlaps.",
      inputSchema: z.object({
        room_id: roomIdSchema,
        new_width: z.number().optional().describe("New width in metres"),
        new_depth: z.number().optional().describe("New depth in metres"),
      }),
      execute: ({ room_id, new_width, new_depth }) =>
        callBackendTool(
          userId,
          `projects/${projectId}/rooms/${encodeURIComponent(room_id)}/resize`,
          {
            method: "POST",
            body: JSON.stringify({ new_width, new_depth }),
          }
        ),
    }),

    swap_rooms: tool({
      description: "Swap the positions of two rooms on the same floor",
      inputSchema: z.object({
        room_id_a: roomIdSchema,
        room_id_b: roomIdSchema,
      }),
      execute: ({ room_id_a, room_id_b }) =>
        callBackendTool(userId, `projects/${projectId}/rooms/swap`, {
          method: "POST",
          body: JSON.stringify({ room_id_a, room_id_b }),
        }),
    }),

    add_room: tool({
      description: "Add a new room to a floor at a specified or auto-placed location",
      inputSchema: z.object({
        floor: z.enum(["gf", "ff", "sf", "basement"]),
        type: z.string().describe("Room type e.g. bedroom, gym, store_room"),
        name: z.string().optional(),
        x: z.number().optional().describe("X position if known"),
        y: z.number().optional().describe("Y position if known"),
        width: z.number().optional(),
        depth: z.number().optional(),
      }),
      execute: ({ floor, type, name, x, y, width, depth }) =>
        callBackendTool(userId, `projects/${projectId}/rooms`, {
          method: "POST",
          body: JSON.stringify({ floor, type, name, x, y, width, depth }),
        }),
    }),

    remove_room: tool({
      description: "Remove a room from the layout",
      inputSchema: z.object({ room_id: roomIdSchema }),
      execute: ({ room_id }) =>
        callBackendTool(userId, `projects/${projectId}/rooms/${encodeURIComponent(room_id)}`, {
          method: "DELETE",
        }),
    }),

    undo_last_change: tool({
      description: "Undo the last room modification",
      inputSchema: z.object({}),
      execute: () =>
        callBackendTool(userId, `projects/${projectId}/rooms/undo`, {
          method: "POST",
        }),
    }),

    refresh_layout: tool({
      description:
        "Fetch the current layout state so the floor plan re-renders. Call this after every successful room modification (move, resize, add, remove, swap, undo).",
      inputSchema: z.object({}),
      execute: () => callBackendTool(userId, `projects/${projectId}/rooms/layout-state`), // { layout: LayoutData }
    }),
  };
}

type Params = Promise<{ projectId: string }>;

export async function POST(req: Request, { params }: { params: Params }) {
  const { projectId } = await params;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { messages, layoutState, selectedModel } = body;

  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    return Response.json({ error: "No messages provided" }, { status: 400 });
  }

  const hasAnthropic = !!process.env.ANTHROPIC_API_KEY;
  const hasOpenAI = !!process.env.OPENAI_API_KEY;
  const hasOpenRouter = !!process.env.OPENROUTER_API_KEY;

  if (!hasAnthropic && !hasOpenAI && !hasOpenRouter) {
    return Response.json(
      {
        error:
          "No AI API key configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENROUTER_API_KEY in .env.local",
      },
      { status: 503 }
    );
  }

  // OpenRouter only supports Chat Completions — use .chat() not the default call.
  // In @ai-sdk/openai v3+, calling provider(modelId) directly routes to the
  // Responses API (/v1/responses) which OpenRouter doesn't implement.
  const openrouterClient = hasOpenRouter
    ? createOpenAI({
        apiKey: process.env.OPENROUTER_API_KEY ?? "",
        baseURL: "https://openrouter.ai/api/v1",
      })
    : null;

  // Configurable OpenRouter fallback model (env var) — defaults to a current Anthropic slug
  const openrouterFallbackModel = process.env.OPENROUTER_MODEL ?? DEFAULT_OPENROUTER_MODEL_ID;

  const requestedId =
    typeof selectedModel === "string" && selectedModel ? selectedModel : DEFAULT_MODEL_ID;

  const provider = getModelProvider(requestedId);
  const plan = buildModelChainPlan({
    requestedId,
    requestedProvider: provider,
    hasAnthropic,
    hasOpenAI,
    hasOpenRouter,
    defaultModelId: DEFAULT_MODEL_ID,
    fallbackOpenAIModelId: FALLBACK_OPENAI_MODEL_ID,
    openrouterFallbackModel,
  });

  // OpenRouter models must route through .chat() (Chat Completions); every
  // openrouter plan entry is only produced when openrouterClient exists.
  const instantiate = (entry: ModelChainPlanEntry): LanguageModel => {
    switch (entry.provider) {
      case "anthropic":
        return anthropic(entry.modelId);
      case "openai":
        return openai.chat(entry.modelId);
      case "openrouter": {
        if (!openrouterClient) {
          throw new Error("OpenRouter client unavailable");
        }
        return openrouterClient.chat(entry.modelId);
      }
    }
  };

  let modelMessages: Awaited<ReturnType<typeof convertToModelMessages>>;
  try {
    modelMessages = await convertToModelMessages(
      messages as Parameters<typeof convertToModelMessages>[0]
    );
  } catch (convErr) {
    console.error("[agent] convertToModelMessages failed:", convErr);
    return createUIMessageStreamResponse({
      stream: createUIMessageStream({
        execute: ({ writer }) => {
          writer.write({
            type: "error",
            errorText:
              convErr instanceof Error
                ? convErr.message
                : "Failed to process messages. Try refreshing the page.",
          });
        },
      }),
    });
  }

  const systemPrompt = buildSystemPrompt(layoutState);
  const tools = buildTools(projectId, session.user.id);

  // Each plan entry becomes a chain entry that lazily opens a streamText run.
  // In ai@6 a provider failure surfaces as an `error` CHUNK (never a thrown
  // rejection), so the raw error is captured via toUIMessageStream's onError —
  // runModelChain reads it to decide whether to fall back to the next provider.
  const entries: ModelChainEntry[] = plan.map((planEntry) => {
    const model = instantiate(planEntry);
    return {
      label: planEntry.label,
      providerName: planEntry.providerName,
      open: ({ sendStart }) => {
        let rawError: unknown;
        const result = streamText({
          model,
          system: systemPrompt,
          messages: modelMessages,
          stopWhen: stepCountIs(10),
          tools,
        });
        const stream = result.toUIMessageStream({
          sendStart,
          onError: (err) => {
            rawError = err;
            return err instanceof Error ? err.message : String(err);
          },
        });
        return { stream, getRawError: () => rawError };
      },
    };
  });

  // Use createUIMessageStream to enable runtime model fallback:
  // if the primary model fails (billing, rate limit), transparently retry the next.
  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      // Adapt the SDK writer to ChainWriter: every chunk runModelChain forwards
      // is either a real UIMessageChunk from toUIMessageStream or a synthetic
      // {type:"error", errorText} — both valid inputs to writer.write.
      execute: ({ writer }) =>
        runModelChain(entries, {
          write: (chunk) => writer.write(chunk as Parameters<typeof writer.write>[0]),
        }),
      onError: (err) => {
        console.error("[agent] Stream error:", err);
        return err instanceof Error ? err.message : "Agent error — check server logs";
      },
    }),
  });
}
