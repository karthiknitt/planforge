"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { Mic, MicOff, RotateCcw, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { useSession } from "@/lib/auth-client";
import type { LayoutData } from "@/lib/layout-types";

interface ChatPanelProps {
  projectId: string;
  currentLayout: LayoutData | null;
  onLayoutUpdate?: (layout: LayoutData) => void;
}

export function ChatPanel({ projectId, currentLayout, onLayoutUpdate }: ChatPanelProps) {
  const { data: session } = useSession();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [input, setInput] = useState("");

  const sessionRef = useRef(session);
  const layoutRef = useRef(currentLayout);
  sessionRef.current = session;
  layoutRef.current = currentLayout;

  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `/api/agent/${projectId}`,
        prepareSendMessagesRequest: ({ messages }) => ({
          body: {
            messages,
            layoutState: layoutRef.current,
            userId: sessionRef.current?.user.id,
          },
        }),
      }),
    [projectId]
  );

  const [agentError, setAgentError] = useState<string | null>(null);

  const {
    messages,
    sendMessage,
    status,
    error: chatError,
  } = useChat({
    transport,
    onError: (err) => {
      console.error("[ChatPanel] useChat error:", err);
      setAgentError(err instanceof Error ? err.message : "Agent failed to respond. Try again.");
    },
    onFinish: ({ message }) => {
      setAgentError(null);
      for (const part of message.parts ?? []) {
        if (part.type === "tool-invocation" && part.state === "output-available") {
          const output = part.output as Record<string, unknown> | null;
          if (output?.layout && onLayoutUpdate) {
            onLayoutUpdate(output.layout as LayoutData);
          }
        }
      }
      setTimeout(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
      }, 50);
    },
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: messages.length and status are intentional scroll triggers
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, status]);

  const {
    status: voiceStatus,
    error: voiceError,
    toggle: toggleVoice,
  } = useVoiceInput({
    onTranscript: (text) => setInput((prev) => (prev ? `${prev} ${text}` : text)),
  });

  const sendUndo = useCallback(() => {
    sendMessage({ text: "Undo the last change" });
  }, [sendMessage]);

  const isLoading = status === "submitted" || status === "streaming";
  const isRecording = voiceStatus === "recording";
  const isTranscribing = voiceStatus === "transcribing";

  const displayError = agentError ?? chatError?.message ?? voiceError;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    setAgentError(null);
    sendMessage({ text: input });
    setInput("");
  };

  function getMessageText(msg: (typeof messages)[number]): string {
    if (!msg.parts || msg.parts.length === 0) {
      return "";
    }
    return msg.parts
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("");
  }

  return (
    <div className="flex flex-col h-[520px] rounded-xl border border-border bg-background overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/30">
        <div>
          <p className="text-sm font-semibold">AI Layout Assistant</p>
          <p className="text-xs text-muted-foreground">Ask to move, resize, or add rooms</p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={sendUndo}
          disabled={isLoading}
          title="Undo last change"
        >
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
          Undo
        </Button>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 flex flex-col gap-3">
        {messages.length === 0 && !isLoading && (
          <div className="text-center text-muted-foreground text-sm py-12">
            <p className="font-medium">Start a conversation</p>
            <p className="mt-1 text-xs">
              Type or click <strong>Speak</strong> to use voice.
            </p>
            <p className="mt-1 text-xs">
              Try: &quot;Make the master bedroom larger&quot; or &quot;Add a dining room on the
              first floor&quot;
            </p>
          </div>
        )}

        {messages.map((msg) => {
          const text = getMessageText(msg);
          const toolParts = msg.parts?.filter((p) => p.type === "tool-invocation") ?? [];
          const hasContent = text || toolParts.length > 0;

          if (!hasContent && msg.role === "assistant") return null;

          return (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={[
                  "max-w-[80%] rounded-xl px-3 py-2 text-sm",
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground",
                ].join(" ")}
              >
                {toolParts.map((part) => {
                  const tp = part as { toolCallId?: string; toolName?: string };
                  return (
                    <div
                      key={tp.toolCallId ?? tp.toolName ?? "tool"}
                      className="mb-1 text-xs opacity-70 italic"
                    >
                      {`⚙ ${tp.toolName ?? "tool"}…`}
                    </div>
                  );
                })}
                {text && <p className="whitespace-pre-wrap leading-relaxed">{text}</p>}
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-xl px-3 py-2 text-sm text-muted-foreground animate-pulse">
              Thinking…
            </div>
          </div>
        )}
      </div>

      {/* Agent / voice errors */}
      {displayError && (
        <div className="px-4 py-2 text-xs text-destructive border-t border-border bg-destructive/5">
          <p className="font-medium">Error</p>
          <p>{displayError}</p>
        </div>
      )}

      {/* Input bar */}
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 px-4 py-3 border-t border-border"
      >
        <button
          type="button"
          onClick={toggleVoice}
          disabled={isTranscribing}
          title={isRecording ? "Stop recording" : "Click to speak"}
          className={[
            "flex h-9 shrink-0 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium transition-colors",
            isRecording
              ? "border-red-500 bg-red-500/10 text-red-600 animate-pulse"
              : isTranscribing
                ? "border-amber-500 bg-amber-500/10 text-amber-600"
                : "border-border text-muted-foreground hover:bg-muted",
          ].join(" ")}
        >
          {isRecording ? (
            <>
              <MicOff className="h-3.5 w-3.5" />
              Stop
            </>
          ) : isTranscribing ? (
            <>
              <Mic className="h-3.5 w-3.5" />…
            </>
          ) : (
            <>
              <Mic className="h-3.5 w-3.5" />
              Speak
            </>
          )}
        </button>

        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            isRecording
              ? "Recording… click mic to stop"
              : isTranscribing
                ? "Transcribing…"
                : "Ask about your floor plan…"
          }
          disabled={isLoading || isRecording || isTranscribing}
          className="flex-1"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e as unknown as React.FormEvent<HTMLFormElement>);
            }
          }}
        />

        <Button type="submit" size="sm" disabled={isLoading || !input.trim()}>
          <Send className="h-3.5 w-3.5" />
        </Button>
      </form>
    </div>
  );
}
