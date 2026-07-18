"use client";

import { RouteError } from "@/components/route-error";

export default function AccountError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError
      error={error}
      reset={reset}
      message="Could not load your account. Please try again."
    />
  );
}
