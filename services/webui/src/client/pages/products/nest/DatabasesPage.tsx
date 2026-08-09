import { useState } from "react";
import { DataTable, DetailDrawer } from "../../../components/kit";
import { NestScreen } from "./NestScreen";
import { NestOperationsPanel } from "./NestOperationsPanel";
import { ActionButton, RowOpenButtons } from "./NestUi";
import { DatabaseTabs } from "./DatabaseTabs";
import {
  ActionConfirmDialog,
  CreateDatabaseModal,
  DeleteConfirmDialog,
  DrawerActions,
} from "./DatabaseDialogs";
import { databaseColumns } from "./databaseColumns";
import type { DatabaseAction } from "./databaseActions";
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
 * Every write is asynchronous: Nest answers 202, so the ids each mutation
 * returns go to `watch()` and are polled until terminal. The operations panel
 * is fed from those results rather than a listing because Nest exposes no
 * operation collection at this service.
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
      description="Managed databases, volumes and object stores."
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
          <DrawerActions
            onAction={setConfirming}
            onDelete={() => setDeleting(selected)}
          />
        }
      />

      <CreateDatabaseModal
        isOpen={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={submit}
      />

      <ActionConfirmDialog
        action={confirming}
        database={selected}
        isLoading={act.isPending}
        onConfirm={() => confirming && runAction(confirming)}
        onCancel={() => setConfirming(null)}
      />

      <DeleteConfirmDialog
        database={deleting}
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
      />
    </NestScreen>
  );
}
