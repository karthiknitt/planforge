export type ModelProvider = "anthropic" | "openai";

export interface ModelOption {
  id: string;
  label: string;
  provider: ModelProvider;
  description: string;
  isDefault?: boolean;
}

export const MODEL_OPTIONS: ModelOption[] = [
  {
    id: "claude-opus-4-6",
    label: "Claude Opus 4.6",
    provider: "anthropic",
    description: "Most capable",
  },
  {
    id: "claude-sonnet-4-6",
    label: "Claude Sonnet 4.6",
    provider: "anthropic",
    description: "Balanced",
    isDefault: true,
  },
  {
    id: "claude-haiku-4-5",
    label: "Claude Haiku 4.5",
    provider: "anthropic",
    description: "Fast & economical",
  },
  { id: "gpt-5.2", label: "GPT-5.2", provider: "openai", description: "Most capable" },
  { id: "gpt-4o", label: "GPT-4o", provider: "openai", description: "Fast multimodal" },
  { id: "o3", label: "o3", provider: "openai", description: "Advanced reasoning" },
  { id: "o4-mini", label: "o4-mini", provider: "openai", description: "Fast reasoning" },
];

export const DEFAULT_MODEL_ID = "claude-sonnet-4-6";

export function getModelProvider(modelId: string): ModelProvider | null {
  return MODEL_OPTIONS.find((m) => m.id === modelId)?.provider ?? null;
}
