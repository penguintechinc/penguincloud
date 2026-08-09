import { useState } from "react";
import {
  DataTable,
  DetailDrawer,
  FactList,
  RowOpenButtons,
} from "../../../components/kit";
import { TobogganingScreen } from "./TobogganingScreen";
import { clientColumns } from "./clientColumns";
import { useTobogganingClients } from "./useTobogganing";
import type { TobogganingClient } from "./types";

/**
 * SD-WAN clients enrolled with Tobogganing.
 *
 * Read-only, and that is a property of the product rather than a phase
 * boundary. Every mutating client route is refused by the proxy allowlist for
 * a stated reason:
 *
 * - `POST /sdwan/clients` and `POST /sdwan/clients/{id}/rotate-key` return a
 *   freshly minted `api_key` in the response body. Proxying either would turn
 *   the portal into a credential-minting oracle.
 * - `PUT .../tunnel-config` and `GET .../config` authenticate a client's own
 *   api_key inline rather than by decorator, so a portal credential is not the
 *   right identity for them at all.
 *
 * So there is no create button and no delete verb here, and their absence is
 * asserted rather than left to be read as unfinished work.
 */
export default function ClientsPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useTobogganingClients();
  const [selected, setSelected] = useState<TobogganingClient | null>(null);
  const [activeTab, setActiveTab] = useState("overview");

  const rows = (data ?? []).map((client) => ({
    ...client,
    id: String(client.id),
  }));

  return (
    <TobogganingScreen
      title="SD-WAN Clients"
      description="Clients enrolled with this tenant's Tobogganing fabric."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <DataTable<TobogganingClient & { id: string }>
        columns={clientColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Tobogganing SD-WAN clients"
      />

      <RowOpenButtons
        rows={rows}
        label={(client) => client.name || client.id}
        onOpen={(client) => {
          setActiveTab("overview");
          setSelected(client);
        }}
        testIdPrefix="tobogganing-client-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.name || selected?.id || ""}
        subtitle={selected ? `Client ${selected.id}` : undefined}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => setSelected(null)}
        testId="tobogganing-client-drawer"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: selected ? (
              <FactList
                testId="tobogganing-facts"
                facts={[
                  ["Status", selected.status],
                  ["Type", selected.type],
                  ["Cluster", selected.cluster_id],
                  ["Last seen", selected.last_seen],
                ]}
              />
            ) : null,
          },
        ]}
      />
    </TobogganingScreen>
  );
}
