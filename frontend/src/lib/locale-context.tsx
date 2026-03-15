"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import en from "../../messages/en.json";
import hi from "../../messages/hi.json";
import ta from "../../messages/ta.json";

export type Locale = "en" | "ta" | "hi";

// Nested key access: t('nav.dashboard') → string
type Messages = typeof en;

// Flatten nested object keys with dot notation
type DotPaths<T, Prefix extends string = ""> = {
  [K in keyof T]: T[K] extends Record<string, string>
    ? `${Prefix}${Prefix extends "" ? "" : "."}${K & string}.${keyof T[K] & string}`
    : `${Prefix}${Prefix extends "" ? "" : "."}${K & string}`;
}[keyof T];

export type TranslationKey = DotPaths<Messages>;

const MESSAGES: Record<Locale, Messages> = { en, ta, hi };

const LOCALE_COOKIE = "pf_locale";

function getInitialLocale(): Locale {
  if (typeof document === "undefined") return "en";
  const cookie = document.cookie.split("; ").find((row) => row.startsWith(`${LOCALE_COOKIE}=`));
  if (cookie) {
    const val = cookie.split("=")[1] as Locale;
    if (val === "en" || val === "ta" || val === "hi") return val;
  }
  return "en";
}

function setLocaleCookie(locale: Locale) {
  document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;
}

interface LocaleContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: TranslationKey) => string;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");

  useEffect(() => {
    setLocaleState(getInitialLocale());
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    setLocaleCookie(next);
  }, []);

  const t = useCallback(
    (key: TranslationKey): string => {
      const parts = key.split(".");
      // biome-ignore lint/suspicious/noExplicitAny: nested traversal requires any
      let cur: any = MESSAGES[locale];
      for (const part of parts) {
        if (cur == null) break;
        cur = cur[part];
      }
      if (typeof cur === "string") return cur;
      // Fallback to English
      // biome-ignore lint/suspicious/noExplicitAny: nested traversal requires any
      let fallback: any = MESSAGES.en;
      for (const part of parts) {
        if (fallback == null) break;
        fallback = fallback[part];
      }
      return typeof fallback === "string" ? fallback : key;
    },
    [locale]
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

// Room name lookup map for SVG (non-React-tree usage)
export const ROOM_NAMES: Record<Locale, Record<string, string>> = {
  en: en.rooms as Record<string, string>,
  ta: ta.rooms as Record<string, string>,
  hi: hi.rooms as Record<string, string>,
};
