// Pure locale type/guard, importable from Server Components and Route
// Handlers. locale-context.tsx is "use client" (React context/hooks) — any
// function exported from it becomes an unusable server-side throwing proxy
// when called outside a Client Component, even though it type-checks and
// builds fine. isLocale has no client-only dependency, so it lives here.

export type Locale = "en" | "ta" | "hi";

export function isLocale(value: string | undefined): value is Locale {
  return value === "en" || value === "ta" || value === "hi";
}
