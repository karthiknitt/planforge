import { getToolName, isToolUIPart, type UIMessage } from "ai";

type MessagePart = UIMessage["parts"][number];
type ToolLikePart = Extract<MessagePart, { type: `tool-${string}` } | { type: "dynamic-tool" }>;

export interface ToolResult {
  toolName: string;
  output: unknown;
}

function hasStringTypeField(part: unknown): part is { type: string } {
  return (
    typeof part === "object" &&
    part !== null &&
    typeof (part as { type?: unknown }).type === "string"
  );
}

export function isToolPart(part: unknown): part is ToolLikePart {
  return hasStringTypeField(part) && isToolUIPart(part as MessagePart);
}

export function toolPartLabel(part: unknown): { toolName: string; state: string } {
  if (!isToolPart(part)) {
    return { toolName: "tool", state: "unknown" };
  }
  const state = typeof part.state === "string" ? part.state : "unknown";
  return { toolName: getToolName(part), state };
}

export function extractToolResults(parts: unknown[]): ToolResult[] {
  const results: ToolResult[] = [];
  for (const part of parts) {
    if (!isToolPart(part) || part.state !== "output-available") {
      continue;
    }
    results.push({ toolName: getToolName(part), output: part.output });
  }
  return results;
}
