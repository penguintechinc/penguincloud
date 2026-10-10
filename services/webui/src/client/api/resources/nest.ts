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

import { envelopeList } from "../envelope";
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
    envelopeList<NestDatabase>(
      await proxyApi.request(productId, "GET", NEST_COLLECTION_PATHS.databases),
      NEST_COLLECTION_ENVELOPE_KEYS.databases,
    ),

  listSnapshots: async (productId: number): Promise<NestSnapshot[]> =>
    envelopeList<NestSnapshot>(
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
