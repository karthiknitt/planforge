"use client";

import * as React from "react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { LogoId } from "@/lib/models";
import { cn } from "@/lib/utils";

// ── Context ──────────────────────────────────────────────────────────────────

interface ModelSelectorContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const ModelSelectorContext = React.createContext<ModelSelectorContextValue>({
  open: false,
  onOpenChange: () => {},
});

// ── Root ──────────────────────────────────────────────────────────────────────

interface ModelSelectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

function ModelSelector({ open, onOpenChange, children }: ModelSelectorProps) {
  return (
    <ModelSelectorContext.Provider value={{ open, onOpenChange }}>
      <Popover open={open} onOpenChange={onOpenChange}>
        {children}
      </Popover>
    </ModelSelectorContext.Provider>
  );
}

// ── Trigger ───────────────────────────────────────────────────────────────────

function ModelSelectorTrigger({
  asChild,
  children,
}: {
  asChild?: boolean;
  children: React.ReactNode;
}) {
  return <PopoverTrigger asChild={asChild}>{children}</PopoverTrigger>;
}

// ── Content ───────────────────────────────────────────────────────────────────

function ModelSelectorContent({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <PopoverContent
      className={cn("w-64 p-0", className)}
      align="start"
      side="bottom"
      sideOffset={4}
    >
      <Command>{children}</Command>
    </PopoverContent>
  );
}

// ── Sub-components delegated to Command primitives ────────────────────────────

function ModelSelectorInput(props: React.ComponentProps<typeof CommandInput>) {
  return <CommandInput {...props} />;
}

function ModelSelectorList(props: React.ComponentProps<typeof CommandList>) {
  return <CommandList {...props} />;
}

function ModelSelectorEmpty(props: React.ComponentProps<typeof CommandEmpty>) {
  return <CommandEmpty {...props} />;
}

function ModelSelectorGroup({
  heading,
  children,
}: {
  heading?: string;
  children: React.ReactNode;
}) {
  return <CommandGroup heading={heading}>{children}</CommandGroup>;
}

function ModelSelectorSeparator(props: React.ComponentProps<typeof CommandSeparator>) {
  return <CommandSeparator {...props} />;
}

interface ModelSelectorItemProps extends React.ComponentProps<typeof CommandItem> {
  value: string;
  onSelect?: (value: string) => void;
  children: React.ReactNode;
}

function ModelSelectorItem({
  value,
  onSelect,
  children,
  className,
  ...props
}: ModelSelectorItemProps) {
  return (
    <CommandItem
      value={value}
      onSelect={onSelect}
      className={cn("flex items-center gap-2 cursor-pointer", className)}
      {...props}
    >
      {children}
    </CommandItem>
  );
}

function ModelSelectorName({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <span className={cn("flex-1 text-sm font-medium", className)}>{children}</span>;
}

// ── Provider logos ────────────────────────────────────────────────────────────

const AnthropicLogo = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="shrink-0"
    aria-hidden="true"
  >
    <path
      d="M13.827 3.52h3.603L24 20h-3.603l-6.57-16.48zm-7.258 0h3.767L16.906 20h-3.674l-1.343-3.461H5.017L3.674 20H0L6.569 3.52zm4.132 9.959L8.453 7.908l-2.195 5.571h4.443z"
      fill="currentColor"
    />
  </svg>
);

const OpenAILogo = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="shrink-0"
    aria-hidden="true"
  >
    <path
      d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0L4.01 14.2A4.504 4.504 0 0 1 2.34 7.896zm16.597 3.855l-5.843-3.372L15.114 7.2a.076.076 0 0 1 .071 0l4.816 2.806a4.5 4.5 0 0 1-.68 8.105v-5.678a.786.786 0 0 0-.384-.682zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.816-2.801a4.5 4.5 0 0 1 6.675 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"
      fill="currentColor"
    />
  </svg>
);

const GoogleLogo = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="shrink-0"
    aria-hidden="true"
  >
    <path
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      fill="#4285F4"
    />
    <path
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      fill="#34A853"
    />
    <path
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      fill="#FBBC05"
    />
    <path
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      fill="#EA4335"
    />
  </svg>
);

const OpenRouterLogo = () => (
  <svg
    width="16"
    height="16"
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="shrink-0"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
    <path
      d="M8 12h8M14 9l3 3-3 3"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

function ModelSelectorLogo({
  logoId,
  className,
}: {
  logoId: LogoId;
  className?: string;
}) {
  const logo = {
    anthropic: <AnthropicLogo />,
    openai: <OpenAILogo />,
    google: <GoogleLogo />,
    openrouter: <OpenRouterLogo />,
  }[logoId] ?? <OpenRouterLogo />;

  return <span className={cn("text-muted-foreground", className)}>{logo}</span>;
}

export {
  ModelSelector,
  ModelSelectorTrigger,
  ModelSelectorContent,
  ModelSelectorInput,
  ModelSelectorList,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorSeparator,
  ModelSelectorItem,
  ModelSelectorName,
  ModelSelectorLogo,
};
