import { useState } from "react";
import { FormModalBuilder } from "@penguintechinc/react-libs";
import {
  ConfirmDialog,
  DataTable,
  DetailDrawer,
  ActionButton,
  FactList,
  RowOpenButtons,
} from "../../../components/kit";
import { GoughScreen } from "./GoughScreen";
import { OperationsPanel } from "./OperationsPanel";
import { biomeColumns, biomeFields } from "./biomeColumns";
import { useGoughBiomes } from "./useGough";
import { useDeleteBiome, useSaveBiome } from "./useBiomeMutations";
import type { GoughBiome, GoughBiomeRow } from "./types";

/**
 * Gough biomes — deployable workload definitions.
 *
 * Full CRUD: create/edit via FormModalBuilder, delete behind a danger
 * ConfirmDialog. Every mutating call needs `products:gough:manage`.
 */
export default function BiomesPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useGoughBiomes();
  const [selected, setSelected] = useState<GoughBiome | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<GoughBiome | null>(null);
  const [deleting, setDeleting] = useState<GoughBiome | null>(null);

  const save = useSaveBiome();
  const remove = useDeleteBiome();

  const rows = (data ?? []).map((biome) => ({
    ...biome,
    id: String(biome.id),
  }));

  const submit = async (values: Record<string, unknown>): Promise<void> => {
    await save.mutateAsync({
      id: editing ? String(editing.id) : null,
      payload: values,
    });
    setFormOpen(false);
    setEditing(null);
  };

  return (
    <GoughScreen
      title="Biomes"
      description="Deployable workload definitions assigned to nodes."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <OperationsPanel />

      <div className="mb-4 flex justify-end">
        <ActionButton
          label="New biome"
          onClick={() => {
            setEditing(null);
            setFormOpen(true);
          }}
          testId="gough-biome-create"
        />
      </div>

      <DataTable<GoughBiomeRow>
        columns={biomeColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Gough biomes"
      />

      <RowOpenButtons
        rows={rows}
        label={(biome) => biome.name}
        onOpen={(biome) => {
          setActiveTab("overview");
          setSelected(biome);
        }}
        testIdPrefix="gough-biome-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.name ?? ""}
        subtitle={selected ? `Biome ${selected.id}` : undefined}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => setSelected(null)}
        testId="gough-biome-drawer"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: selected ? (
              <FactList
                testId="gough-facts"
                facts={[
                  ["Kind", selected.biome_kind],
                  ["Workload", selected.workload_type],
                  ["Version", selected.version],
                  ["Phase", selected.phase],
                ]}
              />
            ) : null,
          },
        ]}
        actions={
          <>
            <ActionButton
              label="Edit"
              onClick={() => {
                setEditing(selected);
                setFormOpen(true);
              }}
              testId="gough-biome-edit"
            />
            <ActionButton
              label="Delete"
              variant="danger"
              onClick={() => setDeleting(selected)}
              testId="gough-biome-delete"
            />
          </>
        }
      />

      <FormModalBuilder
        title={editing ? "Edit biome" : "New biome"}
        fields={biomeFields}
        isOpen={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        onSubmit={submit}
        submitButtonText={editing ? "Save" : "Create"}
      />

      <ConfirmDialog
        isOpen={deleting !== null}
        title="Delete biome"
        message={
          deleting
            ? `Deleting "${deleting.name}" removes the definition. Nodes already running it are not reverted.`
            : ""
        }
        confirmLabel="Delete"
        isDangerous
        isLoading={remove.isPending}
        onConfirm={() => {
          if (!deleting) return;
          remove.mutate(
            { id: String(deleting.id) },
            {
              onSuccess: () => {
                setDeleting(null);
                setSelected(null);
              },
            },
          );
        }}
        onCancel={() => setDeleting(null)}
        testId="gough-biome-confirm"
      />
    </GoughScreen>
  );
}
