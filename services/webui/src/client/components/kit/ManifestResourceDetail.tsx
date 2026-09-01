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
 *
 * Edit (Phase 8 Step 5 frontend) mirrors `ManifestCreateForm.tsx`'s
 * `FormBuilder` binding exactly — same field-config projection, gated on
 * `resource.edit` instead of `resource.create` — but does NOT prefill the
 * form from the selected row: `BiomesPage.tsx` opens the identical
 * `FormModalBuilder` for New and Edit, switching only `title` and
 * `submitButtonText`, never passing the existing biome's values in either
 * mode, so prefilling here would be a real behaviour ADDITION beyond what
 * the hand-written screen does, not parity with it.
 *
 * `useUpdateManifestResource`'s own doc names a found backend gap: the
 * portal registers no `PUT` route at this shape yet, only `POST`/`DELETE`.
 */
import { useState } from "react";
import { FormBuilder } from "@penguintechinc/react-libs";
import { DetailDrawer } from "./DetailDrawer";
import { RowOpenButtons } from "./RowOpenButtons";
import { ActionButton } from "./ActionButton";
import { ConfirmDialog } from "./ConfirmDialog";
import { FactList, type Fact } from "./FactList";
import type { ManifestRow } from "./manifestCells";
import { manifestItemPathBytes } from "./manifestItemPath";
import { toFieldConfig, applyFieldAliases } from "./manifestFormFields";
import {
  useDeleteManifestResource,
  usePerformManifestAction,
  useUpdateManifestResource,
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

/**
 * Substitutes the literal `{name}` token in an `ActionSpec.confirm` string
 * with the acted-on row's own `name_field` value — the one substitution
 * `ActionSpec.confirm`'s docstring authorises; any other braced token is
 * left verbatim (a plain string replace, not a template engine). Byte-exact
 * with `NodesPage.tsx`'s own hand-written interpolation (`` `${pending.
 * confirmation} This affects node "${selected.name}".` ``) once the
 * manifest's confirm string supplies the surrounding text.
 */
function interpolateConfirmName(
  confirm: string | null | undefined,
  name: string,
): string {
  if (!confirm) return "";
  return confirm.replaceAll("{name}", name);
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
  const [editOpen, setEditOpen] = useState(false);

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
  const updateResource = useUpdateManifestResource(
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
  const editFormSpec = resource.edit;

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
            {editFormSpec && (
              <ActionButton
                label="Edit"
                onClick={() => setEditOpen(true)}
                testId={`${testIdPrefix}-edit`}
              />
            )}
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
        message={
          pendingAction && selected
            ? interpolateConfirmName(
                pendingAction.confirm,
                String(selected[resource.name_field] ?? selected.id),
              )
            : ""
        }
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

      {editFormSpec && (
        <FormBuilder
          mode="modal"
          isOpen={editOpen}
          title={`Edit ${resource.label}`}
          fields={editFormSpec.fields.map(toFieldConfig)}
          submitLabel={editFormSpec.submit_label}
          loading={updateResource.isPending}
          onCancel={() => setEditOpen(false)}
          onSubmit={async (values: Record<string, unknown>): Promise<void> => {
            /* istanbul ignore next -- defensive: this form only opens
               (isOpen={editOpen}) via setEditOpen(true) inside the Edit
               button's onClick, which only renders while a row is
               selected — nothing clears selected before a synchronous
               submit completes. */
            if (!selected) return;
            await updateResource.mutateAsync({
              resourceId: selected.id,
              payload: applyFieldAliases(values, editFormSpec.field_aliases),
            });
            setEditOpen(false);
          }}
        />
      )}
    </>
  );
}
