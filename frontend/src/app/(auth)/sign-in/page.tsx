"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signIn } from "@/lib/auth-client";
import { showErrorToast } from "@/lib/toast";

function SignInForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const template = searchParams.get("template");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const { error } = await signIn.email({ email, password });

    if (error) {
      const message = error.message ?? "Invalid email or password.";
      setError(message);
      showErrorToast(message);
      setLoading(false);
      return;
    }

    router.push(template ? `/projects/new?template=${template}` : "/dashboard");
  }

  return (
    <div className="flex flex-col">
      {/* Heading */}
      <div className="animate-fade-up mb-8">
        <h1
          className="text-2xl font-black text-foreground mb-1.5"
          style={{ fontFamily: "var(--font-display)" }}
        >
          Welcome back
        </h1>
        <p className="text-sm text-muted-foreground">Sign in to your account to continue.</p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-5 animate-fade-up delay-100">
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
            className="h-11 bg-card/80 border-border/70 focus-visible:ring-primary/30 focus-visible:border-primary/50"
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
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 bg-card/80 border-border/70 focus-visible:ring-primary/30 focus-visible:border-primary/50"
          />
        </div>

        {error && (
          <p
            role="alert"
            className="rounded-lg border border-destructive/25 bg-destructive/8 px-3 py-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}

        <Button
          type="submit"
          disabled={loading}
          className="mt-1 h-11 w-full bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-sm btn-shine shadow-lg shadow-primary/20"
        >
          {loading ? "Signing in\u2026" : "Sign in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground animate-fade-up delay-200">
        No account?{" "}
        <Link
          href={template ? `/sign-up?template=${template}` : "/sign-up"}
          className="text-primary font-semibold hover:underline underline-offset-4"
        >
          Sign up free &rarr;
        </Link>
      </p>
    </div>
  );
}

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignInForm />
    </Suspense>
  );
}
