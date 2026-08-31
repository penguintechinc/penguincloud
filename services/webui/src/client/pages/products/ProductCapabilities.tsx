import { EmptyState } from "../../components/kit";
import type { ProductManagementSchema } from "../../types";

/** Load state for the capabilities schema, kept distinct from `null` so an
 * unreachable adapter (`schema_status: "unavailable"`) never renders
 * identically to "loading" or to a product that genuinely has nothing to
 * report. */
export type SchemaState =
  | { status: "loading" }
  | { status: "loaded"; schema: ProductManagementSchema }
  | { status: "error" };

/**
 * Renders the capabilities panel for the honest interim state: the console
 * has no manifest-driven per-capability screens yet (Phase 8 Step 3), so a
 * non-empty capability list is shown as read-only names, not clickable tabs
 * that imply a working screen behind them.
 */
export default function ProductCapabilities({
  schemaState,
}: {
  schemaState: SchemaState;
}) {
  if (schemaState.status === "loading") {
    return (
      <div
        className="animate-pulse h-24 bg-slate-700 rounded"
        data-testid="product-capabilities-loading"
      />
    );
  }

  if (schemaState.status === "error") {
    return (
      <EmptyState
        title="Capabilities unavailable"
        description="The console could not reach this product's adapter to list its capabilities. Try again shortly."
        dataTestId="product-capabilities-error"
      />
    );
  }

  const { capabilities } = schemaState.schema;

  if (capabilities.length === 0) {
    return (
      <EmptyState
        title="No management screens yet"
        description="This product is connected, but the console does not yet have screens for it."
        dataTestId="product-capabilities-empty"
      />
    );
  }

  return (
    <div data-testid="product-capabilities-list">
      <p className="text-slate-400 mb-4">
        This product is connected, but the console does not yet have management
        screens for these capabilities:
      </p>
      <div className="flex flex-wrap gap-2">
        {capabilities.map((capability) => (
          <span
            key={capability}
            className="px-2 py-1 bg-slate-800 rounded text-sm text-slate-300"
          >
            {capability}
          </span>
        ))}
      </div>
    </div>
  );
}
