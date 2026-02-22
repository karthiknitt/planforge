import { anthropic } from "@ai-sdk/anthropic";
import { openai } from "@ai-sdk/openai";
import type { LanguageModel } from "ai";
import {
  convertToModelMessages,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
  streamText,
  tool,
} from "ai";
import { z } from "zod";

export const maxDuration = 60;

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
- Always check compliance after making changes using get_compliance_status.
- If a change creates a violation, undo it and explain why.
- Acknowledge what you did after each successful tool call.
- Keep undo available — remind users they can say "undo" after changes.`;
}

function buildTools(projectId: string, backendHeaders: Record<string, string>) {
  return {
    get_room_list: tool({
      description: "List all rooms on a floor or all floors",
      inputSchema: z.object({
        floor: z.enum(["gf", "ff", "sf", "basement", "all"]).describe("Which floor to list"),
      }),
      execute: async ({ floor }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms?floor=${floor}`, {
          headers: backendHeaders,
        });
        return res.json();
      },
    }),

    get_room_details: tool({
      description: "Get details for a specific room by ID",
      inputSchema: z.object({ room_id: z.string() }),
      execute: async ({ room_id }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}`, {
          headers: backendHeaders,
        });
        return res.json();
      },
    }),

    get_compliance_status: tool({
      description: "Check current compliance status of the layout",
      inputSchema: z.object({}),
      execute: async () => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/compliance`, {
          headers: backendHeaders,
        });
        return res.json();
      },
    }),

    get_available_space: tool({
      description: "Get available (unoccupied) space on a floor",
      inputSchema: z.object({
        floor: z.enum(["gf", "ff", "sf", "basement"]),
      }),
      execute: async ({ floor }) => {
        const res = await fetch(
          `${BACKEND}/api/projects/${projectId}/available-space?floor=${floor}`,
          { headers: backendHeaders }
        );
        return res.json();
      },
    }),

    move_room: tool({
      description: "Move a room to new coordinates. Validates no overlap and setback compliance.",
      inputSchema: z.object({
        room_id: z.string(),
        new_x: z.number().describe("New X position in metres"),
        new_y: z.number().describe("New Y position in metres"),
      }),
      execute: async ({ room_id, new_x, new_y }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}/move`, {
          method: "POST",
          headers: backendHeaders,
          body: JSON.stringify({ x: new_x, y: new_y }),
        });
        return res.json();
      },
    }),

    resize_room: tool({
      description: "Resize a room. Validates area minimums and no overlaps.",
      inputSchema: z.object({
        room_id: z.string(),
        new_width: z.number().optional().describe("New width in metres"),
        new_depth: z.number().optional().describe("New depth in metres"),
      }),
      execute: async ({ room_id, new_width, new_depth }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}/resize`, {
          method: "POST",
          headers: backendHeaders,
          body: JSON.stringify({ new_width, new_depth }),
        });
        return res.json();
      },
    }),

    swap_rooms: tool({
      description: "Swap the positions of two rooms on the same floor",
      inputSchema: z.object({
        room_id_a: z.string(),
        room_id_b: z.string(),
      }),
      execute: async ({ room_id_a, room_id_b }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/swap`, {
          method: "POST",
          headers: backendHeaders,
          body: JSON.stringify({ room_id_a, room_id_b }),
        });
        return res.json();
      },
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
      execute: async ({ floor, type, name, x, y, width, depth }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms`, {
          method: "POST",
          headers: backendHeaders,
          body: JSON.stringify({ floor, type, name, x, y, width, depth }),
        });
        return res.json();
      },
    }),

    remove_room: tool({
      description: "Remove a room from the layout",
      inputSchema: z.object({ room_id: z.string() }),
      execute: async ({ room_id }) => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}`, {
          method: "DELETE",
          headers: backendHeaders,
        });
        return res.json();
      },
    }),

    undo_last_change: tool({
      description: "Undo the last room modification",
      inputSchema: z.object({}),
      execute: async () => {
        const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/undo`, {
          method: "POST",
          headers: backendHeaders,
        });
        return res.json();
      },
    }),
  };
}

