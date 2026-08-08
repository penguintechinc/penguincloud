import { useState } from "react";
import {
  ConfirmDialog,
  DataTable,
  DetailDrawer,
} from "../../../components/kit";
import { goughApi } from "../../../api/resources/gough";
import { GoughScreen } from "./GoughScreen";
import { OperationsPanel } from "./OperationsPanel";
import { nodeColumns } from "./nodeColumns";
import { FactList, RowOpenButtons } from "./FactList";
import { ActionButton } from "./ActionButton";
import { NODE_ACTIONS, type NodeAction } from "./nodeActions";
import { useGoughMutation, useGoughNodes } from "./useGough";
import type { GoughNode } from "./types";

/**
 * Gough node fleet.
 *
 * Ported from Gough's own Provisioning MachinesPage, restyled to portal theme
 * tokens. The one structural difference is the action set: the brief called
 * for power actions, and Gough's api-manager registers none. Its fleet verbs
 * are `deploy` (commissions hardware), `evacuate` (drains it) and `reject`
 * (removes it) — all destructive, so every one is behind a danger-variant
 * ConfirmDialog and requires `products:gough:manage`.
 */
export default function NodesPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useGoughNodes();
  const [selected, setSelected] = useState<GoughNode | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [pending, setPending] = useState<NodeAction | null>(null);

  const action = useGoughMutation<{ nodeId: string; verb: NodeAction["verb"] }>(
    "nodes",
    (id, vars) => goughApi.nodeAction(id, vars.nodeId, vars.verb),
  );

  const rows = (data ?? []).map((node) => ({ ...node, id: String(node.id) }));

  const confirmAction = () => {
    if (!selected || !pending) return;
    action.mutate(
      { nodeId: String(selected.id), verb: pending.verb },
      {
        onSuccess: () => {
          setPending(null);
          setSelected(null);
        },
      },
    );
  };

  return (
    <GoughScreen
      title="Nodes"
      description="Physical machines under Gough management."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <OperationsPanel />

      <DataTable<GoughNode & { id: string }>
        columns={nodeColumns as never}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Gough nodes"
      />

      <RowOpenButtons
        rows={rows}
        label={(node) => node.name}
        onOpen={(node) => {
          setActiveTab("overview");
          setSelected(node);
        }}
        testIdPrefix="gough-node-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.name ?? ""}
        subtitle={selected ? `Node ${selected.id}` : undefined}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => setSelected(null)}
        testId="gough-node-drawer"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: selected ? (
              <FactList
                facts={[
                  ["State", selected.state],
                  ["Posture", selected.posture],
                  ["IPv4", selected.ipv4],
                  ["MAC", selected.primary_nic_mac],
                  ["Firmware", selected.firmware_type],
                  ["Discovered", selected.discovered_at],
                  ["Deployed", selected.deployed_at],
                ]}
              />
            ) : null,
          },
          {
            id: "tags",
            label: "Tags",
            content: (
              <p className="text-sm text-slate-300">
                {selected?.hardware_tags?.join(", ") || "No hardware tags."}
              </p>
            ),
          },
        ]}
        actions={NODE_ACTIONS.map((item) => (
          <ActionButton
            key={item.verb}
            label={item.label}
            variant="danger"
            onClick={() => setPending(item)}
            testId={`gough-node-action-${item.verb}`}
          />
        ))}
      />

      <ConfirmDialog
        isOpen={pending !== null}
        title={pending ? `${pending.label} node` : ""}
        message={
          pending && selected
            ? `${pending.confirmation} This affects node "${selected.name}".`
            : ""
        }
        confirmLabel={pending?.label}
        isDangerous
        isLoading={action.isPending}
        onConfirm={confirmAction}
        onCancel={() => setPending(null)}
        testId="gough-node-confirm"
      />
    </GoughScreen>
  );
}
