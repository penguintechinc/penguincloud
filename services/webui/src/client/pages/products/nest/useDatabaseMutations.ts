/**
 * Create, delete and action mutations for Nest data-resources.
 *
 * Split from `DatabasesPage` so the page stays under the 5000-character limit
 * and so the "what do we do with the operation ids" decision is testable
 * without rendering a table, a drawer and two modals to reach it.
 *
 * All three go through TYPED portal routes, not the proxy: Nest's allowlist is
 * GET-only because every one of its writes answers 202 with an operation to
 * poll. See `api/resources/nestResources.ts`.
 */

import { nestResourcesApi } from "../../../api/resources/nestResources";
import { useNestMutation } from "./useNest";
import type { NestActionResult, NestCreatedResource } from "./types";

/**
 * Creates a data-resource.
 *
 * The payload is passed through as the form produced it. Nest's create/read
 * field-name asymmetry (`resourceType` vs `type`) is normalised in the ADAPTER,
 * which is the layer that knows the product; rewriting it here as well would
 * apply the alias twice.
 */
export function useCreateDatabase() {
  return useNestMutation<Record<string, unknown>, NestCreatedResource>(
    "databases",
    (productId, payload) => nestResourcesApi.createDatabase(productId, payload),
  );
}

/**
 * Deletes a data-resource by NAME.
 *
 * A 409 from Nest ("still referenced") reaches the caller as a 409 rather than
 * a generic failure, which is the distinction the confirm dialog needs.
 */
export function useDeleteDatabase() {
  return useNestMutation<{ name: string }, unknown>(
    "databases",
    (productId, vars) => nestResourcesApi.deleteDatabase(productId, vars.name),
  );
}

/** Starts snapshot / restore / migrate, returning the operations it began. */
export function usePerformDatabaseAction() {
  return useNestMutation<
    { name: string; action: string; payload?: Record<string, unknown> },
    NestActionResult
  >("databases", (productId, vars) =>
    nestResourcesApi.performAction(
      productId,
      vars.name,
      vars.action,
      vars.payload,
    ),
  );
}

/**
 * The operation ids an action or create started.
 *
 * An action returns a LIST because the contract allows one action to start
 * several operations; a create returns a single handle in `operation_id`, and
 * `null` there means the create finished synchronously. Normalising both to a
 * list here is what lets the caller hand either to `watch()` without branching
 * on which route produced it.
 */
export function startedOperationIds(
  outcome: NestActionResult | NestCreatedResource,
): string[] {
  if ("operations" in outcome) {
    return outcome.operations.map((operation) => operation.id);
  }
  return outcome.operation_id ? [outcome.operation_id] : [];
}
