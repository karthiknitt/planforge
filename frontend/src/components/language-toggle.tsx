"use client";

import { type Locale, useLocale } from "@/lib/locale-context";

const LOCALES: { value: Locale; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "ta", label: "தமிழ்" },
  { value: "hi", label: "हिं" },
];

export function LanguageToggle() {
  const { locale, setLocale } = useLocale();

  return (
    <div className="flex items-center gap-0.5 rounded-lg border border-border/60 bg-muted/40 p-0.5">
      {LOCALES.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          onClick={() => setLocale(value)}
          className={[
            "rounded-md px-2 py-1 text-xs font-medium transition-colors",
            locale === value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          ].join(" ")}
          aria-pressed={locale === value}
          aria-label={`Switch to ${label}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
