"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export function RouteError({
  error,
  reset,
  message = "Something went wrong. Please try again.",
  fullScreen = false,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  message?: string;
  fullScreen?: boolean;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div
      className={[
        "flex flex-col items-center justify-center gap-4 px-4 text-center",
        fullScreen ? "min-h-screen" : "min-h-[60vh]",
      ].join(" ")}
    >
      <h2 className="font-semibold text-xl">Something went wrong</h2>
      <p className="text-muted-foreground text-sm">{message}</p>
      <Button onClick={reset}>Try again</Button>
    </div>
  );
}
