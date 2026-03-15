import type * as React from "react";

import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "file:text-foreground placeholder:text-muted-foreground/70 selection:bg-primary selection:text-primary-foreground",
        "flex h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-base outline-none",
        "border-input dark:border-input dark:bg-input/20 dark:text-foreground",
        "transition-[border-color,box-shadow,background-color] duration-200",
        "hover:border-ring/60 hover:dark:border-ring/50",
        "focus-visible:border-ring focus-visible:ring-ring/40 focus-visible:ring-[3px] focus-visible:dark:bg-input/30",
        "file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-40 md:text-sm",
        "aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive",
        className
      )}
      {...props}
    />
  );
}

export { Input };
