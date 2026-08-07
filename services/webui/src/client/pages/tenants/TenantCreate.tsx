import { useState } from "react";
import { useNavigate } from "react-router";
import { useTenantStore } from "../../stores/tenantStore";
import Card from "../../components/Card";

export default function TenantCreate() {
  const navigate = useNavigate();
  const { createTenant } = useTenantStore();
  const [form, setForm] = useState({
    name: "",
    slug: "",
    display_name: "",
    plan: "free",
  });
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSlugify = (name: string) => {
    const slug = name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
    setForm((prev) => ({ ...prev, name, slug }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      const tenant = await createTenant(form);
      navigate(`/tenants/${tenant.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create tenant");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-2xl font-bold text-amber-400 mb-6">Create Tenant</h1>

      <Card title="Tenant Details">
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 bg-red-900/30 border border-red-700 rounded text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm text-slate-300 mb-1">
              Organization Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => handleSlugify(e.target.value)}
              className="input w-full"
              placeholder="My Organization"
              required
            />
          </div>

          <div>
            <label className="block text-sm text-slate-300 mb-1">
              Slug (URL identifier)
            </label>
            <input
              type="text"
              value={form.slug}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, slug: e.target.value }))
              }
              className="input w-full"
              placeholder="my-organization"
              required
              pattern="[a-z0-9-]+"
            />
            <p className="text-xs text-slate-500 mt-1">
              Lowercase letters, numbers, and hyphens only
            </p>
          </div>

          <div>
            <label className="block text-sm text-slate-300 mb-1">
              Display Name (optional)
            </label>
            <input
              type="text"
              value={form.display_name}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, display_name: e.target.value }))
              }
              className="input w-full"
              placeholder="My Organization Inc."
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="btn btn-primary"
            >
              {isSubmitting ? "Creating..." : "Create Tenant"}
            </button>
            <button
              type="button"
              onClick={() => navigate("/tenants")}
              className="btn btn-secondary"
            >
              Cancel
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
