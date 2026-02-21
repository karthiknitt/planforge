"use client";

import { useCallback, useRef, useState } from "react";

type Status = "idle" | "recording" | "transcribing" | "error";

interface UseVoiceInputOptions {
  onTranscript: (text: string) => void;
}

export function useVoiceInput({ onTranscript }: UseVoiceInputOptions) {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const recorder = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        for (const t of stream.getTracks()) t.stop();
        setStatus("transcribing");
        try {
          const blob = new Blob(chunksRef.current, { type: mimeType });
          const form = new FormData();
          form.append("audio", blob, "recording.webm");

          const res = await fetch("/api/transcribe", { method: "POST", body: form });
          if (!res.ok) throw new Error("Transcription failed");
          const { text } = await res.json();
          if (text?.trim()) onTranscript(text.trim());
        } catch (err) {
          setError(err instanceof Error ? err.message : "Transcription failed");
          setStatus("error");
          return;
        }
        setStatus("idle");
      };

      mediaRef.current = recorder;
      recorder.start(100); // collect data every 100ms
      setStatus("recording");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone access denied");
      setStatus("error");
    }
  }, [onTranscript]);

  const stop = useCallback(() => {
    if (mediaRef.current?.state === "recording") {
      mediaRef.current.stop();
    }
  }, []);

  const toggle = useCallback(() => {
    if (status === "recording") stop();
    else if (status === "idle" || status === "error") start();
  }, [status, start, stop]);

  return { status, error, toggle };
}
