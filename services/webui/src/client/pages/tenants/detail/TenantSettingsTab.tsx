/**
 * Settings tab of the tenant detail page: rename, change plan, delete.
 * Split out of TenantDetail.tsx to keep each file focused and under the
 * 5000-character limit.
 */

import { useState } from "react";
import Card from "../../../components/Card";
import { ConfirmDialog } from "../../../components/kit/ConfirmDialog";
import { toTenantPlan } from "../../../lib/formValues";
import type { Tenant, TenantPlan } from "../../../types";

interface TenantSettingsTabProps {
  tenant: Tenant;
  onSave: (data: { display_name: string; plan: TenantPlan }) => void;
  onDelete: () => void;
  isSaving: boolean;
}

export default function TenantSettingsTab({
  tenant,
  onSave,
  onDelete,
  isSaving,
}: TenantSettingsTabProps) {
  const [form, setForm] = useState<{ display_name: string; plan: TenantPlan }>({
    display_name: tenant.display_name || "",
    plan: tenant.plan,
  });
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  return (
    <Card title="Tenant Settings">
      <div className="space-y-4">
        <div>
          <label
            htmlFor="tenant-display-name"
            className="block text-sm text-slate-300 mb-1"
          >
            Display Name
          </label>
          <input
            id="tenant-display-name"
            type="text"
            value={form.display_name}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, display_name: e.target.value }))
            }
            className="input w-full"
          />
        </div>
        <div>
          <label
            htmlFor="tenant-plan"
            className="block text-sm text-slate-300 mb-1"
          >
            Plan
          </label>
          <select
            id="tenant-plan"
            value={form.plan}
            onChange={(e) =>
              setForm((prev) => ({
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
          <button
            onClick={() => onSave(form)}
            disabled={isSaving}
            className="btn btn-primary"
          >
            {isSaving ? "Saving..." : "Save Changes"}
          </button>
          <button
            onClick={() => setConfirmingDelete(true)}
            className="btn btn-danger"
          >
            Delete Tenant
          </button>
        </div>
      </div>

      <ConfirmDialog
        isOpen={confirmingDelete}
        title="Delete tenant"
        message={`Delete ${tenant.display_name || tenant.name}? This cannot be undone.`}
        confirmLabel="Delete"
        isDangerous
        onConfirm={() => {
          setConfirmingDelete(false);
          onDelete();
        }}
        onCancel={() => setConfirmingDelete(false)}
      />
    </Card>
  );
}
