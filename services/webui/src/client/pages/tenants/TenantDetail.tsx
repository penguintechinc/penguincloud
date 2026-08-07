import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router";
import { tenantsApi } from "../../hooks/useApi";
import Card from "../../components/Card";
import TabNavigation from "../../components/TabNavigation";
import type {
  Tenant,
  TenantMember,
  TenantPlan,
  TenantUsage,
} from "../../types";
import { toTenantPlan } from "../../lib/formValues";

const tabs = [
  { id: "settings", label: "Settings" },
  { id: "members", label: "Members" },
  { id: "usage", label: "Usage" },
];

export default function TenantDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("settings");
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [members, setMembers] = useState<TenantMember[]>([]);
  const [usage, setUsage] = useState<TenantUsage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [editForm, setEditForm] = useState<{
    display_name: string;
    plan: TenantPlan;
  }>({ display_name: "", plan: "free" });

  const tenantId = Number(id);

  useEffect(() => {
    const fetchTenant = async () => {
      setIsLoading(true);
      try {
        const t = await tenantsApi.get(tenantId);
        setTenant(t);
        setEditForm({ display_name: t.display_name || "", plan: t.plan });
      } catch (err) {
        console.error("Failed to fetch tenant:", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchTenant();
  }, [tenantId]);

  useEffect(() => {
    if (activeTab === "members") {
      tenantsApi
        .getMembers(tenantId)
        .then((res) => setMembers(res.members))
        .catch(console.error);
    } else if (activeTab === "usage") {
      tenantsApi.getUsage(tenantId).then(setUsage).catch(console.error);
    }
  }, [activeTab, tenantId]);

  const handleSave = async () => {
    try {
      const updated = await tenantsApi.update(tenantId, editForm);
      setTenant(updated);
    } catch (err) {
      console.error("Failed to update tenant:", err);
    }
  };

  const handleDelete = async () => {
    if (
      !confirm(
        "Are you sure you want to delete this tenant? This action cannot be undone.",
      )
    )
      return;
    try {
      await tenantsApi.delete(tenantId);
      navigate("/tenants");
    } catch (err) {
      console.error("Failed to delete tenant:", err);
    }
  };

  const handleRemoveMember = async (userId: number) => {
    try {
      await tenantsApi.removeMember(tenantId, userId);
      setMembers((prev) => prev.filter((m) => m.user_id !== userId));
    } catch (err) {
      console.error("Failed to remove member:", err);
    }
  };

  if (isLoading) {
    return <div className="animate-pulse h-64 bg-slate-700 rounded" />;
  }

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
          <Card title="Tenant Settings">
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 mb-1">
                  Display Name
                </label>
                <input
                  type="text"
                  value={editForm.display_name}
                  onChange={(e) =>
                    setEditForm((prev) => ({
                      ...prev,
                      display_name: e.target.value,
                    }))
                  }
                  className="input w-full"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">
                  Plan
                </label>
                <select
                  value={editForm.plan}
                  onChange={(e) =>
                    setEditForm((prev) => ({
                      ...prev,
                      plan: toTenantPlan(e.target.value),
                    }))
                  }
                  className="input w-full"
                >
                  <option value="free">Free</option>
                  <option value="starter">Starter</option>
                  <option value="business">Business</option>
                  <option value="enterprise">Enterprise</option>
                </select>
              </div>
              <div className="flex gap-3">
                <button onClick={handleSave} className="btn btn-primary">
                  Save Changes
                </button>
                <button onClick={handleDelete} className="btn btn-danger">
                  Delete Tenant
                </button>
              </div>
            </div>
          </Card>
        )}

        {activeTab === "members" && (
          <Card title="Team Members">
            {members.length === 0 ? (
              <p className="text-slate-400">No members found.</p>
            ) : (
              <div className="space-y-2">
                {members.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center justify-between py-2 border-b border-slate-800 last:border-0"
                  >
                    <div>
                      <span className="text-slate-200">
                        {member.user_email || `User #${member.user_id}`}
                      </span>
                      <span className={`badge badge-${member.role} ml-2`}>
                        {member.role}
                      </span>
                    </div>
                    <button
                      onClick={() => handleRemoveMember(member.user_id)}
                      className="text-sm text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}

        {activeTab === "usage" && (
          <Card title="Resource Usage">
            {usage ? (
              // Iterates the nested `usage` map rather than the top-level
              // response: the response also carries tenant_id and plan, and its
              // `usage` value is an object that previously rendered as
              // "[object Object]".
              <div className="grid grid-cols-2 gap-4">
                {Object.entries(usage.usage).map(([key, quota]) => (
                  <div key={key} className="p-3 bg-slate-800 rounded">
                    <div className="text-sm text-slate-400">
                      {key.replace(/_/g, " ")}
                    </div>
                    <div className="text-lg font-bold text-amber-400">
                      {quota.current} / {quota.max}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-400">Loading usage data...</p>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
