import type { TenantPlan } from "../types";
import { useTenantStore } from "../stores/tenantStore";
import { useLicenseTier, useTierOrder } from "../lib/featureGates";

/**
 * Hide a subtree unless the deployment's licence tier (and/or the tenant's
 * plan) allows it.
 *
 * Two different axes, deliberately separate props:
 *
 * - `requiredTier` — what this DEPLOYMENT is licensed for
 *   (community/professional/enterprise), from `GET /api/v1/features`. This is
 *   the axis the portal's own gates enforce server-side.
 * - `requiredPlan` — what THIS TENANT pays for (free/starter/business/
 *   enterprise), from the tenant record. A single deployment can hold tenants
 *   on different plans, so this cannot be folded into the tier.
 *
 * Both are UX only. The server refuses an unentitled call regardless of what
 * the browser renders — `require_feature` / `require_tier` answer 403 with the
 * required and current tier named, and this component exists so the operator
 * sees the upgrade path before making the call rather than after.
 */

interface LicenseGateProps {
  /** Minimum licence tier, e.g. `"professional"`. */
  requiredTier?: string;
  requiredPlan?: TenantPlan;
  requiredPlans?: TenantPlan[];
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

const PLAN_HIERARCHY: TenantPlan[] = [
  "free",
  "starter",
  "business",
  "enterprise",
];

export default function LicenseGate({
  requiredTier,
  requiredPlan,
  requiredPlans,
  children,
  fallback,
}: LicenseGateProps) {
  const { currentTenant } = useTenantStore();
  const currentTier = useLicenseTier();
  const tierOrder = useTierOrder();

  const currentPlan = currentTenant?.plan || "free";

  if (requiredTier) {
    const currentIndex = tierOrder.indexOf(currentTier);
    const requiredIndex = tierOrder.indexOf(requiredTier);
    // A tier the server did not publish is treated as unreachable rather
    // than as "no requirement": a typo in a gate must hide the feature, not
    // reveal it. `indexOf` returns -1 for both sides, so an unknown CURRENT
    // tier also fails, which is the same fail-closed direction.
    if (requiredIndex === -1 || currentIndex < requiredIndex) {
      return (
        <>{fallback || <UpgradeNotice tiers={[requiredTier]} label="tier" />}</>
      );
    }
  }

  if (requiredPlans) {
    if (!requiredPlans.includes(currentPlan)) {
      return <>{fallback || <UpgradeNotice tiers={requiredPlans} />}</>;
    }
    return <>{children}</>;
  }

  if (requiredPlan) {
    const currentIndex = PLAN_HIERARCHY.indexOf(currentPlan);
    const requiredIndex = PLAN_HIERARCHY.indexOf(requiredPlan);
    if (currentIndex < requiredIndex) {
      return <>{fallback || <UpgradeNotice tiers={[requiredPlan]} />}</>;
    }
  }

  return <>{children}</>;
}

function UpgradeNotice({
  tiers,
  label = "plan",
}: {
  tiers: string[];
  label?: string;
}) {
  return (
    <div className="card p-6 text-center border-dashed border-slate-600">
      <div className="text-slate-400 mb-2">
        This feature requires an upgraded {label}.
      </div>
      <div className="text-sm text-slate-500">
        Available on:{" "}
        {tiers.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(", ")}
      </div>
    </div>
  );
}
