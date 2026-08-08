import { useNavigate } from "react-router";
import Card from "../../components/Card";
import { isProductEnabled } from "../../lib/featureGates";
import { useGoughAgents, useGoughNodes } from "../products/gough/useGough";
import {
  useGoughMetrics,
  useGoughOperations,
} from "../products/gough/useGoughOperations";

/** One headline number. */
function Stat({
  label,
  value,
  tone = "text-amber-400",
}: {
  label: string;
  value: number | string;
  tone?: string;
}) {
  return (
    <div>
      <div className={`text-2xl font-bold ${tone}`}>{value}</div>
      <div className="text-xs text-slate-400">{label}</div>
    </div>
  );
}

/**
 * Gough fleet summary for the dashboard overview.
 *
 * Renders nothing at all when the flag is off or the tenant has no Gough
 * connection — the hooks stay disabled in that case, so an unconnected tenant
 * costs no requests rather than showing an empty card that implies the
 * product is present but idle.
 *
 * Where each number comes from, and why they differ
 * ------------------------------------------------
 * Queue depths come from `metrics_summary()` — the product's own `/metrics`
 * scrape, reached through `GET /products/{id}/metrics`. That endpoint was
 * added because the adapter had implemented and tested `metrics_summary`
 * since Phase 4G with nothing exposing it.
 *
 * Fleet counts still come from the resource lists, and that is a limitation of
 * the PRODUCT, not an oversight here. Gough's `/metrics` exposes no
 * fleet-size gauge at all: every metric it registers
 * (`services/api-manager/app/metrics.py`) is an operational or security
 * counter — queue depths, API error totals, latency, audit-chain failures.
 * There is no `gough_nodes`/`gough_agents`/`gough_biomes`. So the fleet tiles
 * cannot be sourced from metrics until Gough publishes such a gauge.
 *
 * The list-derived counts carry a real caveat worth knowing: a list page is
 * capped (Gough's `page_size` maxes at 500), so these are "nodes on the first
 * page", not a guaranteed fleet total. Gough's own `total` field is no better
 * — it is the length of the page it just serialised.
 */
export default function GoughSummaryCard() {
  const navigate = useNavigate();
  const nodes = useGoughNodes();
  const agents = useGoughAgents();
  const operations = useGoughOperations();
  const metrics = useGoughMetrics();

  if (!isProductEnabled("gough") || nodes.productId === undefined) return null;

  const nodeRows = nodes.data ?? [];
  const ready = nodeRows.filter((node) => node.state === "ready").length;
  const live = (operations.data ?? []).filter((op) => !op.is_terminal).length;

  // Real product metrics. Absent (rather than zero) when the scrape has not
  // landed yet — a confident "0" for an unknown value is the failure mode the
  // Operation contract already refuses for `progress`.
  const totals = metrics.data?.totals;
  const queued = totals?.["gough_provisioning_queue_depth"];
  const deployQueue = totals?.["gough_deployment_queue_depth"];
  const queueDepth =
    queued === undefined && deployQueue === undefined
      ? "—"
      : (queued ?? 0) + (deployQueue ?? 0);

  return (
    <Card title="Gough">
      <div
        className="grid grid-cols-5 gap-4"
        data-testid="gough-summary-card"
        aria-busy={nodes.isLoading}
      >
        <Stat label="Nodes" value={nodeRows.length} />
        <Stat label="Ready" value={ready} tone="text-emerald-400" />
        <Stat label="Agents" value={(agents.data ?? []).length} />
        <Stat
          label="Running ops"
          value={live}
          tone={live > 0 ? "text-sky-400" : "text-slate-400"}
        />
        <Stat
          label="Queue depth"
          value={queueDepth}
          tone={
            typeof queueDepth === "number" && queueDepth > 0
              ? "text-amber-400"
              : "text-slate-400"
          }
        />
      </div>
      <button
        type="button"
        onClick={() => void navigate("/products/gough/nodes")}
        data-testid="gough-summary-open"
        className="mt-3 text-sm text-sky-400 hover:text-sky-300 focus:ring-2 focus:ring-sky-500 focus:outline-none rounded"
      >
        View fleet →
      </button>
    </Card>
  );
}
