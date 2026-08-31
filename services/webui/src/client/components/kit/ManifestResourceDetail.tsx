/**
 * Row-open buttons, detail drawer, and the drawer's own delete/action
 * buttons for a manifest-driven resource — the "detail and row-actions"
 * `ManifestResourceScreen.tsx`'s module doc used to defer entirely.
 *
 * Gated on `resource.item_path !== null`: schema v2's `ItemPathSpec` is the
 * manifest's own statement that this resource kind has a real, individually
 * addressable item route (`validate_manifest` proves it is proxy-reachable
 * at import time) — Gough's `clusters` is the case with none, and per
 * `ResourceDescriptor`'s Python doc that is a genuine "no item endpoint"
 * fact, not an omission to paper over. A resource with no `item_path`
 * therefore gets no open button and no drawer, the same way it gets no nav
 * link when it has no `list` either.
 *
 * The drawer's Overview tab renders from the ALREADY-FETCHED row, not a
 * fresh per-item proxy fetch — matching every hand-written product screen's
 * own actual behaviour (`NodesPage`/`BiomesPage`/`AgentsPage`'s drawers all
 * read `selected.*` off the row object the list query already returned,
 * never a second request). A live per-item GET is possible in principle
 * (`manifestItemPathBytes` builds the byte-exact route), but this schema
 * version declares no ITEM response envelope — `EnvelopeSpec` is
 * documented as a list-array unwrap path only — and this worktree does not
 * check out Gough's own source to verify one by inspection, the same
 * standard `gough/manifest.py` itself holds to elsewhere ("a fabricated
 * mapping would be worse than a plain string"). Left as a stated follow-up,
 * not guessed at here.
 */
import { useState } from "react";
import { DetailDrawer } from "./DetailDrawer";
import { RowOpenButtons } from "./RowOpenButtons";
import { ActionButton } from "./ActionButton";
import { ConfirmDialog } from "./ConfirmDialog";
import { FactList, type Fact } from "./FactList";
import type { ManifestRow } from "./manifestCells";
import { manifestItemPathBytes } from "./manifestItemPath";
import {
  useDeleteManifestResource,
  usePerformManifestAction,
} from "./manifestMutations";
import type { ActionSpec, ResourceDescriptor } from "./manifestTypes";

type Row = ManifestRow & { id: string };

/** Row-level enable predicate — both fields declared together or not at
 * all (`ActionSpec.__post_init__`), so an absent `enabled_when_field` means
 * always enabled. */
function isActionEnabled(action: ActionSpec, row: Row): boolean {
  if (!action.enabled_when_field) return true;
  const value = String(row[action.enabled_when_field] ?? "");
  return action.enabled_when_in.includes(value);
}

function actionButtonVariant(variant: string): "primary" | "danger" | "ghost" {
  return variant === "danger" ? "danger" : "primary";
}

/** Plain-text rendering of one cell for the drawer's `FactList` — reuses
 * `renderCell`'s `absent_as` handling, then flattens to a string since
 * `FactList` renders its own dash for a falsy value. */
function factValue(
  column: ResourceDescriptor["columns"][number],
  row: Row,
): string {
  const raw = row[column.field];
  if (raw === null || raw === undefined) return "";
  if (Array.isArray(raw)) return raw.map(String).join(", ");
  return String(raw);
}

export interface ManifestResourceDetailProps {
  productType: string;
  tenantId: number | undefined;
  productId: number | undefined;
  resource: ResourceDescriptor;
  rows: Row[];
}

