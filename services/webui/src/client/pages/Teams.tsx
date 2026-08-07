/**
 * Teams management page. Lists teams for the current user with details.
 */

import { useMemo } from "react";
import { useTenantStore } from "../stores/tenantStore";
import { DataTable } from "../components/kit/DataTable";
import { useTeams } from "../hooks/useTeams";
import type { ColumnConfig } from "../components/kit/DataTable";
import type { Team } from "../hooks/useTeams";

export default function Teams() {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const teamsQuery = useTeams(currentTenant?.id);

  const teams = useMemo(() => teamsQuery.data ?? [], [teamsQuery.data]);

  const columns: ColumnConfig<Team>[] = [
    {
      key: "name" as const,
      label: "Team Name",
    },
    {
      key: "slug" as const,
      label: "Slug",
      render: (value) => (
        <code className="text-xs text-slate-400">{value as string}</code>
      ),
    },
    {
      key: "created_at" as const,
      label: "Created",
      render: (value) => new Date(value as string).toLocaleDateString(),
    },
  ];

  if (teamsQuery.isLoading) {
    return <div className="text-amber-400">Loading teams...</div>;
  }

  if (!currentTenant) {
    return <div className="text-amber-400">No tenant selected</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-amber-400 mb-2">Teams</h2>
        <p className="text-slate-300">
          Manage teams within{" "}
          <span className="font-semibold">
            {currentTenant.display_name || currentTenant.name}
          </span>
        </p>
      </div>

      {teams.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 text-center text-slate-400">
          No teams yet. Create one to organize your work.
        </div>
      ) : (
        <DataTable columns={columns} data={teams} />
      )}
    </div>
  );
}
