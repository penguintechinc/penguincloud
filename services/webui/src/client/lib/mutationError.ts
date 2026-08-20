/**
 * Turns a rejected TanStack mutation's error into a message safe to show an
 * operator.
 *
 * This exists because nothing else in the app extracted one: every product
 * mutation hook threw a raw error and nothing downstream read it, so a
 * rejected save produced no visible feedback at all (see
 * `stores/mutationErrorStore.ts` and `lib/queryClient.ts` for the rest of the
 * wiring). Once a message DOES get shown, what it may contain matters — most
 * mutations reach a product through the portal's proxy
 * (`services/portal-api/app/proxy.py`), which forwards the upstream body
 * mostly verbatim. The proxy's own `_redact()` strips the credential it
 * injected outbound, but nothing strips a hostname, internal IP, or other
 * operational detail an upstream product happens to put in an error body —
 * that is exactly the class of thing this function refuses to display.
 */
import { isAxiosError } from "axios";

/** Shown whenever the real message is missing, too long, or looks unsafe. */
export const GENERIC_MUTATION_ERROR_MESSAGE =
  "The request could not be saved. Try again, or contact support if this continues.";

/** Longer than this reads as a dumped body, not a message meant for a user. */
const MAX_MESSAGE_LENGTH = 200;

/**
 * Substrings that disqualify a candidate message outright, rather than being
 * edited out of it. Any one of these means the text came from somewhere that
 * was not written for an end user, so partial cleanup would still be a guess.
 */
const LEAK_PATTERNS: RegExp[] = [
  /https?:\/\//i, // URL
  /\b(?:[a-z0-9-]+\.){1,}[a-z]{2,}\b/i, // dotted hostname, including a bare
  // "gough.local" (one dot). Deliberately over-inclusive: "e.g." and "v1.2"
  // don't match (a single trailing letter fails the {2,} tail), but this WILL
  // flag some legitimate two-word.pairs — the intended trade, since an
  // under-caught hostname is the failure this exists to prevent and an
  // over-caught one just falls back to the generic message.
  /\b\d{1,3}(?:\.\d{1,3}){3}\b/, // IPv4
  /\[REDACTED\]/, // the proxy already found something to strip; the rest of
  // the body is not more trustworthy for showing verbatim
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** True when `text` is short, non-empty, and matches none of the leak patterns. */
function looksSafeToShow(text: string): boolean {
  const trimmed = text.trim();
  if (trimmed.length === 0 || trimmed.length > MAX_MESSAGE_LENGTH) return false;
  return !LEAK_PATTERNS.some((pattern) => pattern.test(trimmed));
}

/** Reads the first plausible message field out of an upstream error body. */
function candidateFromResponseBody(data: unknown): string | null {
  if (!isRecord(data)) return null;
  if (typeof data.error === "string") return data.error;
  if (typeof data.message === "string") return data.message;
  return null;
}

/**
 * Extracts a short, sanitized message from a rejected mutation's error.
 *
 * Axios errors are read from `response.data` — the shape the portal API and
 * its proxy both use (`{"error": "..."}`). A plain `Error` (e.g. the
 * "No <Product> connection for the active tenant" guard every product
 * mutation hook throws) is client-generated, never proxied, so its message is
 * always safe to show as-is. Anything else — network failures with no
 * response, an unrecognised body shape, or a candidate that fails the safety
 * check — falls back to a generic message rather than guessing.
 */
export function describeMutationError(error: unknown): string {
  if (isAxiosError(error)) {
    const candidate = candidateFromResponseBody(error.response?.data);
    if (candidate && looksSafeToShow(candidate)) return candidate;
    return GENERIC_MUTATION_ERROR_MESSAGE;
  }

  if (error instanceof Error && looksSafeToShow(error.message)) {
    return error.message;
  }

  return GENERIC_MUTATION_ERROR_MESSAGE;
}
