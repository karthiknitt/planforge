"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import en from "../../messages/en.json";

export type Locale = "en" | "ta" | "hi";

// Nested key access: t('nav.dashboard') → string
export type Messages = typeof en;

// Flatten nested object keys with dot notation
type DotPaths<T, Prefix extends string = ""> = {
  [K in keyof T]: T[K] extends Record<string, string>
    ? `${Prefix}${Prefix extends "" ? "" : "."}${K & string}.${keyof T[K] & string}`
    : `${Prefix}${Prefix extends "" ? "" : "."}${K & string}`;
}[keyof T];

export type TranslationKey = DotPaths<Messages>;

const LOCALE_COOKIE = "pf_locale";

// "en" ships in the main bundle as the default/fallback; "ta"/"hi" are only
// fetched (and cached here) once a user actually switches to — or the
// server-read cookie says to start in — a non-English locale.
const dictionaryCache: Partial<Record<Locale, Messages>> = { en };
const pendingLoads: Partial<Record<Locale, Promise<Messages>>> = {};

// Exported for tests exercising the lazy-load state machine directly —
// rendering a hooks-based provider isn't set up in this repo's test harness
// (no @testing-library/react), so the loading/caching/dedup logic is
// verified at this level instead.
export function loadMessages(locale: Locale): Promise<Messages> {
  const cached = dictionaryCache[locale];
  if (cached) return Promise.resolve(cached);
  const pending = pendingLoads[locale];
  if (pending) return pending;

  const promise = (
    locale === "ta" ? import("../../messages/ta.json") : import("../../messages/hi.json")
  ).then((mod) => {
    const messages = mod.default as Messages;
    dictionaryCache[locale] = messages;
    return messages;
  });
  pendingLoads[locale] = promise;
  return promise;
}

export function isLocale(value: string | undefined): value is Locale {
  return value === "en" || value === "ta" || value === "hi";
}

function getInitialLocale(): Locale {
  if (typeof document === "undefined") return "en";
  const cookie = document.cookie.split("; ").find((row) => row.startsWith(`${LOCALE_COOKIE}=`));
  const val = cookie?.split("=")[1];
  return isLocale(val) ? val : "en";
}

function setLocaleCookie(locale: Locale) {
  // Cookie Store API is async and lacks Safari/Firefox support; this needs a
  // synchronous write on locale switch.
  // biome-ignore lint/suspicious/noDocumentCookie: sync write required, see above
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({
  children,
  initialLocale,
  initialMessages,
}: {
  children: React.ReactNode;
  initialLocale?: Locale;
  // Resolved server-side (see (app)/layout.tsx) so the FIRST render — the
  // one that produces the SSR HTML — already has the correct strings for a
  // non-English `initialLocale`. Without this, SSR would always render "en"
  // (the only dictionary statically bundled), since the lazy-load effect
  // below never runs during server rendering.
  initialMessages?: Messages;
}) {
  // Idempotent cache warm: mirrors what (app)/layout.tsx already resolved
  // server-side into this client module's own cache, so the mount effect
  // below sees it as already-loaded and skips a redundant re-fetch of the
  // same dictionary the server just sent down.
  if (initialLocale && initialMessages && !dictionaryCache[initialLocale]) {
    dictionaryCache[initialLocale] = initialMessages;
  }

  const [locale, setLocaleState] = useState<Locale>(initialLocale ?? "en");
  // Seeded from the server-resolved dictionary when available, otherwise
  // whatever's already cached for `locale` (always true for "en"); as a
  // last resort starts on "en" until the effect below resolves the real
  // dictionary — never an empty object.
  const [messages, setMessages] = useState<Messages>(
    initialMessages ?? dictionaryCache[locale] ?? en
  );

  // Defensive client-side fallback for the rare case a <LocaleProvider> is
  // mounted without a server-provided `initialLocale` (e.g. outside the root
  // layout). When the server already read the cookie, this is a no-op.
  // biome-ignore lint/correctness/useExhaustiveDependencies: mount-only reconciliation against the cookie; initialLocale intentionally not re-read
  useEffect(() => {
    if (initialLocale !== undefined) return;
    const clientLocale = getInitialLocale();
    setLocaleState((current) => (current === clientLocale ? current : clientLocale));
  }, []);

  // Fetches (and caches) the dictionary for whatever `locale` currently is.
  // Runs on mount too, so a server-provided non-English `initialLocale`
  // gets its real strings loaded immediately rather than staying on the
  // "en" fallback set above. Until it resolves, `messages` keeps showing
  // the previously-loaded locale's strings — never a blank Messages object.
  useEffect(() => {
    if (dictionaryCache[locale]) {
      setMessages(dictionaryCache[locale]);
      return;
    }
    let cancelled = false;
    loadMessages(locale).then((dict) => {
      if (!cancelled) setMessages(dict);
    });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    setLocaleCookie(next);
  }, []);

  const t = useCallback(
    (key: TranslationKey): string => {
      const parts = key.split(".");
      // biome-ignore lint/suspicious/noExplicitAny: nested traversal requires any
      let cur: any = messages;
      for (const part of parts) {
        if (cur == null) break;
        cur = cur[part];
      }
      if (typeof cur === "string") return cur;
      // Fallback to English
      // biome-ignore lint/suspicious/noExplicitAny: nested traversal requires any
      let fallback: any = en;
      for (const part of parts) {
        if (fallback == null) break;
        fallback = fallback[part];
      }
      return typeof fallback === "string" ? fallback : key;
    },
    [messages]
  );

  return (
    <LocaleContext.Provider value={{ locale, setLocale, t }}>{children}</LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextValue {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used inside <LocaleProvider>");
  return ctx;
}