export function ManifestResourceDetail({
  productType,
  tenantId,
  productId,
  resource,
  rows,
}: ManifestResourceDetailProps) {
  const [selected, setSelected] = useState<Row | null>(null);
  const [pendingAction, setPendingAction] = useState<ActionSpec | null>(null);
  const [pendingDelete, setPendingDelete] = useState(false);

  const deleteResource = useDeleteManifestResource(
    productType,
    tenantId,
    productId,
    resource.kind,
  );
  const performAction = usePerformManifestAction(
    productType,
    tenantId,
    productId,
    resource.kind,
  );

  if (resource.item_path === null || resource.item_path === undefined) {
    return null;
  }
  const itemPath = resource.item_path;
  const testIdPrefix = `${productType}-manifest-${resource.kind}`;

  const openRow = (row: Row) => {
    console.log(
      `[ManifestResourceDetail] OpenDetail { kind: "${resource.kind}", itemPath: "${manifestItemPathBytes(itemPath, row.id)}" }`,
    );
    setSelected(row);
  };

  const facts: Fact[] = selected
    ? resource.columns.map((column) => [
        column.label,
        factValue(column, selected),
      ])
    : [];

  return (
    <>
      <RowOpenButtons
        rows={rows}
        label={(row) => String(row[resource.name_field] ?? row.id)}
        onOpen={openRow}
        testIdPrefix={`${testIdPrefix}-open`}
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={
          selected ? String(selected[resource.name_field] ?? selected.id) : ""
        }
        subtitle={selected ? `${resource.label} ${selected.id}` : undefined}
        activeTab="overview"
        /* istanbul ignore next -- defensive: DetailDrawer only renders tab
           buttons (and so ever calls onTabChange) when tabs.length > 1; this
           drawer always declares exactly one "overview" tab, so the handler
           is structurally unreachable through the UI, not untested behaviour. */
        onTabChange={() => undefined}
        onClose={() => setSelected(null)}
        testId={`${testIdPrefix}-drawer`}
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: (
              <FactList testId={`${testIdPrefix}-facts`} facts={facts} />
            ),
          },
        ]}
        actions={
          <>
            {resource.actions.map((action) => (
              <ActionButton
                key={action.verb}
                label={action.label}
                variant={actionButtonVariant(action.variant)}
                disabled={
                  action.form != null ||
                  (selected !== null && !isActionEnabled(action, selected))
                }
                onClick={() => setPendingAction(action)}
                testId={`${testIdPrefix}-action-${action.verb}`}
              />
            ))}
            {resource.delete && (
              <ActionButton
                label="Delete"
                variant="danger"
                onClick={() => setPendingDelete(true)}
                testId={`${testIdPrefix}-delete`}
              />
            )}
          </>
        }
      />

      <ConfirmDialog
        isOpen={pendingAction !== null}
        title={
          pendingAction
            ? `${pendingAction.label} ${resource.label.toLowerCase()}`
            : ""
        }
        message={pendingAction?.confirm ?? ""}
        confirmLabel={pendingAction?.label}
        isDangerous={pendingAction?.variant === "danger"}
        isLoading={performAction.isPending}
        onConfirm={() => {
          /* istanbul ignore next -- defensive: this dialog only opens
             (isOpen={pendingAction !== null}) once both selected and
             pendingAction are set by openRow/setPendingAction, and nothing
             clears either before a synchronous confirm click completes. */
          if (!selected || !pendingAction) return;
          performAction.mutate(
            { resourceId: selected.id, verb: pendingAction.verb },
            { onSuccess: () => setPendingAction(null) },
          );
        }}
        onCancel={() => setPendingAction(null)}
        testId={`${testIdPrefix}-action-confirm`}
      />

      <ConfirmDialog
        isOpen={pendingDelete}
        title={`Delete ${resource.label.toLowerCase()}`}
        message={resource.delete?.confirm ?? ""}
        confirmLabel="Delete"
        isDangerous
        isLoading={deleteResource.isPending}
        onConfirm={() => {
          /* istanbul ignore next -- defensive: this dialog only opens
             (isOpen={pendingDelete}) via setPendingDelete(true) inside the
             Delete button's onClick, which only renders while a row is
             selected — nothing clears selected before a synchronous
             confirm click completes. */
          if (!selected) return;
          deleteResource.mutate(selected.id, {
            onSuccess: () => {
              setPendingDelete(false);
              setSelected(null);
            },
          });
        }}
        onCancel={() => setPendingDelete(false)}
        testId={`${testIdPrefix}-delete-confirm`}
      />
    </>
  );
}
