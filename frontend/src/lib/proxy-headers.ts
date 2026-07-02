// Headers that must never be forwarded from a client request to the backend
// through the auth proxy — hop-by-hop headers, and anything the proxy itself
// controls or recalculates.
export const HEADER_BLOCKLIST = new Set([
  "host",
  "connection",
  "content-length",
  "cookie",
  "x-internal-auth", // the proxy mints its own; never trust one from the client
  "transfer-encoding",
  "te",
]);

export function forwardableHeaders(reqHeaders: Headers): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [key, value] of reqHeaders.entries()) {
    if (!HEADER_BLOCKLIST.has(key.toLowerCase())) {
      result[key] = value;
    }
  }
  if (!result["content-type"] && !result["Content-Type"]) {
    result["Content-Type"] = "application/json";
  }
  return result;
}
