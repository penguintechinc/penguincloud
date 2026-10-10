/**
 * Generic response-driven operation watch for a `mode="watch"` manifest
 * resource (`OperationsSpec.mode`, `app/adapters/manifest.py`).
 *
 * Generalises `pages/products/nest/useNestOperations.ts`'s
 * `useNestOperationWatch`/`useRefetchOnSettled` pair into one product-agnostic
 * hook: a `mode="watch"` resource has no operation COLLECTION to list
 * (`list_operations` answers 501 for an adapter like Nest's), so this watches
 * only the ids a create or action handed back, via
 * `GET /operations/{kind}/{id}` — never a `GET /operations` poll. See
 * `manifestMutations.ts`'s `startedManifestOperationIds` for where those ids
 * come from.
 *
 * `kind` is the resource's own kind (`ResourceDescriptor.kind`) — used to
 * invalidate that resource's list query, which is always keyed off the
 * resource's kind (`useProductResource.ts`), never an operation kind.
 *
 * `operationKind` is the Nest-convergence closure: schema v2's
 * `OperationsSpec.operation_kind` lets a manifest override the URL kind the
 * watch route addresses. Nest's own adapter hardcodes
 * `NEST_OPERATION_KIND = "operation"`, unrelated to its resource kind
 * `"database"` — `get_operation` 501s if addressed with `"database"`
 * instead. `operationKind ?? kind` is the resolution: a manifest that
 * declares no override (`operation_kind` absent) watches at the resource's
 * own kind, the prior and still-default behaviour; one that does (Nest's)
 * watches at the declared literal instead, while the resource-list
 * invalidation still targets `kind` — the two are deliberately decoupled,
 * not the same value reused twice.
 *
 * Both invalidation points `useNestOperationWatch`/`useRefetchOnSettled`
 * split across two files are folded into this one hook: `watch()` invalidates
 * immediately (the product has just started doing something, so the list
 * this screen renders is already stale), and an internal effect invalidates
 * again the first time each watched operation reports `is_terminal` (the
 * write finishes out of band, so the row's displayed state does not update on
 * its own). A `Set` of already-settled ids is what keeps the second
 * invalidation firing exactly once per operation rather than on every poll
 * response after it turns terminal.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";
import { portalUrl } from "../../api/portalPaths";
import { queryKeys } from "../../api/keys";
import type { OperationLike } from "./operationsPanelTypes";

/**
 * The per-id polling decision, factored out of the `useQueries` options so it
 * is directly unit-testable rather than only reachable through TanStack
 * Query's own internals — mirrors `nextPollInterval` in
 * `useManifestOperations.ts`, but per-item (one operation) rather than
 * per-collection (any row in a page): with no data yet, keep polling; once an
 * operation reports `is_terminal`, stop for that id specifically, leaving any
 * other still-watched id polling independently.
 */
export function nextOperationPollInterval(
  operation: OperationLike | null | undefined,
  pollIntervalMs: number,
): number | false {
  if (!operation) return pollIntervalMs;
  return operation.is_terminal ? false : pollIntervalMs;
}

export interface UseManifestOperationWatchResult {
  /** Resolved operations for every watched id, oldest-started first — so the
   * panel reads oldest-first and a newly started action appends rather than
   * reorders the list under the operator's cursor. */
  operations: OperationLike[];
  /** Registers ids to poll. Called from a create form's or a row action's
   * onSuccess — never invoked with an empty list from an omitted watch(). */
  watch: (ids: string[]) => void;
  /** True while any watched operation is still non-terminal. */
  isPolling: boolean;
}

/**
 * Tracks the operation ids one `mode="watch"` resource screen started, and
 * polls each until it reports `is_terminal`.
 *
 * @param kind The resource's own kind — drives resource-list invalidation
 * only, never the watch URL.
 * @param operationKind `OperationsSpec.operation_kind`, when the manifest
 * declares one. `undefined`/`null` falls back to `kind` for the watch URL
 * too, matching every adapter whose operation-kind space is its own
 * resource kind.
 */
export function useManifestOperationWatch(
  productType: string,
  tenantId: number | undefined,
  productId: number | undefined,
  kind: string,
  enabled: boolean,
  pollIntervalMs: number,
  operationKind?: string | null,
): UseManifestOperationWatchResult {
  const queryClient = useQueryClient();
  const urlKind = operationKind ?? kind;
  const [watched, setWatched] = useState<string[]>([]);
  const settledIds = useRef<Set<string>>(new Set());

  const invalidateResourceList = useCallback(() => {
    void queryClient.invalidateQueries({
      queryKey: [
        ...queryKeys.consoleManifestResource(productType),
        tenantId,
        productId,
        kind,
      ],
    });
  }, [queryClient, productType, tenantId, productId, kind]);

  const watch = useCallback(
    (ids: string[]) => {
      if (ids.length === 0) return;
      setWatched((current) => [
        ...current,
        ...ids.filter((id) => !current.includes(id)),
      ]);
      invalidateResourceList();
    },
    [invalidateResourceList],
  );

  const results = useQueries({
    queries: watched.map((operationId) => ({
      queryKey: queryKeys.consoleManifestOperationWatch(
        tenantId,
        productId,
        operationId,
      ),
      queryFn: async (): Promise<OperationLike | null> => {
        /* istanbul ignore next -- defensive: `enabled` requires productId to
           be defined before queryFn ever runs; this keeps queryFn total for
           the type checker rather than asserting past it. */
        if (productId === undefined) return null;
        const response = await api.get(
          portalUrl.operation(productId, urlKind, operationId),
        );
        return response.data as OperationLike;
      },
      enabled: enabled && productId !== undefined,
      refetchInterval: (query: { state: { data?: OperationLike | null } }) =>
        nextOperationPollInterval(query.state.data, pollIntervalMs),
    })),
  });

  const operations = results
    .map((result) => result.data)
    .filter((operation): operation is OperationLike => Boolean(operation));

  useEffect(() => {
    const newlyTerminal = operations.filter(
      (operation) =>
        operation.is_terminal && !settledIds.current.has(operation.id),
    );
    if (newlyTerminal.length === 0) return;
    for (const operation of newlyTerminal) {
      settledIds.current.add(operation.id);
    }
    invalidateResourceList();
    // `operations` is a new array reference every render (built fresh above
    // from `results.map().filter()`), so this effect body runs more often
    // than strictly necessary — the `settledIds` Set is what makes a
    // spurious re-run a no-op rather than a duplicate invalidation.
  }, [operations, invalidateResourceList]);

  return {
    operations,
    watch,
    isPolling: operations.some((operation) => !operation.is_terminal),
  };
}
