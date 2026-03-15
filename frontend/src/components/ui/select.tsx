import type * as React from "react";
import { cn } from "@/lib/utils";

function Select({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(
        "flex h-9 w-full appearance-none rounded-md border px-3 py-1 text-sm outline-none",
        "border-input dark:border-input dark:bg-input/20 dark:text-foreground",
        "bg-background text-foreground placeholder:text-muted-foreground",
        "transition-[border-color,box-shadow,background-color] duration-200",
        "hover:border-ring/60 hover:dark:border-ring/50",
        "focus-visible:border-ring focus-visible:ring-ring/40 focus-visible:ring-[3px] focus-visible:dark:bg-input/30",
        "disabled:cursor-not-allowed disabled:opacity-40",
        className
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export { Select };
