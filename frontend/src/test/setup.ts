/**
 * Shared bun:test preload (bunfig.toml [test].preload).
 *
 * bun's mock.module() registry is process-global with ESM live bindings:
 * when two test files each registered their OWN mock for "@/lib/auth", the
 * last registration silently won for BOTH files' routes, so tests passed in
 * isolation but failed in the full run. Register the mock exactly once here;
 * test files import and configure the shared getSessionMock.
 */
import { mock } from "bun:test";

export const getSessionMock = mock(async () => null as { user: { id: string } } | null);

mock.module("@/lib/auth", () => ({
  auth: { api: { getSession: getSessionMock } },
}));

mock.module("next/headers", () => ({
  headers: async () => new Headers(),
}));
