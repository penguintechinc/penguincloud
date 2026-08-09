/**
 * Operation polling for the Nest screens.
 *
 * Nest has no operation COLLECTION reachable from a Nest connection — that
 * route lives on nest-manager, which the deployed HTTPRoute never sends `/api`
 * to, so the adapter raises 501 rather than returning an empty page that would
 * read as "nothing is running". The consequence for the UI is structural: it
 * cannot discover operations, so it watches the ones it started, by the ids the
 * action and create routes hand back.
 *
 * Every loop stops on `is_terminal`, which the portal publishes for exactly
 * this purpose. Branching on a status string instead means re-implementing the
 * terminal-state set in the client, and getting one state wrong there freezes
 * the UI on a stale frame that never corrects itself.
 */

import { useCallback, useState } from "react";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import { nestResourcesApi } from "../../../api/resources/nestResources";
import { queryKeys } from "../../../api/keys";
import { useNestConnection } from "./useNest";
import type { NestOperation } from "./types";

/** Poll interval for a live operation. */
const OPERATION_POLL_MS = 3000;

/**
 * Tracks the operations this screen started and polls each until terminal.
 *
 * Returns the ids in the order they were started, so the panel reads
 * oldest-first and a newly started action appends rather than reorders the
 * list under the operator's cursor.
 */
export function useNestOperationWatch(): {
  operations: NestOperation[];
  watch: (ids: string[]) => void;
  isPolling: boolean;
} {
  const { tenantId, productId, isEnabled } = useNestConnection();
  const queryClient = useQueryClient();
  const [watched, setWatched] = useState<string[]>([]);

  const watch = useCallback(
    (ids: string[]) => {
      if (ids.length === 0) return;
      setWatched((current) => [
        ...current,
        ...ids.filter((id) => !current.includes(id)),
      ]);
      // A create or action has just changed what the product is doing; the
      // list this screen renders is stale until it is refetched.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.nestResource(tenantId, productId, "databases"),
      });
    },
    [queryClient, tenantId, productId],
  );

  const results = useQueries({
    queries: watched.map((operationId) => ({
      queryKey: queryKeys.nestOperation(tenantId, productId, operationId),
      queryFn: async (): Promise<NestOperation | null> => {
        if (productId === undefined) return null;
        return nestResourcesApi.getOperation(productId, operationId);
      },
      enabled: isEnabled && productId !== undefined,
      refetchInterval: (query: { state: { data?: NestOperation | null } }) => {
        const operation = query.state.data;
        if (!operation) return OPERATION_POLL_MS;
        return operation.is_terminal ? false : OPERATION_POLL_MS;
      },
    })),
  });

  const operations = results
    .map((result) => result.data)
    .filter((operation): operation is NestOperation => Boolean(operation));

  return {
    operations,
    watch,
    isPolling: operations.some((operation) => !operation.is_terminal),
  };
}

/**
 * Refetch the databases list when an operation reaches a terminal state.
 *
 * Nest's writes finish out of band, so the row an operator is looking at keeps
 * its pre-action `phase` until something refetches. Tying that to `is_terminal`
 * rather than to a timer means the list updates once, when there is actually
 * something new to show.
 */
export function useRefetchOnSettled(): (operation: NestOperation) => void {
  const queryClient = useQueryClient();
  const { tenantId, productId } = useNestConnection();

  return useCallback(
    (operation: NestOperation) => {
      if (!operation.is_terminal) return;
      void queryClient.invalidateQueries({
        queryKey: queryKeys.nestResource(tenantId, productId, "databases"),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.nestResource(tenantId, productId, "snapshots"),
      });
    },
    [queryClient, tenantId, productId],
  );
}
