/**
 * Turns a rejected TanStack mutation OR query error into a message safe to
 * show an operator.
 *
 * This exists because nothing else in the app extracted one: every product
 * mutation hook threw a raw error and nothing downstream read it, so a
 * rejected save produced no visible feedback at all (see
 * `stores/mutationErrorStore.ts` and `lib/queryClient.ts` for the rest of the
 * wiring). The query half shares this same function — `DataTableError`
 * (`components/kit/DataTableStates.tsx`) calls the `describeQueryError`
 * export below, which is this function under a name honest about that call
 * site. Nothing about the logic is mutation-specific: an axios error's
 * provenance (upstream-forwarded vs portal-native) does not depend on which
 * kind of request produced it, so one implementation covers both rather than
 * two copies of the same denylist-vs-provenance reasoning drifting apart.
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

/**
 * The query counterpart of {@link GENERIC_MUTATION_ERROR_MESSAGE}. Not the
 * same string: "could not be saved" is a false claim about a failed GET —
 * nothing was being saved — so the two call sites need their own generic
 * text even though they share every byte of the provenance logic that
 * decides WHEN to fall back to it.
 */
export const GENERIC_QUERY_ERROR_MESSAGE =
  "The data could not be loaded. Try again, or contact support if this continues.";

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
 * Extracts a message from a rejected mutation or query's error, safe to
 * show an operator. `describeMutationError` and `describeQueryError` below
 * are both thin wrappers around this — the only thing that differs between
 * a failed save and a failed load is which generic sentence to fall back
 * to, never the provenance decision itself.
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
 * guard every product mutation hook throws, or a decode failure like
 * `envelopeList` throws for a query) is client-generated, never proxied, so
 * it is in the TRUSTED category — eligible to be shown verbatim, the same
 * as a portal-native response. "Trusted" still means "checked with
 * `isDisplayable`", not "shown unconditionally": an empty or pathologically
 * long `Error.message` still falls back to the generic message, same as an
 * untrustworthy candidate would. Anything else — network failures with no
 * response, or an unrecognised body shape — also falls back rather than
 * guessing.
 */
function describeRequestError(error: unknown, genericMessage: string): string {
  if (isAxiosError(error)) {
    if (isUpstreamResponse(error.response?.headers)) {
      return genericMessage;
    }
    const candidate = candidateFromResponseBody(error.response?.data);
    if (candidate && isDisplayable(candidate)) return candidate;
    return genericMessage;
  }

  if (error instanceof Error && isDisplayable(error.message)) {
    return error.message;
  }

  return genericMessage;
}

/** Call site: a rejected `useMutation`. Fed to `MutationCache.onError`. */
export function describeMutationError(error: unknown): string {
  return describeRequestError(error, GENERIC_MUTATION_ERROR_MESSAGE);
}

/** Call site: a failed `useQuery` (or query-shaped) list/detail fetch. */
export function describeQueryError(error: unknown): string {
  return describeRequestError(error, GENERIC_QUERY_ERROR_MESSAGE);
}

/** Shown for an operation-failure reason too long to trust — see below. */
export const GENERIC_OPERATION_ERROR_MESSAGE =
  "This operation failed. Try again, or contact support if this continues.";

/**
 * Sanitizes an `Operation.error` field
 * (`services/portal-api/app/adapters/base.py`) for display in an
 * operations panel.
 *
 * This is deliberately NOT `describeRequestError` under another name, and
 * cannot reuse its provenance check: that function decides safety from
 * whether the AXIOS RESPONSE carries `UPSTREAM_RESPONSE_HEADER` — a
 * transport-level marker on a REJECTED request. An operation's `error` is a
 * plain string field inside an already-successful, schema-validated 200
 * response (`OperationView`); there is no header to inspect, and by the
 * dataclass's own contract (`Operation.error`'s doc comment: "the product's
 * reason") the field is ALWAYS product-derived when present — there is no
 * "portal-native" case to trust the way a validation message is trusted.
 *
 * What still applies is the length guard `isDisplayable` already uses: a
 * short, structured reason (`"nest.migrate.source_unreachable"`) is exactly
 * the kind of thing a product is expected to report and is safe to show,
 * while a long one is the shape of a raw exception dump — see
 * `adapters/transport.py`'s `error=str(e)`, which stringifies a connection
 * failure complete with hostname and port. The cap catches that dump
 * without needing to enumerate what a leak looks like, the same lesson
 * `describeRequestError`'s own history already taught (see its doc
 * comment above).
 */
export function describeOperationError(
  error: string | null | undefined,
): string | null {
  if (error == null) return null;
  return isDisplayable(error) ? error : GENERIC_OPERATION_ERROR_MESSAGE;
}
