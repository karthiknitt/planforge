/**
 * Where to send an already-authenticated user who lands on an auth page
 * (`/sign-in` or `/sign-up`). Preserves a `?template=` param through the
 * redirect so the gallery's "Customize this plan" CTA doesn't drop it when
 * proxy.ts short-circuits straight past the auth pages.
 */
export function resolveAuthenticatedRedirect(searchParams: URLSearchParams): string {
  const template = searchParams.get("template");
  if (!template) return "/dashboard";
  return `/projects/new?template=${encodeURIComponent(template)}`;
}
