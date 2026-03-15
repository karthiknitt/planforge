export type ModelProvider = "anthropic" | "openai" | "openrouter";

export type ModelGroup = "Anthropic" | "OpenAI" | "Google" | "OpenRouter";

export type LogoId = "anthropic" | "openai" | "google" | "openrouter";

export interface ModelOption {
  id: string;
  label: string;
  provider: ModelProvider;
  group: ModelGroup;
  logoId: LogoId;
  description: string;
  isDefault?: boolean;
}

export const MODEL_OPTIONS: ModelOption[] = [
  // ── Anthropic ────────────────────────────────────────────────────────────
  {
    id: "claude-opus-4-6",
    label: "Claude Opus 4.6",
    provider: "anthropic",
    group: "Anthropic",
    logoId: "anthropic",
    description: "Most capable",
  },
  {
    id: "claude-sonnet-4-6",
    label: "Claude Sonnet 4.6",
    provider: "anthropic",
    group: "Anthropic",
    logoId: "anthropic",
    description: "Balanced",
    isDefault: true,
  },
  {
    id: "claude-haiku-4-5",
    label: "Claude Haiku 4.5",
    provider: "anthropic",
    group: "Anthropic",
    logoId: "anthropic",
    description: "Fast & economical",
  },

  // ── OpenAI ───────────────────────────────────────────────────────────────
  {
    id: "gpt-5.2",
    label: "GPT-5.2",
    provider: "openai",
    group: "OpenAI",
    logoId: "openai",
    description: "Most capable",
  },
  {
    id: "gpt-4o",
    label: "GPT-4o",
    provider: "openai",
    group: "OpenAI",
    logoId: "openai",
    description: "Fast multimodal",
  },
  {
    id: "o3",
    label: "o3",
    provider: "openai",
    group: "OpenAI",
    logoId: "openai",
    description: "Advanced reasoning",
  },
  {
    id: "o4-mini",
    label: "o4-mini",
    provider: "openai",
    group: "OpenAI",
    logoId: "openai",
    description: "Fast reasoning",
  },

  // ── Google (via OpenRouter) ───────────────────────────────────────────────
  {
    id: "google/gemini-2.5-pro",
    label: "Gemini 2.5 Pro",
    provider: "openrouter",
    group: "Google",
    logoId: "google",
    description: "Most capable Gemini",
  },
  {
    id: "google/gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    provider: "openrouter",
    group: "Google",
    logoId: "google",
    description: "Fast & efficient",
  },
  {
    id: "google/gemini-2.0-flash-001",
    label: "Gemini 2.0 Flash",
    provider: "openrouter",
    group: "Google",
    logoId: "google",
    description: "Balanced Gemini",
  },

  // ── OpenRouter Popular Models ─────────────────────────────────────────────
  {
    id: "deepseek/deepseek-r1",
    label: "DeepSeek R1",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "Strong reasoning",
  },
  {
    id: "deepseek/deepseek-chat-v3-0324",
    label: "DeepSeek V3",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "Fast & capable",
  },
  {
    id: "meta-llama/llama-3.3-70b-instruct",
    label: "Llama 3.3 70B",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "Meta open model",
  },
  {
    id: "meta-llama/llama-4-maverick",
    label: "Llama 4 Maverick",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "Latest Meta model",
  },
  {
    id: "mistralai/mistral-large",
    label: "Mistral Large",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "Mistral's best",
  },
  {
    id: "qwen/qwq-32b",
    label: "QwQ 32B",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "Alibaba reasoning",
  },
  {
    id: "x-ai/grok-3",
    label: "Grok 3",
    provider: "openrouter",
    group: "OpenRouter",
    logoId: "openrouter",
    description: "xAI's latest",
  },
];

export const DEFAULT_MODEL_ID = "claude-sonnet-4-6";

export function getModelProvider(modelId: string): ModelProvider | null {
  return MODEL_OPTIONS.find((m) => m.id === modelId)?.provider ?? null;
}

export function getModelLogoId(modelId: string): LogoId {
  return MODEL_OPTIONS.find((m) => m.id === modelId)?.logoId ?? "openrouter";
}

export const MODEL_GROUPS: ModelGroup[] = ["Anthropic", "OpenAI", "Google", "OpenRouter"];
