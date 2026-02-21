import { anthropic } from "@ai-sdk/anthropic";
import { streamText } from "ai";
import { z } from "zod";

export const maxDuration = 30;

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

type Params = Promise<{ projectId: string }>;

export async function POST(req: Request, { params }: { params: Params }) {
  const { messages, layoutState, userId } = await req.json();
  const { projectId } = await params;

  if (!userId) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
  }

  const headers = { "Content-Type": "application/json", "X-User-Id": userId };

  // Use opus for complex, sonnet for simple requests
  const lastMsg = messages.at(-1)?.content ?? "";
  const isComplex =
    lastMsg.length > 200 ||
    /redesign|optimize|rearrange all|vastu layout|redo|completely/i.test(lastMsg);
  const model = anthropic(isComplex ? "claude-opus-4-6" : "claude-sonnet-4-6");

  const result = streamText({
    model,
    system: buildSystemPrompt(layoutState),
    messages,
    maxSteps: 10,
    tools: {
      get_room_list: {
        description: "List all rooms on a floor or all floors",
        parameters: z.object({
          floor: z.enum(["gf", "ff", "sf", "basement", "all"]).describe("Which floor to list"),
        }),
        execute: async ({ floor }) => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms?floor=${floor}`, {
            headers,
          });
          return res.json();
        },
      },

      get_room_details: {
        description: "Get details for a specific room by ID",
        parameters: z.object({ room_id: z.string() }),
        execute: async ({ room_id }) => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}`, {
            headers,
          });
          return res.json();
        },
      },

      get_compliance_status: {
        description: "Check current compliance status of the layout",
        parameters: z.object({}),
        execute: async () => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/compliance`, { headers });
          return res.json();
        },
      },

      get_available_space: {
        description: "Get available (unoccupied) space on a floor",
        parameters: z.object({
          floor: z.enum(["gf", "ff", "sf", "basement"]),
        }),
        execute: async ({ floor }) => {
          const res = await fetch(
            `${BACKEND}/api/projects/${projectId}/available-space?floor=${floor}`,
            { headers }
          );
          return res.json();
        },
      },

      move_room: {
        description: "Move a room to new coordinates. Validates no overlap and setback compliance.",
        parameters: z.object({
          room_id: z.string(),
          new_x: z.number().describe("New X position in metres"),
          new_y: z.number().describe("New Y position in metres"),
        }),
        execute: async ({ room_id, new_x, new_y }) => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}/move`, {
            method: "POST",
            headers,
            body: JSON.stringify({ x: new_x, y: new_y }),
          });
          return res.json();
        },
      },

      resize_room: {
        description: "Resize a room. Validates area minimums and no overlaps.",
        parameters: z.object({
          room_id: z.string(),
          new_width: z.number().optional().describe("New width in metres"),
          new_depth: z.number().optional().describe("New depth in metres"),
        }),
        execute: async ({ room_id, new_width, new_depth }) => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}/resize`, {
            method: "POST",
            headers,
            body: JSON.stringify({ new_width, new_depth }),
          });
          return res.json();
        },
      },

      swap_rooms: {
        description: "Swap the positions of two rooms on the same floor",
        parameters: z.object({
          room_id_a: z.string(),
          room_id_b: z.string(),
        }),
        execute: async ({ room_id_a, room_id_b }) => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/swap`, {
            method: "POST",
            headers,
            body: JSON.stringify({ room_id_a, room_id_b }),
          });
          return res.json();
        },
      },

      add_room: {
        description: "Add a new room to a floor at a specified or auto-placed location",
        parameters: z.object({
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
            headers,
            body: JSON.stringify({ floor, type, name, x, y, width, depth }),
          });
          return res.json();
        },
      },

      remove_room: {
        description: "Remove a room from the layout",
        parameters: z.object({ room_id: z.string() }),
        execute: async ({ room_id }) => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/${room_id}`, {
            method: "DELETE",
            headers,
          });
          return res.json();
        },
      },

      undo_last_change: {
        description: "Undo the last room modification",
        parameters: z.object({}),
        execute: async () => {
          const res = await fetch(`${BACKEND}/api/projects/${projectId}/rooms/undo`, {
            method: "POST",
            headers,
          });
          return res.json();
        },
      },
    },
  });

  return result.toDataStreamResponse();
}
