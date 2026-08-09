import { useState } from "react";
import { FormModalBuilder } from "@penguintechinc/react-libs";
import {
  ConfirmDialog,
  DataTable,
  DetailDrawer,
} from "../../../components/kit";
import { NestScreen } from "./NestScreen";
import { NestOperationsPanel } from "./NestOperationsPanel";
import { ActionButton, RowOpenButtons } from "./NestUi";
import { DatabaseTabs } from "./DatabaseTabs";
import { databaseColumns, databaseFields } from "./databaseColumns";
import { DATABASE_ACTIONS, type DatabaseAction } from "./databaseActions";
import { useNestDatabases } from "./useNest";
import { useNestOperationWatch } from "./useNestOperations";
import {
  startedOperationIds,
  useCreateDatabase,
  useDeleteDatabase,
  usePerformDatabaseAction,
} from "./useDatabaseMutations";
import type { NestDatabase, NestDatabaseRow } from "./types";

/**
 * Nest data-resources — databases, volumes and object stores.
 *
 * Every write here is asynchronous: Nest answers 202 and keeps working, so the
 * ids each mutation returns are handed to `watch()` and polled until terminal.
 * That is why the operations panel exists on this screen and why it is fed from
 * mutation results rather than a listing — Nest exposes no operation
 * collection at this service.
 */
export default function DatabasesPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useNestDatabases();
  const [selected, setSelected] = useState<NestDatabase | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<NestDatabase | null>(null);
  const [confirming, setConfirming] = useState<DatabaseAction | null>(null);

  const { operations, watch } = useNestOperationWatch();
  const create = useCreateDatabase();
  const remove = useDeleteDatabase();
  const act = usePerformDatabaseAction();

  // Nest addresses every resource by NAME; the UUID it also carries is not
  // usable in any route, so the table keys on the name.
  const rows: NestDatabaseRow[] = (data ?? []).map((database) => ({
    ...database,
    id: database.name,
  }));

  const submit = async (values: Record<string, unknown>): Promise<void> => {
    const created = await create.mutateAsync(values);
    watch(startedOperationIds(created));
    setFormOpen(false);
  };

  const runAction = (action: DatabaseAction): void => {
    if (!selected) return;
    act.mutate(
      { name: selected.name, action: action.id },
      {
        onSuccess: (outcome) => {
          watch(startedOperationIds(outcome));
          setConfirming(null);
        },
      },
    );
  };

  return (
    <NestScreen
      title="Databases"
      description="Nest data resources: managed databases, volumes and object stores."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <NestOperationsPanel operations={operations} />

      <div className="mb-4 flex justify-end">
        <ActionButton
          label="New database"
          onClick={() => setFormOpen(true)}
          testId="nest-database-create"
        />
      </div>

      <DataTable<NestDatabaseRow>
        columns={databaseColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Nest data resources"
      />

      <RowOpenButtons
        rows={rows}
        label={(database) => database.name}
        onOpen={(database) => {
          setActiveTab("overview");
          setSelected(database);
        }}
        testIdPrefix="nest-database-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.name ?? ""}
        subtitle={
          selected ? `${selected.resourceType ?? "resource"}` : undefined
        }
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => setSelected(null)}
        testId="nest-database-drawer"
        tabs={DatabaseTabs(selected)}
        actions={
          <>
            {DATABASE_ACTIONS.map((action) => (
              <ActionButton
                key={action.id}
                label={action.label}
                variant={action.isDangerous ? "danger" : "primary"}
                onClick={() => setConfirming(action)}
                testId={`nest-database-action-${action.id}`}
              />
            ))}
            <ActionButton
              label="Delete"
              variant="danger"
              onClick={() => setDeleting(selected)}
              testId="nest-database-delete"
            />
          </>
        }
      />

      <FormModalBuilder
        title="New database"
        fields={databaseFields}
        isOpen={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={submit}
        submitButtonText="Create"
      />

      <ConfirmDialog
        isOpen={confirming !== null}
        title={confirming?.label ?? ""}
        message={
          confirming && selected ? confirming.message(selected.name) : ""
        }
        confirmLabel={confirming?.confirmLabel ?? "Confirm"}
        isDangerous={confirming?.isDangerous ?? false}
        isLoading={act.isPending}
        onConfirm={() => confirming && runAction(confirming)}
        onCancel={() => setConfirming(null)}
        testId="nest-database-confirm"
      />

      <ConfirmDialog
        isOpen={deleting !== null}
        title="Delete database"
        message={
          deleting
            ? `Deleting "${deleting.name}" destroys the resource and its data. ` +
              `Snapshots taken from it are not removed and remain billable.`
            : ""
        }
        confirmLabel="Delete"
        isDangerous
        isLoading={remove.isPending}
        onConfirm={() => {
          if (!deleting) return;
          remove.mutate(
            { name: deleting.name },
            {
              onSuccess: () => {
                setDeleting(null);
                setSelected(null);
              },
            },
          );
        }}
        onCancel={() => setDeleting(null)}
        testId="nest-database-delete-confirm"
      />
    </NestScreen>
  );
}
