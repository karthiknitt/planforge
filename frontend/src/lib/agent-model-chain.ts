import {
  describeProviderError as defaultDescribeProviderError,
  shouldFallback as defaultShouldFallback,
} from "@/lib/agent-errors";
import type { ModelProvider } from "@/lib/models";

// A UI message stream chunk. We only ever branch on `type === "error"`; every
// other shape is forwarded to the client untouched.
export interface UIStreamChunk {
  type: string;
  [key: string]: unknown;
}

export interface StreamAttempt {
  /** UI message chunks for one model attempt. */
  stream: AsyncIterable<UIStreamChunk>;
  /**
   * The raw provider error captured while streaming (via toUIMessageStream's
   * onError), or undefined if the attempt produced no error. Populated by the
   * time an `error` chunk is yielded, since onError runs to build that chunk.
   */
  getRawError: () => unknown;
}

export interface ModelChainEntry {
  label: string;
  providerName: string;
  /**
   * Opens the UI stream for this model. `sendStart` must be true only for the
   * first attempt, so a fallback after partial output does not emit a duplicate
   * `start` chunk.
   */
  open: (opts: { sendStart: boolean }) => StreamAttempt;
}

export interface ChainWriter {
  write: (chunk: UIStreamChunk) => void;
}

export interface RunModelChainDeps {
  shouldFallback?: (err: unknown) => boolean;
  describeProviderError?: (err: unknown, providerName: string) => string;
  logger?: Pick<Console, "log" | "error">;
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function errorFromChunk(chunk: UIStreamChunk): Error {
  const text = typeof chunk.errorText === "string" ? chunk.errorText : "Unknown provider error";
  return new Error(text);
}

function aggregateErrorText(descriptions: string[]): string {
  return descriptions.length > 0
    ? `${descriptions.join("; ")} — check API keys in Vercel env`
    : "All AI providers failed";
}

type AttemptResult = { type: "success" } | { type: "error"; rawError: unknown };

// Consumes one model's stream. Non-error chunks are forwarded immediately;
// the first error chunk stops consumption and surfaces the raw error so the
// caller can decide whether to fall back. In ai@6 provider failures arrive as
// `error` CHUNKS (never thrown), but the try/catch is kept as a belt-and-braces
// guard for a genuinely rejecting iterable.
async function consumeAttempt(
  entry: ModelChainEntry,
  sendStart: boolean,
  writer: ChainWriter
): Promise<AttemptResult> {
  const attempt = entry.open({ sendStart });
  try {
    for await (const chunk of attempt.stream) {
      if (chunk.type === "error") {
        const rawError = attempt.getRawError() ?? errorFromChunk(chunk);
        return { type: "error", rawError };
      }
      writer.write(chunk);
    }
    return { type: "success" };
  } catch (err) {
    return { type: "error", rawError: err };
  }
}

/**
 * Runs the model chain, transparently falling back to the next provider when a
 * model fails with a retryable error. Only the first model emits a `start`
 * chunk; a swallowed error is never forwarded to the client. When the chain is
 * exhausted (or a non-retryable error occurs), a single aggregated error chunk
 * carrying every provider's description is written.
 */
export async function runModelChain(
  entries: ModelChainEntry[],
  writer: ChainWriter,
  deps: RunModelChainDeps = {}
): Promise<void> {
  const shouldFallback = deps.shouldFallback ?? defaultShouldFallback;
  const describeProviderError = deps.describeProviderError ?? defaultDescribeProviderError;
  const logger = deps.logger ?? console;

  const failureDescriptions: string[] = [];

  for (let i = 0; i < entries.length; i += 1) {
    const entry = entries[i];
    const hasMoreModels = i < entries.length - 1;

    logger.log(`[agent] Trying model: ${entry.label}`);
    const result = await consumeAttempt(entry, i === 0, writer);

    if (result.type === "success") {
      logger.log(`[agent] Completed with: ${entry.label}`);
      return;
    }

    failureDescriptions.push(describeProviderError(result.rawError, entry.providerName));
    logger.error(`[agent] Model ${entry.label} failed: ${messageOf(result.rawError)}`);

    if (hasMoreModels && shouldFallback(result.rawError)) {
      logger.log("[agent] Falling back to next model...");
      continue;
    }

    // Last model, or an error not worth retrying: report every failure so far.
    const errText = aggregateErrorText(failureDescriptions);
    logger.error(`[agent] Model chain exhausted: ${errText}`);
    writer.write({ type: "error", errorText: errText });
    return;
  }

  // Reached only with an empty chain.
  writer.write({ type: "error", errorText: aggregateErrorText(failureDescriptions) });
}

export interface ModelChainPlanEntry {
  provider: ModelProvider;
  modelId: string;
  label: string;
  providerName: string;
}

export interface BuildModelChainPlanInput {
  requestedId: string;
  requestedProvider: ModelProvider | null;
  hasAnthropic: boolean;
  hasOpenAI: boolean;
  hasOpenRouter: boolean;
  defaultModelId: string;
  fallbackOpenAIModelId: string;
  openrouterFallbackModel: string;
}

/**
 * Decides the ordered provider chain (primary + fallbacks) for a request. Pure
 * — it returns descriptors, leaving actual model instantiation to the caller so
 * the branching can be unit-tested without provider SDKs.
 */
export function buildModelChainPlan(input: BuildModelChainPlanInput): ModelChainPlanEntry[] {
  const {
    requestedId,
    requestedProvider,
    hasAnthropic,
    hasOpenAI,
    hasOpenRouter,
    defaultModelId,
    fallbackOpenAIModelId,
    openrouterFallbackModel,
  } = input;

  const anthropicDefault: ModelChainPlanEntry = {
    provider: "anthropic",
    modelId: defaultModelId,
    label: "claude-sonnet-fallback",
    providerName: "Anthropic",
  };
  const openaiFallback: ModelChainPlanEntry = {
    provider: "openai",
    modelId: fallbackOpenAIModelId,
    label: "gpt-4o-fallback",
    providerName: "OpenAI",
  };
  const openrouterFallback: ModelChainPlanEntry = {
    provider: "openrouter",
    modelId: openrouterFallbackModel,
    label: `openrouter-fallback(${openrouterFallbackModel})`,
    providerName: "OpenRouter",
  };

  const plan: ModelChainPlanEntry[] = [];

  if (requestedProvider === "openrouter" && hasOpenRouter) {
    plan.push({
      provider: "openrouter",
      modelId: requestedId,
      label: requestedId,
      providerName: "OpenRouter",
    });
    if (hasAnthropic) {
      plan.push(anthropicDefault);
    } else if (hasOpenAI) {
      plan.push(openaiFallback);
    }
  } else if (requestedProvider === "anthropic" && hasAnthropic) {
    plan.push({
      provider: "anthropic",
      modelId: requestedId,
      label: requestedId,
      providerName: "Anthropic",
    });
    if (hasOpenAI) {
      plan.push(openaiFallback);
    } else if (hasOpenRouter) {
      plan.push(openrouterFallback);
    }
  } else if (requestedProvider === "openai" && hasOpenAI) {
    plan.push({
      provider: "openai",
      modelId: requestedId,
      label: requestedId,
      providerName: "OpenAI",
    });
    if (hasAnthropic) {
      plan.push(anthropicDefault);
    } else if (hasOpenRouter) {
      plan.push(openrouterFallback);
    }
  } else {
    // No matching provider available — try all in priority order.
    if (hasAnthropic) {
      plan.push({
        provider: "anthropic",
        modelId: defaultModelId,
        label: defaultModelId,
        providerName: "Anthropic",
      });
    }
    if (hasOpenAI) {
      plan.push({
        provider: "openai",
        modelId: fallbackOpenAIModelId,
        label: fallbackOpenAIModelId,
        providerName: "OpenAI",
      });
    }
    if (hasOpenRouter) {
      plan.push({
        provider: "openrouter",
        modelId: openrouterFallbackModel,
        label: `openrouter(${openrouterFallbackModel})`,
        providerName: "OpenRouter",
      });
    }
  }

  return plan;
}
