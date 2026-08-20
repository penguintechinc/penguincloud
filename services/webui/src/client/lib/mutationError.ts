/**
 * Turns a rejected TanStack mutation's error into a message safe to show an
 * operator.
 *
 * This exists because nothing else in the app extracted one: every product
 * mutation hook threw a raw error and nothing downstream read it, so a
 * rejected save produced no visible feedback at all (see
 * `stores/mutationErrorStore.ts` and `lib/queryClient.ts` for the rest of the
 * wiring).
 *
 * Once a message DOES get shown, an earlier version of this function decided
 * whether it was safe by pattern-matching the STRING — a denylist of things
 * that "look like" a hostname, an IP, or a URL. A reviewer broke that in one
 * pass with strings the patterns never anticipated: a dotless in-cluster
 * service name (`gough-api-primary:8080`), an IPv6 address, a bare
 * filesystem path, a raw `sk_live_...` credential — none contain a scheme, a
 * dotted hostname, or an IPv4 octet, so all five rendered verbatim. A
 * denylist over content shape can only ever cover shapes someone thought of;
 * the next unanticipated one always wins.
 *
 * This version decides from PROVENANCE instead of content: a portal-native
 * body (auth failures, `@validate_response` validation errors, `_deny()`
 * refusals) is trusted and shown verbatim; anything the backend has marked
 * as containing product-derived text is ALWAYS replaced with a generic
 * message, regardless of what it contains. The marker is
 * `UPSTREAM_RESPONSE_HEADER`, defined once in
 * `services/portal-api/app/adapters/base.py` — read that constant's own doc
 * comment for the CURRENT, authoritative list of writers, not this one.
 *
 * Naming a single writer here is exactly the mistake that let one of them
 * ship unmarked: an earlier version of this comment named
 * `services/portal-api/app/proxy.py` as "the" writer, because at the time it
 * was the only one — and that framing is what let
 * `app.product_access.adapter_failure` (the typed portal routes' error
 * path, entirely separate from the proxy) go unmarked in the same round
 * that introduced this mechanism. A reader who believes "the proxy handles
 * this" has no reason to go looking for a second writer, a third, or a
 * fourth. There are four as of this writing (`adapters/base.py` enumerates
 * them); do not copy that count here either — go read the source of truth.
 */
import { isAxiosError } from "axios";

/** Shown for every upstream-forwarded body, and any body this can't read. */
export const GENERIC_MUTATION_ERROR_MESSAGE =
  "The request could not be saved. Try again, or contact support if this continues.";

/** Longer than this reads as a dumped body, not a message meant for a user. */
const MAX_MESSAGE_LENGTH = 200;

/**
 * Matches `UPSTREAM_RESPONSE_HEADER`, defined once in
 * `services/portal-api/app/adapters/base.py` (not owned by any single
 * route file — see that constant's doc comment for the current list of
 * writers). Axios normalises response header names to lowercase.
 */
const UPSTREAM_RESPONSE_HEADER = "x-portal-upstream-response";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** True when the response carries the proxy's upstream-provenance marker. */
function isUpstreamResponse(headers: unknown): boolean {
  return isRecord(headers) && Boolean(headers[UPSTREAM_RESPONSE_HEADER]);
}

/** Reads the first plausible message field out of an error response body. */
function candidateFromResponseBody(data: unknown): string | null {
  if (!isRecord(data)) return null;
  if (typeof data.error === "string") return data.error;
  if (typeof data.message === "string") return data.message;
  return null;
}

/**
 * True when `text` is short and non-empty enough to render as a toast.
 *
 * A length cap only, now that provenance (not content) decides safety — a
 * portal validation message ("config.timeout must be a positive integer")
 * is trusted regardless of shape; this just keeps a pathologically long one
 * from being dumped into a fixed-width banner.
 */
function isDisplayable(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.length > 0 && trimmed.length <= MAX_MESSAGE_LENGTH;
}

/**
 * Extracts a message from a rejected mutation's error, safe to show an
 * operator.
 *
 * Axios errors are read from `response.data` — the shape every portal route
 * uses (`{"error": "..."}`). A response ANY backend writer marked as
 * upstream-forwarded (see `UPSTREAM_RESPONSE_HEADER`'s doc comment in
 * `adapters/base.py` for the current list) is ALWAYS replaced with the
 * generic message, before its body is even inspected — that is the
 * provenance check this function exists to make. A portal-native response
 * (no marker) is trusted and shown verbatim, length permitting.
 *
 * A plain `Error` (e.g. the "No <Product> connection for the active tenant"
 * guard every product mutation hook throws) is client-generated, never
 * proxied, so it is in the TRUSTED category — eligible to be shown
 * verbatim, the same as a portal-native response. "Trusted" still means
 * "checked with `isDisplayable`", not "shown unconditionally": an empty or
 * pathologically long `Error.message` still falls back to the generic
 * message below, same as an untrustworthy candidate would. Anything else —
 * network failures with no response, or an unrecognised body shape — also
 * falls back rather than guessing.
 */
export function describeMutationError(error: unknown): string {
  if (isAxiosError(error)) {
    if (isUpstreamResponse(error.response?.headers)) {
      return GENERIC_MUTATION_ERROR_MESSAGE;
    }
    const candidate = candidateFromResponseBody(error.response?.data);
    if (candidate && isDisplayable(candidate)) return candidate;
    return GENERIC_MUTATION_ERROR_MESSAGE;
  }

  if (error instanceof Error && isDisplayable(error.message)) {
    return error.message;
  }

  return GENERIC_MUTATION_ERROR_MESSAGE;
}
