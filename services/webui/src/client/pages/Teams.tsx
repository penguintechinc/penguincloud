/**
 * Teams management page. Lists teams for the current user with details.
 */

import { useMemo } from "react";
import { useTenantStore } from "../stores/tenantStore";
import { DataTable } from "../components/kit/DataTable";
import { EmptyState } from "../components/kit/EmptyState";
import { useTeams } from "../hooks/useTeams";
import type { ColumnConfig } from "../components/kit/DataTable";
import type { Team } from "../hooks/useTeams";

export default function Teams() {
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const teamsQuery = useTeams(currentTenant?.id);

  const teams = useMemo(() => teamsQuery.data ?? [], [teamsQuery.data]);
  const error = teamsQuery.error as Error | null;

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

      {/*
        `error`/`isLoading` are wired straight into DataTable so its own
        loading > error > empty precedence decides what renders — the same
        pattern every Gough/Nest/Tobogganing list screen uses (see e.g.
        `pages/products/tobogganing/PeersPage.tsx`). Previously this page
        derived its own "teams.length === 0" empty state and never looked at
        `teamsQuery.error` at all, so a failed `/teams` request rendered "No
        teams yet" — a fact about a request that never returned data,
        printed as if it were a fact about the tenant. The custom
        `EmptyState` below is gated on `!error` for the same reason
        PeersPage's is: it must not render over a failure DataTable is
        already showing.
      */}
      <DataTable
        columns={columns}
        data={teams}
        isLoading={teamsQuery.isLoading}
        error={error}
        onRetry={() => void teamsQuery.refetch()}
        caption="Teams"
      />

      {!teamsQuery.isLoading && !error && teams.length === 0 && (
        <EmptyState
          title="No teams yet"
          description="Create one to organize your work."
          dataTestId="teams-empty"
        />
      )}
    </div>
  );
}
