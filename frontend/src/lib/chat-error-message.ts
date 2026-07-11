export interface FriendlyChatError {
  title: string;
  detail?: string;
}

function getStatusCode(error: unknown): number | undefined {
  if (error && typeof error === "object" && "statusCode" in error) {
    const statusCode = (error as { statusCode?: unknown }).statusCode;
    if (typeof statusCode === "number") {
      return statusCode;
    }
  }
  return undefined;
}

function getName(error: unknown): string {
  if (error && typeof error === "object" && "name" in error) {
    const name = (error as { name?: unknown }).name;
    if (typeof name === "string") {
      return name;
    }
  }
  return "";
}

function getMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "";
}

const AUTH_PATTERN = /\b401\b|unauthorized/i;
const FORBIDDEN_PATTERN = /\b403\b|forbidden|pro plan|pro.tier|requires pro/i;
const TIMEOUT_PATTERN = /\btimed out\b|\btimeout\b|\baborted\b|etimedout/i;

/** Turns a useChat/agent-route error into a short, human-readable banner message. */
export function friendlyChatError(error: unknown): FriendlyChatError {
  const statusCode = getStatusCode(error);
  const name = getName(error);
  const message = getMessage(error);

  if (statusCode === 401 || AUTH_PATTERN.test(message)) {
    return { title: "Session expired", detail: "Sign in again" };
  }
  if (statusCode === 403 || FORBIDDEN_PATTERN.test(message)) {
    return { title: "Pro plan required for agent chat" };
  }
  if (name === "AbortError" || statusCode === 408 || TIMEOUT_PATTERN.test(message)) {
    return { title: "Backend timed out — it may be cold-starting; try again in ~30s" };
  }

  return message
    ? { title: "Something went wrong", detail: message }
    : { title: "Something went wrong" };
}
