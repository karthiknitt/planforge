"use client";

import { useChat } from "ai/react";
import { Mic, MicOff, RotateCcw, Send } from "lucide-react";
import { useCallback, useRef } from "react";

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

  const { messages, input, setInput, handleInputChange, handleSubmit, isLoading, append } = useChat(
    {
      api: `/api/agent/${projectId}`,
      body: {
        layoutState: currentLayout,
        userId: session?.user.id,
      },
      onFinish: (msg) => {
        // If any tool result contains a "layout" key, propagate it upward
        if (msg.parts) {
          for (const part of msg.parts) {
            if (part.type === "tool-result" && typeof part.result === "object") {
              const result = part.result as Record<string, unknown>;
              if (result.layout && onLayoutUpdate) {
                onLayoutUpdate(result.layout as LayoutData);
              }
            }
          }
        }
        // Scroll to bottom
        setTimeout(() => {
          scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
        }, 50);
      },
    }
  );

  const {
    status: voiceStatus,
    error: voiceError,
    toggle: toggleVoice,
  } = useVoiceInput({
    onTranscript: (text) => setInput((prev) => (prev ? `${prev} ${text}` : text)),
  });

  const sendUndo = useCallback(() => {
    append({ role: "user", content: "Undo the last change" });
  }, [append]);

  const isRecording = voiceStatus === "recording";
  const isTranscribing = voiceStatus === "transcribing";

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
        {messages.length === 0 && (
          <div className="text-center text-muted-foreground text-sm py-12">
            <p className="font-medium">Start a conversation</p>
            <p className="mt-1 text-xs">
              Try: &quot;Make the master bedroom larger&quot; or &quot;Move the kitchen to the
              ground floor&quot;
            </p>
          </div>
        )}

        {messages.map((msg) => (
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
              {/* Tool call indicators */}
              {msg.parts
                ?.filter((p) => p.type === "tool-invocation")
                .map((part) => {
                  const toolPart = part as { toolCallId?: string; toolName?: string };
                  return (
                    <div
                      key={toolPart.toolCallId ?? toolPart.toolName ?? part.type}
                      className="mb-1 text-xs opacity-70 italic"
                    >
                      {`⚙ ${toolPart.toolName ?? "tool"}…`}
                    </div>
                  );
                })}
              <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-muted rounded-xl px-3 py-2 text-sm text-muted-foreground animate-pulse">
              Thinking…
            </div>
          </div>
        )}
      </div>

      {/* Voice error */}
      {voiceError && (
        <p className="px-4 py-1.5 text-xs text-destructive border-t border-border">{voiceError}</p>
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
          title={isRecording ? "Stop recording" : "Start voice input"}
          className={[
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border transition-colors",
            isRecording
              ? "border-red-500 bg-red-500/10 text-red-600 animate-pulse"
              : isTranscribing
                ? "border-amber-500 bg-amber-500/10 text-amber-600"
                : "border-border text-muted-foreground hover:bg-muted",
          ].join(" ")}
        >
          {isRecording ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        </button>

        <Input
          value={input}
          onChange={handleInputChange}
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
