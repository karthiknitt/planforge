"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ApprovalStatus = "approved" | "changes_requested" | "pending" | null;

interface LayoutOption {
  id: string;
  name: string;
  score?: number;
}

interface ApprovalActionsProps {
  token: string;
  layouts: LayoutOption[];
  initialStatus: ApprovalStatus;
  initialNote: string | null;
  initialSelectedLayouts: string[] | null;
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
  layouts,
  initialStatus,
  initialNote,
  initialSelectedLayouts,
  initialUpdatedAt,
}: ApprovalActionsProps) {
  const [status, setStatus] = useState<ApprovalStatus>(initialStatus);
  const [note, setNote] = useState<string | null>(initialNote);
  const [selectedLayouts, setSelectedLayouts] = useState<string[]>(initialSelectedLayouts ?? []);
  const [updatedAt, setUpdatedAt] = useState<string | null>(initialUpdatedAt);
  const [loading, setLoading] = useState<"approve" | "changes" | null>(null);
  const [showNoteInput, setShowNoteInput] = useState(false);
  const [noteInput, setNoteInput] = useState("");
  const [error, setError] = useState("");

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";

  function toggleLayout(id: string) {
    setSelectedLayouts((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handleApprove() {
    if (selectedLayouts.length === 0) {
      setError("Please select at least one layout to approve.");
      return;
    }
    setLoading("approve");
    setError("");
    try {
      const res = await fetch(`${apiBase}/api/share/${token}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_layout_ids: selectedLayouts }),
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

  // ── Status banners ───────────────────────────────────────────────────────────

  if (status === "approved") {
    const approvedNames = layouts
      .filter((l) => selectedLayouts.includes(l.id))
      .map((l) => `Layout ${l.id} — ${l.name}`);

    return (
      <div className="rounded-xl border border-green-500/40 bg-green-500/10 px-5 py-4 flex items-start gap-3">
        <span className="text-green-600 text-lg mt-0.5">✅</span>
        <div className="flex flex-col gap-1">
          <p className="font-semibold text-green-700 dark:text-green-400">You approved this plan</p>
          {approvedNames.length > 0 && (
            <ul className="text-sm text-green-700 dark:text-green-400 list-disc list-inside">
              {approvedNames.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          {updatedAt && <p className="text-sm text-muted-foreground">on {formatDate(updatedAt)}</p>}
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

  // ── Action panel (null or "pending") ────────────────────────────────────────

  return (
    <div className="rounded-xl border border-border bg-card px-5 py-5 flex flex-col gap-5">
      <div>
        <h2 className="font-semibold text-foreground">Review this plan</h2>
        <p className="text-sm text-muted-foreground mt-0.5">
          Select the layout(s) you prefer, then approve or request changes.
        </p>
      </div>

      {/* Layout selector */}
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Select layout(s) to approve
        </p>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          {layouts.map((l) => {
            const selected = selectedLayouts.includes(l.id);
            return (
              <button
                key={l.id}
                type="button"
                onClick={() => toggleLayout(l.id)}
                className={[
                  "flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
                  "min-w-[180px] flex-1 sm:flex-none",
                  selected
                    ? "border-green-500 bg-green-500/10 text-green-700 dark:text-green-400"
                    : "border-border hover:border-ring/60 hover:bg-muted/50",
                ].join(" ")}
              >
                {/* Checkbox indicator */}
                <span
                  className={[
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded border-2 transition-colors",
                    selected
                      ? "border-green-500 bg-green-500 text-white"
                      : "border-muted-foreground/40",
                  ].join(" ")}
                >
                  {selected && (
                    <svg viewBox="0 0 12 10" className="h-3 w-3 fill-current">
                      <path
                        d="M1 5l3 4L11 1"
                        stroke="currentColor"
                        strokeWidth="2"
                        fill="none"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </span>
                <div>
                  <p className="text-sm font-medium">
                    Layout {l.id} — {l.name}
                  </p>
                  {l.score !== undefined && (
                    <p className="text-xs text-muted-foreground">Score {l.score.toFixed(0)}/100</p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
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
            disabled={loading !== null || selectedLayouts.length === 0}
            className="bg-green-600 hover:bg-green-700 text-white disabled:opacity-40"
          >
            {loading === "approve"
              ? "Approving…"
              : selectedLayouts.length === 0
                ? "✅ Approve (select a layout first)"
                : `✅ Approve ${selectedLayouts.length === 1 ? "Layout " + selectedLayouts[0] : `${selectedLayouts.length} layouts`}`}
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
