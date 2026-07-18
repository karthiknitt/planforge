"use client";

import { RouteError } from "@/components/route-error";

export default function SignInError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError error={error} reset={reset} message="Could not load sign in. Please try again." />
  );
}
