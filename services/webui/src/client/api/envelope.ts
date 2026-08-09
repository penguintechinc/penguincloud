/**
 * Reading a list out of a response envelope, without inventing an empty one.
 *
 * Why this is shared rather than a helper per module
 * ==================================================
 * `?? []` on a missing envelope key is a false statement to the operator, not a
 * default. The screen renders "no snapshots", "no operations", "no customers" —
 * as fact, with nothing anywhere reporting that the response was not the shape
 * the client was written against.
 *
 * That shipped for Nest (three of four collections decoded as permanently empty
 * behind "No snapshots have been taken from this resource") and the identical
 * pattern was still live in `goughOperations.ts` (`body.operations ?? []`,
 * `body.logs ?? []`) and `dashboard.ts` (`data.rollup ?? []`). One helper, so
 * the next product cannot re-decide it.
 *
 * Why an absent key cannot mean "none"
 * ====================================
 * Both producers name the key unconditionally:
 *
 * - the portal's own routes answer `@dataclass(slots=True, frozen=True)`
 *   response DTOs through `quart-schema`'s `validate_response`, and
 *   `OperationListResponse.operations` / `OperationLogsResponse.logs` /
 *   `RollupResponse.rollup` are all required fields — an empty page is
 *   `{"operations": []}`, never `{}`;
 * - Nest's list handlers build their key with an unconditional comprehension
 *   (`handlers/protection.py:26` and friends).
 *
 * So a missing key is a shape this client does not understand — a route that
 * 404'd into an error page, a proxy that returned the product's raw body, a
 * response schema that changed. Every one of those deserves the caller's error
 * branch, which each screen already renders ("Could not read …", with a retry).
 */

/**
 * Return `payload[key]` as a string, or throw explaining what arrived.
 *
 * The scalar counterpart of {@link envelopeList}, and it exists for the same
 * reason one key at a time: `payload.html ?? ""` renders a blank white iframe
 * with nothing anywhere reporting that the response was not the expected
 * shape. "Empty page" and "key renamed" are indistinguishable to the operator,
 * and the first is a plausible thing for a block page to be.
 *
 * @param payload - the decoded response body
 * @param key - the key the value is published under
 */
export function envelopeString(payload: unknown, key: string): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`no envelope object carrying "${key}"`);
  }
  const record = payload as Record<string, unknown>;
  if (!(key in record)) {
    throw new Error(
      `no "${key}" key (got ${JSON.stringify(Object.keys(record))}) — ` +
        `refusing to render it as blank`,
    );
  }
  const value = record[key];
  if (typeof value !== "string") {
    throw new Error(`non-string under "${key}"`);
  }
  return value;
}

/**
 * Return `payload[key]` as a list, or throw explaining what actually arrived.
 *
 * @param payload - the decoded response body
 * @param key - the envelope key this collection is published under
 */
export function envelopeList<T>(payload: unknown, key: string): T[] {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`no envelope object carrying "${key}"`);
  }
  const record = payload as Record<string, unknown>;
  if (!(key in record)) {
    throw new Error(
      `no "${key}" key (got ${JSON.stringify(Object.keys(record))}) — ` +
        `refusing to report it as empty`,
    );
  }
  const rows = record[key];
  if (!Array.isArray(rows)) {
    throw new Error(`non-list under "${key}"`);
  }
  return rows as T[];
}