/** Check if an error is a billing/auth/rate-limit issue worth retrying on a different provider */
function isProviderError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return /billing|balance|insufficient|quota|rate.limit|payment|credit|402|429/i.test(msg);
}

type Params = Promise<{ projectId: string }>;

export async function POST(req: Request, { params }: { params: Params }) {
  const { projectId } = await params;

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { messages, layoutState, userId, forceOpenAI } = body;

  if (!userId) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }

  if (!messages || !Array.isArray(messages) || messages.length === 0) {
    return Response.json({ error: "No messages provided" }, { status: 400 });
  }

  const hasAnthropic = !!process.env.ANTHROPIC_API_KEY;
  const hasOpenAI = !!process.env.OPENAI_API_KEY;

  if (!hasAnthropic && !hasOpenAI) {
    return Response.json(
      { error: "No AI API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env.local" },
      { status: 503 }
    );
  }

  const lastMsg = messages.at(-1);
  const lastContent =
    typeof lastMsg?.content === "string"
      ? lastMsg.content
      : (lastMsg?.parts
          ?.filter((p: { type: string }) => p.type === "text")
          .map((p: { text: string }) => p.text)
          .join("") ?? "");

  const isComplex =
    lastContent.length > 200 ||
    /redesign|optimize|rearrange all|vastu layout|redo|completely/i.test(lastContent);

  // Build model priority: try Anthropic first (unless forced to OpenAI), fall back to OpenAI
  const models: { model: LanguageModel; label: string }[] = [];
  if (!forceOpenAI && hasAnthropic) {
    models.push({
      model: anthropic(isComplex ? "claude-opus-4-6" : "claude-sonnet-4-6"),
      label: isComplex ? "claude-opus" : "claude-sonnet",
    });
  }
  if (hasOpenAI) {
    models.push({ model: openai("gpt-5.2"), label: "gpt-5.2" });
  }
  // If only Anthropic key and forced OpenAI, still try Anthropic as last resort
  if (models.length === 0 && hasAnthropic) {
    models.push({ model: anthropic("claude-sonnet-4-6"), label: "claude-sonnet-fallback" });
  }

  const backendHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    "X-User-Id": userId as string,
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
  const tools = buildTools(projectId, backendHeaders);

  // Use createUIMessageStream to enable runtime model fallback:
  // if primary model fails (billing, rate limit), transparently retry with next model
  return createUIMessageStreamResponse({
    stream: createUIMessageStream({
      execute: async ({ writer }) => {
        let lastError: unknown;

        for (let i = 0; i < models.length; i++) {
          const { model, label } = models[i];
          const hasMoreModels = i < models.length - 1;
          try {
            console.log(`[agent] Trying model: ${label}`);
            const result = streamText({
              model,
              system: systemPrompt,
              messages: modelMessages,
              stopWhen: stepCountIs(10),
              tools,
            });

            // Consume the full stream — this is where provider errors surface
            const uiStream = result.toUIMessageStream({ sendStart: true });
            for await (const chunk of uiStream) {
              writer.write(chunk);
            }

            console.log(`[agent] Completed with: ${label}`);
            return;
          } catch (err) {
            lastError = err;
            const errMsg = err instanceof Error ? err.message : String(err);
            console.error(`[agent] Model ${label} failed: ${errMsg}`);

            if (isProviderError(err) && hasMoreModels) {
              console.log(`[agent] Falling back to next model...`);
              continue;
            }
            break;
          }
        }

        // All models failed
        const errText = lastError instanceof Error ? lastError.message : "All AI providers failed";
        console.error("[agent] All models exhausted:", errText);
        writer.write({ type: "error", errorText: errText });
      },
      onError: (err) => {
        console.error("[agent] Stream error:", err);
        return err instanceof Error ? err.message : "Agent error — check server logs";
      },
    }),
  });
}
