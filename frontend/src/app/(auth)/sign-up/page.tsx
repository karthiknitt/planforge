"use client";

import { Building2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signUp } from "@/lib/auth-client";

export default function SignUpPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const { error } = await signUp.email({ name, email, password });

    if (error) {
      setError(error.message ?? "Could not create account. Please try again.");
      setLoading(false);
      return;
    }

    router.push("/dashboard");
  }

  return (
    <div className="flex flex-col">
      {/* Mobile-only logo — hidden when left panel is visible */}
      <div className="flex items-center gap-2.5 mb-10 lg:hidden">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-orange-500 to-amber-600 shadow-lg shadow-orange-500/20">
          <Building2 className="h-4 w-4 text-white" />
        </div>
        <span
          className="text-xl font-bold tracking-tight"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Plan<span className="text-[#f97316]">Forge</span>
        </span>
      </div>

      {/* Heading */}
      <div className="animate-fade-up mb-8">
        <h1
          className="text-2xl font-black text-foreground mb-1.5"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Create your account
        </h1>
        <p className="text-sm text-muted-foreground">Free to start. No credit card required.</p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-5 animate-fade-up delay-100">
        <div className="flex flex-col gap-2">
          <Label
            htmlFor="name"
            className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest"
          >
            Full name
          </Label>
          <Input
            id="name"
            type="text"
            placeholder="Ravi Kumar"
            autoComplete="name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-11 bg-card/80 border-border/70 focus-visible:ring-[#f97316]/30 focus-visible:border-[#f97316]/50"
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label
            htmlFor="email"
            className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest"
          >
            Email
          </Label>
          <Input
            id="email"
            type="email"
            placeholder="you@example.com"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 bg-card/80 border-border/70 focus-visible:ring-[#f97316]/30 focus-visible:border-[#f97316]/50"
          />
        </div>

        <div className="flex flex-col gap-2">
          <Label
            htmlFor="password"
            className="text-[11px] font-semibold text-muted-foreground uppercase tracking-widest"
          >
            Password
          </Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 bg-card/80 border-border/70 focus-visible:ring-[#f97316]/30 focus-visible:border-[#f97316]/50"
          />
        </div>

        {error && (
          <p className="rounded-lg border border-destructive/25 bg-destructive/8 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <Button
          type="submit"
          disabled={loading}
          className="mt-1 h-11 w-full bg-[#f97316] hover:bg-[#ea6c0a] text-white font-bold text-sm btn-shine shadow-lg shadow-orange-500/15"
        >
          {loading ? "Creating account\u2026" : "Create account"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground animate-fade-up delay-200">
        Already have an account?{" "}
        <Link
          href="/sign-in"
          className="text-[#f97316] font-semibold hover:underline underline-offset-4"
        >
          Sign in &rarr;
        </Link>
      </p>
    </div>
  );
}
