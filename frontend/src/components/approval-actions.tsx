"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ApprovalStatus = "approved" | "changes_requested" | "pending" | null;

interface ApprovalActionsProps {
  token: string;
  initialStatus: ApprovalStatus;
  initialNote: string | null;
  initialUpdatedAt: string | null;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function ApprovalActions({
  token,
  initialStatus,
  initialNote,
  initialUpdatedAt,
}: ApprovalActionsProps) {
  const [status, setStatus] = useState<ApprovalStatus>(initialStatus);
  const [note, setNote] = useState<string | null>(initialNote);
  const [updatedAt, setUpdatedAt] = useState<string | null>(initialUpdatedAt);
  const [loading, setLoading] = useState<"approve" | "changes" | null>(null);
  const [showNoteInput, setShowNoteInput] = useState(false);
  const [noteInput, setNoteInput] = useState("");
  const [error, setError] = useState("");

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";

  async function handleApprove() {
    setLoading("approve");
    setError("");
    try {
      const res = await fetch(`${apiBase}/api/share/${token}/approve`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setStatus("approved");
      setNote(null);
      setUpdatedAt(new Date().toISOString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(null);
    }
  }

  async function handleRequestChanges() {
    setLoading("changes");
    setError("");
    try {
      const res = await fetch(`${apiBase}/api/share/${token}/request-changes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: noteInput }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setStatus("changes_requested");
      setNote(noteInput || null);
      setUpdatedAt(new Date().toISOString());
      setShowNoteInput(false);
      setNoteInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(null);
    }
  }

  // ── Status banners ──────────────────────────────────────────────────────────

  if (status === "approved") {
    return (
      <div className="rounded-xl border border-green-500/40 bg-green-500/10 px-5 py-4 flex items-start gap-3">
        <span className="text-green-600 text-lg mt-0.5">✅</span>
        <div>
          <p className="font-semibold text-green-700 dark:text-green-400">You approved this plan</p>
          {updatedAt && (
            <p className="text-sm text-muted-foreground mt-0.5">on {formatDate(updatedAt)}</p>
          )}
        </div>
      </div>
    );
  }

  if (status === "changes_requested") {
    return (
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-5 py-4 flex items-start gap-3">
        <span className="text-amber-600 text-lg mt-0.5">✏️</span>
        <div>
          <p className="font-semibold text-amber-700 dark:text-amber-400">Changes requested</p>
          {updatedAt && (
            <p className="text-sm text-muted-foreground mt-0.5">on {formatDate(updatedAt)}</p>
          )}
          {note && (
            <p className="mt-2 text-sm text-foreground border border-amber-400/40 bg-amber-50 dark:bg-amber-900/10 rounded-lg px-3 py-2">
              {note}
            </p>
          )}
        </div>
      </div>
    );
  }

  // ── Action buttons (null or "pending") ─────────────────────────────────────

  return (
    <div className="rounded-xl border border-border bg-card px-5 py-5 flex flex-col gap-4">
      <div>
        <h2 className="font-semibold text-foreground">Review this plan</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Let the engineer know if you approve or need changes.
        </p>
      </div>

      {error && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {showNoteInput ? (
        <div className="flex flex-col gap-3">
          <Textarea
            placeholder="Describe what changes you'd like (e.g. Move kitchen to south side)"
            value={noteInput}
            onChange={(e) => setNoteInput(e.target.value)}
            rows={3}
            className="resize-none"
          />
          <div className="flex gap-2">
            <Button
              onClick={handleRequestChanges}
              disabled={loading === "changes"}
              className="bg-amber-500 hover:bg-amber-600 text-white"
            >
              {loading === "changes" ? "Sending…" : "Send Request"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setShowNoteInput(false);
                setNoteInput("");
              }}
              disabled={loading === "changes"}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap gap-3">
          <Button
            onClick={handleApprove}
            disabled={loading !== null}
            className="bg-green-600 hover:bg-green-700 text-white"
          >
            {loading === "approve" ? "Approving…" : "✅ Approve this plan"}
          </Button>
          <Button
            variant="outline"
            onClick={() => setShowNoteInput(true)}
            disabled={loading !== null}
            className="border-amber-500/50 text-amber-700 dark:text-amber-400 hover:bg-amber-500/10"
          >
            ✏️ Request Changes
          </Button>
        </div>
      )}
    </div>
  );
}
