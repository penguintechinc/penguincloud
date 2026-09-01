/**
 * The capability-subset gate between {@link ManifestResourceScreen} and each
 * product's hand-written screens — the mechanism WaddleAI acceptance test
 * §8.1 requires: a routing DECISION with no per-product name, list, or
 * branch anywhere in it, so a future read-only product renders from its
 * manifest with zero new webui lines, while a product whose manifest
 * declares capabilities this renderer cannot yet reproduce losslessly keeps
 * its existing screen rather than silently regressing.
 *
 * `SUPPORTED_CAPABILITIES` is the ONLY place this file names what the
 * renderer can do. Widening it later (once a capability earns its own
 * equivalence proof, the way `ManifestResourceScreen.equivalence.test.tsx`
 * proves the table today) lets every already-declared resource with that
 * capability start routing with no change anywhere else — including no
 * change to `App.tsx` or to this module's own logic.
 */
import type { ConsoleManifest, ResourceDescriptor } from "./manifestTypes";

/** Every capability this schema version's resources can declare. */
export const RESOURCE_CAPABILITIES = [
  "list",
  "operations",
  "actions",
  "create",
] as const;

export type ResourceCapability = (typeof RESOURCE_CAPABILITIES)[number];

/**
 * What `ManifestResourceScreen` can render losslessly TODAY, proven by an
 * equivalence test against a hand-written screen — not merely "the code
 * path exists". The component technically renders operations panels, row
 * actions, delete, and a create form too (see `ManifestResourceDetail.tsx`,
 * `ManifestCreateForm.tsx`), but only the rendered TABLE has an equivalence
 * proof against Gough's committed manifest
 * (`ManifestResourceScreen.equivalence.test.tsx`'s module doc: "actions/
 * create/item_path are simplified to the empty/null case here ... this
 * file's scope is the rendered TABLE"). Routing a resource whose manifest
 * declares more than this set would be shipping unverified UI, not a
 * capability gap this gate should paper over.
 */
export const SUPPORTED_CAPABILITIES: ReadonlySet<ResourceCapability> = new Set([
  "list",
]);

/**
 * The capabilities one resource, in one manifest, actually needs to render
 * losslessly — derived purely from what the manifest DECLARES, never from a
 * product name.
 *
 * `operations` is a PRODUCT-level field (`ConsoleManifest.operations`), not
 * a per-resource one — `ManifestResourceScreen` renders the operations
 * panel whenever the manifest carries one, for every resource of that
 * product (see that component's `operationsSpec` wiring), so its presence
 * folds into every resource's requirement the same way.
 *
 * `delete` folds into `'actions'` rather than adding a fifth capability:
 * both render from the same not-yet-equivalence-proven code path in
 * `ManifestResourceDetail.tsx` (the detail drawer's action buttons), gated
 * on the same `item_path` precondition, so a resource declaring only
 * `delete` is exactly as unproven as one declaring only `actions`.
 */
export function requiredCapabilities(
  manifest: ConsoleManifest,
  resource: ResourceDescriptor,
): Set<ResourceCapability> {
  const required = new Set<ResourceCapability>(["list"]);
  if (manifest.operations) required.add("operations");
  if (resource.actions.length > 0 || resource.delete) required.add("actions");
  if (resource.create) required.add("create");
  return required;
}

/**
 * True iff every capability this resource requires is a subset of
 * {@link SUPPORTED_CAPABILITIES} — the single boolean `ProductResourceRoute`
 * acts on. No product identity is inspected anywhere in this function or
 * its callees.
 */
export function isManifestRoutable(
  manifest: ConsoleManifest,
  resource: ResourceDescriptor,
): boolean {
  for (const capability of requiredCapabilities(manifest, resource)) {
    if (!SUPPORTED_CAPABILITIES.has(capability)) return false;
  }
  return true;
}
