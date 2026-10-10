/**
 * Fetches `GET /api/v1/console/manifests` — every product the active
 * tenant is connected to that has a committed manifest (Phase 8 Design §3).
 *
 * Goes through `portal.get`, the OpenAPI-generated typed client
 * (`api/portal.ts`), not a hand-written `api/resources/console.ts` binding:
 * there is exactly one call site for this endpoint and `portal.get` already
 * gives it full compile-time path safety against `api/schema.d.ts` (which
 * `npm run generate:api` derives from `openapi/v1.yaml`) with zero manual
 * URL wiring to keep in sync. The response is re-asserted against this
 * module's own `ConsoleManifestsResponse` (see `manifestTypes.ts`'s module
 * doc for why that type is hand-mirrored rather than the generated one).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { portal } from "../../api/portal";
import { queryKeys } from "../../api/keys";
import { useActiveTenantId } from "./useProductResource";
import type {
  ConsoleManifestsResponse,
  ProductManifestEntry,
} from "./manifestTypes";

/**
 * Every connected product's overlaid manifest for the active tenant.
 *
 * Disabled (and returns an empty list, never fires) until a tenant is
 * selected — the same "no placeholder id" discipline `useProductResource`
 * follows for the identical reason.
 */
export function useConsoleManifests(): UseQueryResult<ProductManifestEntry[]> {
  const tenantId = useActiveTenantId();

  return useQuery({
    queryKey: queryKeys.consoleManifestsByTenant(tenantId),
    queryFn: async (): Promise<ProductManifestEntry[]> => {
      /* istanbul ignore next -- defensive: `enabled` requires tenantId to be
         defined before queryFn ever runs; this keeps queryFn total for the
         type checker rather than asserting past it. */
      if (tenantId === undefined) return [];
      const raw = await portal.get("/api/v1/console/manifests", {
        query: { tenant_id: tenantId },
      });
      return (raw as unknown as ConsoleManifestsResponse).manifests;
    },
    enabled: tenantId !== undefined,
  });
}
