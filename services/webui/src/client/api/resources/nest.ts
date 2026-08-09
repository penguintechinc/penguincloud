/**
 * Nest READS, made through the portal PROXY.
 *
 * The proxy is the untrusted-input path — the caller supplies the path string
 * — so every path below is admitted by an explicit RouteRule in
 * `app/adapters/nest/routes.py`. That allowlist is GET-only by design, so this
 * module is reads only; writes live in `nestResources.ts` on typed portal
 * routes, and the two must not be reached for interchangeably.
 *
 * Paths come from `nestPaths.ts`, which `tests/api/test_nest_webui_paths.py`
 * pins against the adapter's own `tenant_path()` builder.
 */

import { proxyApi } from "./products";
import {
  NEST_COLLECTION_ENVELOPE_KEYS,
  NEST_COLLECTION_PATHS,
} from "./nestPaths";
import type {
  NestBillingResult,
  NestCostSummary,
  NestDatabase,
  NestSnapshot,
  NestUsageRecord,
} from "../../pages/products/nest/types";

/**
 * Pull a collection's rows out from under ITS OWN envelope key.
 *
 * Nest has no shared envelope — see `NEST_COLLECTION_ENVELOPE_KEYS`. Reading
 * `items` for every collection and returning `[]` when it was absent made
 * snapshots decode as permanently empty, which the Snapshots tab then stated
 * as fact ("No snapshots have been taken from this resource").
 *
 * So an absent key throws. Every Nest list handler builds its key
 * unconditionally, so an empty collection still arrives as `{"snapshots": []}`
 * — a missing key means the response is not the shape this client was written
 * against, and the only reading an operator can give `[]` is "there are none".
 * Mirrors `NestResponse.items` in `app/adapters/nest/responses.py`.
 */
function items<T>(payload: unknown, key: string): T[] {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`nest returned no collection envelope carrying "${key}"`);
  }
  const record = payload as Record<string, unknown>;
  if (!(key in record)) {
    throw new Error(
      `nest returned a collection with no "${key}" key (got ` +
        `${JSON.stringify(Object.keys(record))}) — refusing to report it as empty`,
    );
  }
  const rows = record[key];
  if (!Array.isArray(rows)) {
    throw new Error(`nest returned a non-list under "${key}"`);
  }
  return rows as T[];
}

/**
 * Unwrap Nest's cost envelope, distinguishing "unavailable" from "empty".
 *
 * The cost routes proxy to `nest-cost-calculator` and answer 503 with
 * `{status: "unavailable"}` when it is absent. The portal forwards that status,
 * so the axios call rejects — hence the caller catches and calls this with
 * `null`. Reporting `available: false` is what lets the screen say the
 * calculator is not deployed instead of showing a zeroed bill.
 */
function billing<T>(payload: unknown): NestBillingResult<T> {
  if (!payload || typeof payload !== "object") {
    return { available: false, data: null };
  }
  const body = payload as { status?: unknown; data?: unknown };
  if (body.status === "unavailable") return { available: false, data: null };
  return { available: true, data: (body.data ?? null) as T | null };
}

/** Runs a billing read, mapping an unreachable calculator to a soft result. */
async function readBilling<T>(
  call: () => Promise<unknown>,
): Promise<NestBillingResult<T>> {
  try {
    return billing<T>(await call());
  } catch (error) {
    const status = (error as { response?: { status?: number } })?.response
      ?.status;
    // 503 is the calculator being absent, which is a deployment state rather
    // than a failure of this request. Anything else is a real error and must
    // surface as one — swallowing it would hide an auth or routing fault
    // behind the same "not deployed" notice.
    if (status === 503) return { available: false, data: null };
    throw error;
  }
}

export const nestApi = {
  listDatabases: async (productId: number): Promise<NestDatabase[]> =>
    items<NestDatabase>(
      await proxyApi.request(productId, "GET", NEST_COLLECTION_PATHS.databases),
      NEST_COLLECTION_ENVELOPE_KEYS.databases,
    ),

  listSnapshots: async (productId: number): Promise<NestSnapshot[]> =>
    items<NestSnapshot>(
      await proxyApi.request(productId, "GET", NEST_COLLECTION_PATHS.snapshots),
      NEST_COLLECTION_ENVELOPE_KEYS.snapshots,
    ),

  costReport: async (
    productId: number,
  ): Promise<NestBillingResult<{ records?: NestUsageRecord[] }>> =>
    readBilling(() =>
      proxyApi.request(productId, "GET", NEST_COLLECTION_PATHS.costReport),
    ),

  costSummary: async (
    productId: number,
  ): Promise<NestBillingResult<NestCostSummary>> =>
    readBilling(() =>
      proxyApi.request(productId, "GET", NEST_COLLECTION_PATHS.costSummary),
    ),
};
