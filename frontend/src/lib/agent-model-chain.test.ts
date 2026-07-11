import { describe, expect, test } from "bun:test";
import {
  buildModelChainPlan,
  type ModelChainEntry,
  runModelChain,
  type UIStreamChunk,
} from "./agent-model-chain";

const SILENT = { log: () => {}, error: () => {} };

function apiError(message: string, statusCode?: number): Error {
  const err = new Error(message) as Error & { statusCode?: number };
  if (statusCode !== undefined) {
    err.statusCode = statusCode;
  }
  return err;
}

function recordingWriter() {
  const written: UIStreamChunk[] = [];
  return { writer: { write: (c: UIStreamChunk) => written.push(c) }, written };
}

interface StubConfig {
  label: string;
  providerName: string;
  chunks: UIStreamChunk[];
  rawError?: unknown;
}

// Builds a ModelChainEntry backed by a fixed chunk sequence. It honours
// `sendStart` exactly like ai@6's toUIMessageStream: the `start` chunk is
// suppressed unless sendStart is true, so a fallback attempt never re-emits it.
function stubEntry(config: StubConfig) {
  let opened = 0;
  let lastSendStart: boolean | undefined;
  const entry: ModelChainEntry = {
    label: config.label,
    providerName: config.providerName,
    open: ({ sendStart }) => {
      opened += 1;
      lastSendStart = sendStart;
      const chunks = config.chunks.filter((c) => c.type !== "start" || sendStart);
      async function* gen() {
        for (const c of chunks) {
          yield c;
        }
      }
      return { stream: gen(), getRawError: () => config.rawError };
    },
  };
  return {
    entry,
    getOpened: () => opened,
    getLastSendStart: () => lastSendStart,
  };
}

describe("runModelChain", () => {
  test("(a) a fallback-worthy error chunk is swallowed, the next model runs, and only one start is written", async () => {
    const m0 = stubEntry({
      label: "primary",
      providerName: "Anthropic",
      chunks: [{ type: "start" }, { type: "error", errorText: "overloaded" }],
      rawError: apiError("overloaded", 503),
    });
    const m1 = stubEntry({
      label: "fallback",
      providerName: "OpenAI",
      chunks: [
        { type: "start" },
        { type: "text-start", id: "t1" },
        { type: "text-delta", id: "t1", delta: "hi" },
        { type: "finish" },
      ],
    });
    const { writer, written } = recordingWriter();

    await runModelChain([m0.entry, m1.entry], writer, { logger: SILENT });

    expect(m1.getOpened()).toBe(1);
    expect(m0.getLastSendStart()).toBe(true);
    expect(m1.getLastSendStart()).toBe(false);
    expect(written.filter((c) => c.type === "start")).toHaveLength(1);
    expect(written.some((c) => c.type === "error")).toBe(false);
    expect(written.some((c) => c.type === "text-delta")).toBe(true);
  });

  test("(b) when every model fails, one aggregated error part carries each provider description", async () => {
    const m0 = stubEntry({
      label: "primary",
      providerName: "Anthropic",
      chunks: [{ type: "start" }, { type: "error", errorText: "boom" }],
      rawError: apiError("internal server error", 500),
    });
    const m1 = stubEntry({
      label: "fallback",
      providerName: "OpenAI",
      chunks: [{ type: "error", errorText: "boom" }],
      rawError: apiError("service unavailable", 503),
    });
    const { writer, written } = recordingWriter();

    await runModelChain([m0.entry, m1.entry], writer, { logger: SILENT });

    const errors = written.filter((c) => c.type === "error");
    expect(errors).toHaveLength(1);
    const text = String(errors[0].errorText);
    expect(text).toContain("Anthropic: service unavailable");
    expect(text).toContain("OpenAI: service unavailable");
    expect(text).toContain("check API keys");
  });

  test("(c) a content-policy refusal is forwarded without any fallback attempt", async () => {
    const m0 = stubEntry({
      label: "primary",
      providerName: "Anthropic",
      chunks: [{ type: "start" }, { type: "error", errorText: "refusal" }],
      rawError: apiError("stop_reason: refusal - request declined for safety reasons"),
    });
    const m1 = stubEntry({
      label: "fallback",
      providerName: "OpenAI",
      chunks: [
        { type: "start" },
        { type: "text-delta", id: "t1", delta: "hi" },
        { type: "finish" },
      ],
    });
    const { writer, written } = recordingWriter();

    await runModelChain([m0.entry, m1.entry], writer, { logger: SILENT });

    expect(m1.getOpened()).toBe(0);
    const errors = written.filter((c) => c.type === "error");
    expect(errors).toHaveLength(1);
    expect(String(errors[0].errorText).toLowerCase()).toContain("refusal");
  });

  test("(d) when the first model succeeds, no fallback model is opened and every chunk is forwarded", async () => {
    const m0 = stubEntry({
      label: "primary",
      providerName: "Anthropic",
      chunks: [
        { type: "start" },
        { type: "text-start", id: "t1" },
        { type: "text-delta", id: "t1", delta: "hello" },
        { type: "text-end", id: "t1" },
        { type: "finish" },
      ],
    });
    const m1 = stubEntry({
      label: "fallback",
      providerName: "OpenAI",
      chunks: [{ type: "start" }, { type: "text-delta", id: "x", delta: "unused" }],
    });
    const { writer, written } = recordingWriter();

    await runModelChain([m0.entry, m1.entry], writer, { logger: SILENT });

    expect(m0.getOpened()).toBe(1);
    expect(m1.getOpened()).toBe(0);
    expect(written.some((c) => c.type === "error")).toBe(false);
    expect(written.map((c) => c.type)).toEqual([
      "start",
      "text-start",
      "text-delta",
      "text-end",
      "finish",
    ]);
  });

  test("a raw error captured via getRawError drives fallback even when the chunk only carries text", async () => {
    // Simulates the real route: toUIMessageStream flattens the chunk's errorText
    // to a message, but the raw error (with statusCode) is captured separately.
    const m0 = stubEntry({
      label: "primary",
      providerName: "OpenRouter",
      chunks: [{ type: "start" }, { type: "error", errorText: "opaque" }],
      rawError: apiError("opaque", 429),
    });
    const m1 = stubEntry({
      label: "fallback",
      providerName: "Anthropic",
      chunks: [{ type: "text-delta", id: "t", delta: "ok" }, { type: "finish" }],
    });
    const { writer, written } = recordingWriter();

    await runModelChain([m0.entry, m1.entry], writer, { logger: SILENT });

    expect(m1.getOpened()).toBe(1);
    expect(written.some((c) => c.type === "error")).toBe(false);
  });

  test("an empty chain writes a single generic error", async () => {
    const { writer, written } = recordingWriter();
    await runModelChain([], writer, { logger: SILENT });
    expect(written).toHaveLength(1);
    expect(written[0].type).toBe("error");
  });
});

