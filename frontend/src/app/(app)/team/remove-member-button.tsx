"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";

interface RemoveMemberButtonProps {
  teamId: number;
  targetUserId: string;
}

export function RemoveMemberButton({ teamId, targetUserId }: RemoveMemberButtonProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);

  async function handleRemove() {
    if (!confirm("Remove this member from the team?")) return;
    setLoading(true);

    try {
      const res = await fetch(`/api/team/members`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teamId, targetUserId }),
      });

      if (res.ok) router.refresh();
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handleRemove}
      disabled={loading}
      className="h-7 px-2 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
    >
      {loading ? "…" : "Remove"}
    </Button>
  );
}
