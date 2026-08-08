import { useNavigate } from "react-router";
import Card from "../../components/Card";
import { isProductEnabled } from "../../lib/featureGates";
import { useGoughAgents, useGoughNodes } from "../products/gough/useGough";
import { useGoughOperations } from "../products/gough/useGoughOperations";

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
 * Counts come from the resource lists rather than a `total` field: Gough's
 * `total` is the length of the page it just serialised, not the collection
 * size, so reading it would report the page size as the fleet size.
 */
export default function GoughSummaryCard() {
  const navigate = useNavigate();
  const nodes = useGoughNodes();
  const agents = useGoughAgents();
  const operations = useGoughOperations();

  if (!isProductEnabled("gough") || nodes.productId === undefined) return null;

  const nodeRows = nodes.data ?? [];
  const ready = nodeRows.filter((node) => node.state === "ready").length;
  const live = (operations.data ?? []).filter((op) => !op.is_terminal).length;

  return (
    <Card title="Gough">
      <div
        className="grid grid-cols-4 gap-4"
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
