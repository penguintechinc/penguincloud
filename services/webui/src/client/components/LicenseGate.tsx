import type { TenantPlan } from "../types";
import { useTenantStore } from "../stores/tenantStore";

interface LicenseGateProps {
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
  requiredPlan,
  requiredPlans,
  children,
  fallback,
}: LicenseGateProps) {
  const { currentTenant } = useTenantStore();

  const currentPlan = currentTenant?.plan || "free";

  if (requiredPlans) {
    if (!requiredPlans.includes(currentPlan)) {
      return <>{fallback || <UpgradeNotice plans={requiredPlans} />}</>;
    }
    return <>{children}</>;
  }

  if (requiredPlan) {
    const currentIndex = PLAN_HIERARCHY.indexOf(currentPlan);
    const requiredIndex = PLAN_HIERARCHY.indexOf(requiredPlan);
    if (currentIndex < requiredIndex) {
      return <>{fallback || <UpgradeNotice plans={[requiredPlan]} />}</>;
    }
  }

  return <>{children}</>;
}

function UpgradeNotice({ plans }: { plans: TenantPlan[] }) {
  return (
    <div className="card p-6 text-center border-dashed border-slate-600">
      <div className="text-slate-400 mb-2">
        This feature requires an upgraded plan.
      </div>
      <div className="text-sm text-slate-500">
        Available on:{" "}
        {plans.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(", ")}
      </div>
    </div>
  );
}
