"use client";

import { RouteError } from "@/components/route-error";

export default function TermsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteError error={error} reset={reset} message="Could not load this page. Please try again." />
  );
}
