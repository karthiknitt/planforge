"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { showErrorToast, showToast } from "@/lib/toast";

interface InviteMemberFormProps {
  teamId: number;
}

export function InviteMemberForm({ teamId }: InviteMemberFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;

    setLoading(true);
    setError(null);
    setSuccess(false);

    // Call the backend invite endpoint via the proxy (/api/team/invite)
    // The proxy mints X-Internal-Auth and forwards the request to the backend
    try {
      const res = await fetch(`/api/team/invite`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ teamId, email: email.trim(), role }),
      });

      if (!res.ok) {
        const data = (await res.json()) as { error?: string };
        throw new Error(data.error ?? "Failed to invite member");
      }

      setSuccess(true);
      setEmail("");
      showToast("success", "Invite recorded");
      router.refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong";
      setError(message);
      showErrorToast(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="invite-email" className="text-sm font-medium">
          Email Address
        </Label>
        <Input
          id="invite-email"
          type="email"
          placeholder="engineer@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="invite-role" className="text-sm font-medium">
          Role
        </Label>
        <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="member">Member</option>
          <option value="admin">Admin</option>
        </Select>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}
      {success && (
        <p className="text-xs text-green-600 dark:text-green-400">
          Invite recorded. Share the app link with your engineer manually.
        </p>
      )}

      <Button
        type="submit"
        disabled={loading || !email.trim()}
        className="bg-primary hover:bg-primary/90 text-primary-foreground font-bold"
      >
        {loading ? "Inviting…" : "Send Invite"}
      </Button>
    </form>
  );
}