describe("buildModelChainPlan", () => {
  const base = {
    defaultModelId: "claude-sonnet-5",
    fallbackOpenAIModelId: "gpt-4o",
    openrouterFallbackModel: "anthropic/claude-sonnet-5",
  };

  test("anthropic request with OpenAI available chains anthropic → openai fallback", () => {
    const plan = buildModelChainPlan({
      ...base,
      requestedId: "claude-opus-4-8",
      requestedProvider: "anthropic",
      hasAnthropic: true,
      hasOpenAI: true,
      hasOpenRouter: false,
    });
    expect(plan.map((p) => [p.provider, p.modelId])).toEqual([
      ["anthropic", "claude-opus-4-8"],
      ["openai", "gpt-4o"],
    ]);
  });

  test("anthropic request with no other provider yields a single-model chain", () => {
    const plan = buildModelChainPlan({
      ...base,
      requestedId: "claude-opus-4-8",
      requestedProvider: "anthropic",
      hasAnthropic: true,
      hasOpenAI: false,
      hasOpenRouter: false,
    });
    expect(plan).toHaveLength(1);
    expect(plan[0].modelId).toBe("claude-opus-4-8");
  });

  test("openrouter request falls back to anthropic when available", () => {
    const plan = buildModelChainPlan({
      ...base,
      requestedId: "google/gemini-2.5-pro",
      requestedProvider: "openrouter",
      hasAnthropic: true,
      hasOpenAI: false,
      hasOpenRouter: true,
    });
    expect(plan.map((p) => p.provider)).toEqual(["openrouter", "anthropic"]);
    expect(plan[0].modelId).toBe("google/gemini-2.5-pro");
  });

  test("an unmatched provider tries every configured provider in priority order", () => {
    const plan = buildModelChainPlan({
      ...base,
      requestedId: "unknown-model",
      requestedProvider: null,
      hasAnthropic: true,
      hasOpenAI: true,
      hasOpenRouter: true,
    });
    expect(plan.map((p) => p.provider)).toEqual(["anthropic", "openai", "openrouter"]);
  });

  test("a requested provider whose key is missing falls through to the available providers", () => {
    const plan = buildModelChainPlan({
      ...base,
      requestedId: "gpt-4.1",
      requestedProvider: "openai",
      hasAnthropic: true,
      hasOpenAI: false,
      hasOpenRouter: false,
    });
    expect(plan.map((p) => p.provider)).toEqual(["anthropic"]);
    expect(plan[0].modelId).toBe("claude-sonnet-5");
  });
});
