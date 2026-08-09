import { useState } from "react";
import {
  DataTable,
  DetailDrawer,
  FactList,
  RowOpenButtons,
} from "../../../components/kit";
import { TobogganingScreen } from "./TobogganingScreen";
import { clusterColumns } from "./clusterColumns";
import { useTobogganingClusters } from "./useTobogganing";
import type { TobogganingCluster } from "./types";

/**
 * SD-WAN clusters — the headend groups clients attach to.
 *
 * Reads `GET /api/v1/sdwan/clusters`, which is registered WITHOUT a trailing
 * slash. Tobogganing also serves `GET /api/v1/clusters/` — a different route,
 * registered WITH one, and both are `strict_slashes=True`. The two read alike
 * and fail in opposite directions (404 vs a 308 the portal transport does not
 * follow), so the path is taken from `tobogganingPaths.ts` and pinned against
 * the adapter rather than spelled by eye. See task-4T-report.md.
 *
 * Read-only for the same reason the clients screen is: `POST /sdwan/clusters`
 * returns a freshly minted `api_key`, and the heartbeat and headend-config
 * routes authenticate a node credential rather than the portal's. All are
 * refused by the proxy allowlist.
 */
export default function ClustersPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useTobogganingClusters();
  const [selected, setSelected] = useState<TobogganingCluster | null>(null);
  const [activeTab, setActiveTab] = useState("overview");

  const rows = (data ?? []).map((cluster) => ({
    ...cluster,
    id: String(cluster.id),
  }));

  return (
    <TobogganingScreen
      title="SD-WAN Clusters"
      description="Headend clusters serving this tenant's clients."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <DataTable<TobogganingCluster & { id: string }>
        columns={clusterColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Tobogganing SD-WAN clusters"
      />

      <RowOpenButtons
        rows={rows}
        label={(cluster) => cluster.name || cluster.id}
        onOpen={(cluster) => {
          setActiveTab("overview");
          setSelected(cluster);
        }}
        testIdPrefix="tobogganing-cluster-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.name || selected?.id || ""}
        subtitle={selected ? `Cluster ${selected.id}` : undefined}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => setSelected(null)}
        testId="tobogganing-cluster-drawer"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: selected ? (
              <FactList
                testId="tobogganing-facts"
                facts={[
                  ["Status", selected.status],
                  ["Region", selected.region],
                  ["Datacenter", selected.datacenter],
                  [
                    "Clients",
                    typeof selected.client_count === "number"
                      ? String(selected.client_count)
                      : null,
                  ],
                ]}
              />
            ) : null,
          },
        ]}
      />
    </TobogganingScreen>
  );
}
