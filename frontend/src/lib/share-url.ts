/**
 * Pure helpers for building a public, non-login-walled share link and the
 * WhatsApp message/deep-link that wraps it. Kept dependency-free (no
 * `window`) so they can be unit tested and reused by both the Share dialog
 * and the WhatsApp share button.
 */

/** Joins an origin with the backend-provided `/share/{token}` path. */
export function buildShareUrl(origin: string, sharePath: string): string {
  return `${origin.replace(/\/$/, "")}${sharePath}`;
}

/** The message body sent to WhatsApp — always points at the public share URL. */
export function buildWhatsAppMessage(
  projectName: string,
  layoutId: string,
  shareUrl: string
): string {
  return `Check out this floor plan for ${projectName} (Layout ${layoutId}): ${shareUrl}`;
}

/** Wraps message text into a `wa.me` deep link. */
export function buildWhatsAppShareLink(text: string): string {
  return `https://wa.me/?text=${encodeURIComponent(text)}`;
}
