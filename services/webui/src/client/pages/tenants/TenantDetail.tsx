/**
 * Tenant detail page — routes between the settings, members and usage tabs.
 * All server state is TanStack Query; the tab bodies live in ./detail/.
 */

import { useState } from "react";
import { useParams, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { tenantsApi } from "../../api/resources/tenants";
import { queryKeys } from "../../api/keys";
import { useUpdateTenant, useDeleteTenant } from "../../hooks/useTenants";
import TabNavigation from "../../components/TabNavigation";
import TenantSettingsTab from "./detail/TenantSettingsTab";
import TenantMembersTab from "./detail/TenantMembersTab";
import TenantUsageTab from "./detail/TenantUsageTab";

const tabs = [
  { id: "settings", label: "Settings" },
  { id: "members", label: "Members" },
  { id: "usage", label: "Usage" },
];

export default function TenantDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("settings");

  const tenantId = Number(id);
  const updateTenant = useUpdateTenant();
  const deleteTenant = useDeleteTenant();

  const tenantQuery = useQuery({
    queryKey: queryKeys.tenant(String(tenantId)),
    queryFn: () => tenantsApi.get(tenantId),
    enabled: Number.isFinite(tenantId),
  });

  if (tenantQuery.isLoading) {
    return <div className="animate-pulse h-64 bg-slate-700 rounded" />;
  }

  const tenant = tenantQuery.data;
  if (!tenant) {
    return <p className="text-slate-400">Tenant not found.</p>;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-400">
          {tenant.display_name || tenant.name}
        </h1>
        <p className="text-slate-400 mt-1">/{tenant.slug}</p>
      </div>

      <TabNavigation
        tabs={tabs}
        activeTab={activeTab}
        onChange={setActiveTab}
      />

      <div className="mt-6">
        {activeTab === "settings" && (
          <TenantSettingsTab
            tenant={tenant}
            isSaving={updateTenant.isPending}
            onSave={(data) => updateTenant.mutate({ id: tenantId, data })}
            onDelete={() =>
              deleteTenant.mutate(tenantId, {
                onSuccess: () => navigate("/tenants"),
              })
            }
          />
        )}

        {activeTab === "members" && <TenantMembersTab tenantId={tenantId} />}

        {activeTab === "usage" && <TenantUsageTab tenantId={tenantId} />}
      </div>
    </div>
  );
}
