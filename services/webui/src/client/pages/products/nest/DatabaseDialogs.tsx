import { FormModalBuilder } from "@penguintechinc/react-libs";
import { ConfirmDialog } from "../../../components/kit";
import { ActionButton } from "./NestUi";
import { databaseFields } from "./databaseColumns";
import { DATABASE_ACTIONS, type DatabaseAction } from "./databaseActions";
import type { NestDatabase } from "./types";

interface CreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (values: Record<string, unknown>) => Promise<void>;
}

/**
 * The create-database form.
 *
 * There is no edit counterpart: Nest exposes no update route for a
 * data-resource. Changing one is `migrate`, which is an action with an
 * operation to poll, not a field edit — so a shared create/edit modal would
 * imply a capability the product does not have.
 */
export function CreateDatabaseModal({
  isOpen,
  onClose,
  onSubmit,
}: CreateModalProps) {
  return (
    <FormModalBuilder
      title="New database"
      fields={databaseFields}
      isOpen={isOpen}
      onClose={onClose}
      onSubmit={onSubmit}
      submitButtonText="Create"
    />
  );
}

interface DrawerActionsProps {
  onAction: (action: DatabaseAction) => void;
  onDelete: () => void;
}

/**
 * The verb buttons in the detail drawer's footer.
 *
 * Rendered from `DATABASE_ACTIONS` rather than written out, so a verb cannot
 * be added to the table without a button appearing — or, worse, be styled as
 * safe here while the table marks it dangerous.
 */
export function DrawerActions({ onAction, onDelete }: DrawerActionsProps) {
  return (
    <>
      {DATABASE_ACTIONS.map((action) => (
        <ActionButton
          key={action.id}
          label={action.label}
          variant={action.isDangerous ? "danger" : "primary"}
          onClick={() => onAction(action)}
          testId={`nest-database-action-${action.id}`}
        />
      ))}
      <ActionButton
        label="Delete"
        variant="danger"
        onClick={onDelete}
        testId="nest-database-delete"
      />
    </>
  );
}

interface ActionConfirmProps {
  action: DatabaseAction | null;
  database: NestDatabase | null;
  isLoading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirmation for snapshot / restore / migrate.
 *
 * Extracted with the delete dialog so `DatabasesPage` stays under the
 * 5000-character limit the other product pages hold to. The copy itself lives
 * in `databaseActions.ts`: each verb fails differently, and a dialog that does
 * not say how is one an operator learns to click through.
 */
export function ActionConfirmDialog({
  action,
  database,
  isLoading,
  onConfirm,
  onCancel,
}: ActionConfirmProps) {
  return (
    <ConfirmDialog
      isOpen={action !== null}
      title={action?.label ?? ""}
      message={action && database ? action.message(database.name) : ""}
      confirmLabel={action?.confirmLabel ?? "Confirm"}
      isDangerous={action?.isDangerous ?? false}
      isLoading={isLoading}
      onConfirm={onConfirm}
      onCancel={onCancel}
      testId="nest-database-confirm"
    />
  );
}

interface DeleteConfirmProps {
  database: NestDatabase | null;
  isLoading: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirmation for deleting a data-resource.
 *
 * The message names the snapshot consequence because it is the one an operator
 * will not predict: Nest does not cascade a delete to the snapshots taken from
 * a resource, so they survive it and keep being charged.
 */
export function DeleteConfirmDialog({
  database,
  isLoading,
  onConfirm,
  onCancel,
}: DeleteConfirmProps) {
  return (
    <ConfirmDialog
      isOpen={database !== null}
      title="Delete database"
      message={
        database
          ? `Deleting "${database.name}" destroys the resource and its data. ` +
            `Snapshots taken from it are not removed and remain billable.`
          : ""
      }
      confirmLabel="Delete"
      isDangerous
      isLoading={isLoading}
      onConfirm={onConfirm}
      onCancel={onCancel}
      testId="nest-database-delete-confirm"
    />
  );
}
