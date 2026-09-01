/**
 * Generic create/delete/action mutations for a manifest-driven product
 * screen, all through the portal's own TYPED routes
 * (`app/resources_api.py`, `app/operations_api.py`'s
 * `perform_resource_action`) — never the byte proxy. These routes are
 * already product-agnostic (`kind` is a path segment, not baked into the
 * route), the same way `useManifestOperations.ts`'s `GET
 * /products/{id}/operations` is, so nothing here is Gough-specific or needs
 * to be.
 *
 * Distinct from `useProductResource.ts`'s READ path on purpose: a resource
 * with `transport === "proxy"` has no typed mutation backing at all (see
 * `ResourceDescriptor`'s Python doc) and these hooks are never called for
 * one — `ManifestResourceScreen` gates `create`/`delete`/`actions` on the
 * manifest declaring them, which schema v2's own `ResourceDescriptor.
 * __post_init__` already refuses to let a `"proxy"` resource do.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";
import { portalUrl } from "../../api/portalPaths";
import { queryKeys } from "../../api/keys";

/** Invalidates the one manifest resource list a mutation just changed, and
 * the product's operations feed (a `starts_operations` action needs the
 * panel to pick up what it just started without a manual refresh). */
function useInvalidateManifestResource(
  productType: string,
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
) {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({
      queryKey: [
        ...queryKeys.consoleManifestResource(productType),
        tenantId,
        productId,
        kind,
      ],
    });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.consoleManifestOperations(tenantId, productId),
    });
  };
}

/** Creates one resource via `POST /products/{id}/resources/{kind}`. */
export function useCreateManifestResource(
  productType: string,
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
) {
  const invalidate = useInvalidateManifestResource(
    productType,
    tenantId,
    productId,
    kind,
  );
  return useMutation({
    mutationFn: async (payload: Record<string, unknown>): Promise<unknown> => {
      if (productId === undefined) {
        throw new Error("No connection for the active tenant");
      }
      const response = await api.post(
        portalUrl.resources(productId, kind),
        payload,
      );
      return response.data;
    },
    onSuccess: invalidate,
  });
}

/**
 * Updates one resource via `PUT /products/{id}/resources/{kind}/{id}` — the
 * exact parallel of {@link useCreateManifestResource}, gated on the
 * manifest's own `resource.edit` the same way create is gated on
 * `resource.create` (`ManifestResourceDetail.tsx`).
 *
 * BACKEND GAP (Phase 8 Step 5 frontend, found not guessed at): as of this
 * commit, `services/portal-api/app/resources_api.py`'s `resources_bp`
 * registers only `POST /resources/<kind>` (`create_resource`) and `DELETE
 * /resources/<kind>/<id>` (`delete_resource`) — no `PUT` route exists at
 * `/resources/<kind>/<id>` yet, confirmed by reading that module directly
 * and by `openapi/v1.yaml`'s `paths:` section (Stage 1 added the `edit`
 * SCHEMA field but no new path). `GoughAdapter.update_resource` exists and
 * is listed in `capabilities()` (`adapters/gough/adapter.py:438,198`), so
 * `apply_capabilities_overlay` does NOT strip Gough biomes' `edit` — the
 * overlaid manifest served to the browser really does carry a non-null
 * `edit` FormSpec, but there is nowhere on the portal for this PUT to land
 * yet. It will 405 (the URL shape already serves DELETE) against a live
 * portal until that route ships.
 *
 * Wired here to the contract the schema and the overlay already commit to
 * — same URL `useDeleteManifestResource` uses, PUT instead of DELETE (the
 * same same-URL-different-verb reuse `/tenants/{id}` and `/users/{id}`
 * already use for their own PUT) — so this hook needs no change once the
 * backend route exists. A stated backend follow-up, not guessed at here;
 * see the Step 5 frontend report for the finding.
 */
export function useUpdateManifestResource(
  productType: string,
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
) {
  const invalidate = useInvalidateManifestResource(
    productType,
    tenantId,
    productId,
    kind,
  );
  return useMutation({
    mutationFn: async (vars: {
      resourceId: string;
      payload: Record<string, unknown>;
    }): Promise<unknown> => {
      if (productId === undefined) {
        throw new Error("No connection for the active tenant");
      }
      const response = await api.put(
        portalUrl.resource(productId, kind, vars.resourceId),
        vars.payload,
      );
      return response.data;
    },
    onSuccess: invalidate,
  });
}

/** Deletes one resource via `DELETE /products/{id}/resources/{kind}/{id}`. */
export function useDeleteManifestResource(
  productType: string,
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
) {
  const invalidate = useInvalidateManifestResource(
    productType,
    tenantId,
    productId,
    kind,
  );
  return useMutation({
    mutationFn: async (resourceId: string): Promise<unknown> => {
      if (productId === undefined) {
        throw new Error("No connection for the active tenant");
      }
      const response = await api.delete(
        portalUrl.resource(productId, kind, resourceId),
      );
      return response.data;
    },
    onSuccess: invalidate,
  });
}

/** Invokes one `ActionSpec` verb via `POST
 * /products/{id}/resources/{kind}/{id}/actions/{verb}`. */
export function usePerformManifestAction(
  productType: string,
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
) {
  const invalidate = useInvalidateManifestResource(
    productType,
    tenantId,
    productId,
    kind,
  );
  return useMutation({
    mutationFn: async (vars: {
      resourceId: string;
      verb: string;
      payload?: Record<string, unknown>;
    }): Promise<unknown> => {
      if (productId === undefined) {
        throw new Error("No connection for the active tenant");
      }
      const response = await api.post(
        portalUrl.resourceAction(productId, kind, vars.resourceId, vars.verb),
        vars.payload ?? {},
      );
      return response.data;
    },
    onSuccess: invalidate,
  });
}
