/**
 * Overview tab: headline counters plus the per-category product breakdown.
 */

import Card from "../../components/Card";
import type { DashboardOverview } from "../../types";

interface OverviewTabProps {
  overview: DashboardOverview | undefined;
}

export default function OverviewTab({ overview }: OverviewTabProps) {
  const health = overview?.stats.health;
  const categories = overview?.stats.categories;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card title="Products">
          <div className="text-3xl font-bold text-amber-400">
            {overview?.stats.total_products || 0}
          </div>
          <div className="text-sm text-slate-400">Connected</div>
        </Card>
        <Card title="Members">
          <div className="text-3xl font-bold text-amber-400">
            {overview?.stats.total_members || 0}
          </div>
          <div className="text-sm text-slate-400">Team members</div>
        </Card>
        <Card title="Healthy">
          <div className="text-3xl font-bold text-green-400">
            {health?.healthy || 0}
          </div>
          <div className="text-sm text-slate-400">Products healthy</div>
        </Card>
        <Card title="Alerts">
          <div className="text-3xl font-bold text-red-400">
            {(health?.unhealthy || 0) + (health?.degraded || 0)}
          </div>
          <div className="text-sm text-slate-400">Need attention</div>
        </Card>
      </div>

      {categories && Object.keys(categories).length > 0 && (
        <Card title="Products by Category">
          <div className="flex flex-wrap gap-3">
            {Object.entries(categories).map(([cat, count]) => (
              <div
                key={cat}
                className="px-3 py-1 bg-slate-800 rounded-full text-sm"
              >
                <span className="text-slate-400">{cat}:</span>{" "}
                <span className="text-amber-400">{count}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
