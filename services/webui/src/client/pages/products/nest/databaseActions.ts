/**
 * The Nest data-resource actions, and what each one warns about.
 *
 * `introspect` is absent by choice. It is a read-only probe that produces a
 * schema report, and the portal has nowhere to show one — offering a button
 * that starts an operation whose output the operator cannot read would be a
 * control that appears to do nothing. It stays available through the adapter.
 *
 * The confirm copy is per-action rather than a generic "are you sure": the
 * three verbs fail differently, and a dialog that does not say how is one an
 * operator learns to click through.
 */

export interface DatabaseAction {
  /** Literal Nest action segment. Validated adapter-side against a set. */
  id: string;
  label: string;
  /** Danger styling and a mandatory confirm for anything that overwrites. */
  isDangerous: boolean;
  /** Written to be read under time pressure — what happens, and to what. */
  message: (name: string) => string;
  confirmLabel: string;
}

export const DATABASE_ACTIONS: DatabaseAction[] = [
  {
    id: "snapshot",
    label: "Snapshot",
    isDangerous: false,
    message: (name) =>
      `Take a point-in-time snapshot of "${name}". The resource stays online; ` +
      `the snapshot is charged as stored capacity until it is deleted.`,
    confirmLabel: "Take snapshot",
  },
  {
    id: "restore",
    label: "Restore",
    isDangerous: true,
    message: (name) =>
      `Restore "${name}" from its most recent backup. Nest restores ` +
      `side-by-side by default, so this provisions a NEW resource rather than ` +
      `overwriting this one — but it consumes capacity and takes time.`,
    confirmLabel: "Restore",
  },
  {
    id: "migrate",
    label: "Migrate to managed",
    isDangerous: true,
    message: (name) =>
      `Migrate "${name}" to Nest-managed storage. This moves the underlying ` +
      `data and cannot be reversed from the portal.`,
    confirmLabel: "Migrate",
  },
];
