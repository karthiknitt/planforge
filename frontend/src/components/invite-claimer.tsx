"use client";

import { useEffect } from "react";

const CLAIMED_FLAG = "invite-claimed";

/**
 * Fire-and-forget: claims any pending team invites addressed to the current
 * session's verified email, once per browser session. Renders nothing.
 *
 * The claim itself is authorized server-side purely from the signed internal
 * auth token's `email` claim (see /api/backend/teams/claim) — this component
 * never sends an email, it just triggers the check.
 */
export function InviteClaimer() {
  useEffect(() => {
    if (sessionStorage.getItem(CLAIMED_FLAG) === "1") {
      return;
    }
    sessionStorage.setItem(CLAIMED_FLAG, "1");
    fetch("/api/backend/teams/claim", { method: "POST" }).catch(() => {
      // Best-effort — a failed claim attempt is not user-facing; the next
      // session (or a page refresh after sessionStorage clears) will retry.
    });
  }, []);

  return null;
}
