import { useState } from "react";
import {
  ConfirmDialog,
  DataTable,
  DetailDrawer,
  ActionButton,
  FactList,
  RowOpenButtons,
} from "../../../components/kit";
import { goughOperationsApi } from "../../../api/resources/goughOperations";
import { GoughScreen } from "./GoughScreen";
import { OperationsPanel } from "./OperationsPanel";
import { agentColumns } from "./agentColumns";
import { useGoughAgents, useGoughMutation } from "./useGough";
import type { GoughAgent, GoughAgentRow } from "./types";

type AgentVerb = "suspend" | "resume";

/**
 * Gough access agents.
 *
 * Agents are addressed by `agent_id` (the UUID Gough's detail and
 * suspend/resume routes take), never the numeric row id — using the row id
 * builds a list whose every action 404s.
 *
 * Enrollment is deliberately absent from this screen. Gough's enrollment
 * routes (`/agents/enroll`, `/agents/enrollment-keys`) hand out credentials
 * and are explicitly NOT in the portal's proxy allowlist, so there is nothing
 * here to call. That exclusion is asserted in test_gough_allowlist.py.
 */
export default function AgentsPage() {
  const { data, isLoading, error, productId, isConnectionLoading, refetch } =
    useGoughAgents();
  const [selected, setSelected] = useState<GoughAgent | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [pending, setPending] = useState<AgentVerb | null>(null);

  const action = useGoughMutation<{ agentId: string; verb: AgentVerb }>(
    "agents",
    // Typed portal route — same action surface as nodes, so a caller does
    // not have to know which verbs happen to start background work.
    (id, vars) =>
      goughOperationsApi.performAction(id, "agents", vars.agentId, vars.verb),
  );

  const rows = (data ?? []).map((agent) => ({
    ...agent,
    id: String(agent.agent_id ?? agent.id),
  }));

  return (
    <GoughScreen
      title="Agents"
      description="Enrolled access agents reporting to Gough."
      productId={productId}
      isConnectionLoading={isConnectionLoading}
    >
      <OperationsPanel />

      <DataTable<GoughAgentRow>
        columns={agentColumns}
        data={rows}
        isLoading={isLoading}
        error={error as Error | null}
        onRetry={() => void refetch()}
        caption="Gough agents"
      />

      <RowOpenButtons
        rows={rows}
        label={(agent) => agent.hostname || agent.id}
        onOpen={(agent) => {
          setActiveTab("overview");
          setSelected(agent);
        }}
        testIdPrefix="gough-agent-open"
      />

      <DetailDrawer
        isOpen={selected !== null}
        title={selected?.hostname || selected?.id || ""}
        subtitle={
          selected ? `Agent ${selected.agent_id ?? selected.id}` : undefined
        }
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onClose={() => setSelected(null)}
        testId="gough-agent-drawer"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: selected ? (
              <FactList
                testId="gough-facts"
                facts={[
                  ["Status", selected.status],
                  ["IP address", selected.ip_address],
                  ["Last heartbeat", selected.last_heartbeat],
                  ["Enrolled", selected.enrolled_at],
                ]}
              />
            ) : null,
          },
        ]}
        actions={
          <>
            <ActionButton
              label="Suspend"
              variant="danger"
              onClick={() => setPending("suspend")}
              testId="gough-agent-suspend"
            />
            <ActionButton
              label="Resume"
              onClick={() => setPending("resume")}
              testId="gough-agent-resume"
            />
          </>
        }
      />

      <ConfirmDialog
        isOpen={pending !== null}
        title={pending === "suspend" ? "Suspend agent" : "Resume agent"}
        message={
          pending === "suspend"
            ? "Suspending stops this agent from acting until it is resumed."
            : "Resuming returns this agent to service."
        }
        confirmLabel={pending === "suspend" ? "Suspend" : "Resume"}
        // Suspend cuts an agent off; resume restores normal service. Only the
        // first warrants the danger styling.
        isDangerous={pending === "suspend"}
        isLoading={action.isPending}
        onConfirm={() => {
          if (!selected || !pending) return;
          action.mutate(
            {
              agentId: String(selected.agent_id ?? selected.id),
              verb: pending,
            },
            {
              onSuccess: () => {
                setPending(null);
                setSelected(null);
              },
            },
          );
        }}
        onCancel={() => setPending(null)}
        testId="gough-agent-confirm"
      />
    </GoughScreen>
  );
}
