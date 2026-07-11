function getStatusCode(err: unknown): number | undefined {
  if (err && typeof err === "object" && "statusCode" in err) {
    const statusCode = (err as { statusCode?: unknown }).statusCode;
    if (typeof statusCode === "number") {
      return statusCode;
    }
  }
  return undefined;
}

function getMessage(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === "string") {
    return err;
  }
  return "";
}

const REFUSAL_PATTERN = /\brefus(al|ed)\b|content.?polic|declined for safety|safety reasons/i;

const NOT_FOUND_PATTERN = /not_found_error|model:.*not found|model_not_found|no such model/i;
const AUTH_PATTERN = /unauthorized|invalid.?(x-)?api.?key/i;
const BILLING_PATTERN = /billing|balance|insufficient|credit|payment/i;
const RATE_LIMIT_PATTERN = /rate.?limit/i;
const NETWORK_PATTERN = /fetch failed|econnrefused|econnreset|enotfound|network/i;
const SERVER_ERROR_PATTERN = /\boverloaded\b|internal server error|service unavailable/i;

const FALLBACK_STATUS_CODES = new Set([401, 402, 404, 429]);

/** Whether a provider error is worth retrying on the next configured provider. */
export function shouldFallback(error: unknown): boolean {
  const message = getMessage(error);
  if (REFUSAL_PATTERN.test(message)) {
    return false;
  }

  const statusCode = getStatusCode(error);
  if (statusCode !== undefined) {
    return statusCode >= 500 || FALLBACK_STATUS_CODES.has(statusCode);
  }

  return (
    NOT_FOUND_PATTERN.test(message) ||
    AUTH_PATTERN.test(message) ||
    BILLING_PATTERN.test(message) ||
    RATE_LIMIT_PATTERN.test(message) ||
    NETWORK_PATTERN.test(message) ||
    SERVER_ERROR_PATTERN.test(message)
  );
}

/** Short, human-readable summary of a provider failure for the end-of-chain error message. */
export function describeProviderError(error: unknown, providerName: string): string {
  const message = getMessage(error);
  const statusCode = getStatusCode(error);

  if (statusCode === 404 || NOT_FOUND_PATTERN.test(message)) {
    return `${providerName}: model not found`;
  }
  if (statusCode === 401 || AUTH_PATTERN.test(message)) {
    return `${providerName}: invalid API key`;
  }
  if (statusCode === 402 || BILLING_PATTERN.test(message)) {
    return `${providerName}: billing/insufficient credit`;
  }
  if (statusCode === 429 || RATE_LIMIT_PATTERN.test(message)) {
    return `${providerName}: rate limited`;
  }
  if (NETWORK_PATTERN.test(message)) {
    return `${providerName}: network/connection error`;
  }
  if ((statusCode !== undefined && statusCode >= 500) || SERVER_ERROR_PATTERN.test(message)) {
    return `${providerName}: service unavailable`;
  }

  const summary = message || "unknown error";
  return `${providerName}: ${summary.slice(0, 120)}`;
}
