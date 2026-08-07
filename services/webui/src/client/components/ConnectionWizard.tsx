import { useState } from "react";
import { useProductTypes, useRegisterProduct } from "../hooks/useProducts";
import type { ProductConnection, ProductType } from "../types";

interface ConnectionWizardProps {
  /** Tenant the new connection is registered under. */
  tenantId: number;
  /** Receives the newly created connection so callers can route to it. */
  onComplete: (product: ProductConnection) => void;
  onCancel: () => void;
}

export default function ConnectionWizard({
  tenantId,
  onComplete,
  onCancel,
}: ConnectionWizardProps) {
  const productTypes = useProductTypes().data ?? [];
  const registerProduct = useRegisterProduct().mutateAsync;
  const [step, setStep] = useState(1);
  const [selectedType, setSelectedType] = useState<ProductType | null>(null);
  const [formData, setFormData] = useState({
    display_name: "",
    base_url: "",
    auth_type: "bearer",
    api_key: "",
    api_secret: "",
    health_endpoint: "/healthz",
    api_version: "v1",
  });
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!selectedType) return;
    setIsSubmitting(true);
    setError("");

    try {
      const product = await registerProduct({
        tenant_id: tenantId,
        product_type: selectedType.product_type,
        ...formData,
      });
      onComplete(product);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to register product",
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Group product types by category
  const categories: Record<string, ProductType[]> = {};
  productTypes.forEach((pt) => {
    if (!categories[pt.category]) categories[pt.category] = [];
    categories[pt.category].push(pt);
  });

  return (
    <div className="card p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-bold text-amber-400 mb-4">
        Connect a Product — Step {step} of 2
      </h2>

      {step === 1 && (
        <div>
          <p className="text-slate-400 mb-4">
            Select the product type to connect:
          </p>
          {Object.entries(categories).map(([category, types]) => (
            <div key={category} className="mb-4">
              <h3 className="text-sm font-medium text-slate-400 uppercase mb-2">
                {category}
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {types.map((pt) => (
                  <button
                    key={pt.product_type}
                    onClick={() => {
                      setSelectedType(pt);
                      setFormData((prev) => ({
                        ...prev,
                        display_name: pt.display_name,
                        health_endpoint: pt.default_health_endpoint,
                        api_version: pt.default_api_version,
                      }));
                      setStep(2);
                    }}
                    className={`text-left p-3 rounded-lg border transition-colors ${
                      selectedType?.product_type === pt.product_type
                        ? "border-amber-400 bg-slate-800"
                        : "border-slate-700 hover:border-slate-600"
                    }`}
                  >
                    <div className="text-sm font-medium text-amber-400">
                      {pt.display_name}
                    </div>
                    <div className="text-xs text-slate-500">{pt.category}</div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">
              Display Name
            </label>
            <input
              type="text"
              value={formData.display_name}
              onChange={(e) =>
                setFormData({ ...formData, display_name: e.target.value })
              }
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">
              Base URL
            </label>
            <input
              type="url"
              placeholder="https://product.example.com"
              value={formData.base_url}
              onChange={(e) =>
                setFormData({ ...formData, base_url: e.target.value })
              }
              className="input w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">
              Auth Type
            </label>
            <select
              value={formData.auth_type}
              onChange={(e) =>
                setFormData({ ...formData, auth_type: e.target.value })
              }
              className="input w-full"
            >
              <option value="bearer">Bearer Token</option>
              <option value="api_key">API Key</option>
              <option value="basic">Basic Auth</option>
              <option value="none">None</option>
            </select>
          </div>
          {formData.auth_type !== "none" && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                API Key / Token
              </label>
              <input
                type="password"
                value={formData.api_key}
                onChange={(e) =>
                  setFormData({ ...formData, api_key: e.target.value })
                }
                className="input w-full"
              />
            </div>
          )}
          {formData.auth_type === "basic" && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                API Secret / Password
              </label>
              <input
                type="password"
                value={formData.api_secret}
                onChange={(e) =>
                  setFormData({ ...formData, api_secret: e.target.value })
                }
                className="input w-full"
              />
            </div>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                Health Endpoint
              </label>
              <input
                type="text"
                value={formData.health_endpoint}
                onChange={(e) =>
                  setFormData({ ...formData, health_endpoint: e.target.value })
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">
                API Version
              </label>
              <input
                type="text"
                value={formData.api_version}
                onChange={(e) =>
                  setFormData({ ...formData, api_version: e.target.value })
                }
                className="input w-full"
              />
            </div>
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="flex gap-3 pt-2">
            <button onClick={() => setStep(1)} className="btn btn-secondary">
              Back
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !formData.base_url}
              className="btn btn-primary flex-1"
            >
              {isSubmitting ? "Connecting..." : "Connect Product"}
            </button>
          </div>
        </div>
      )}

      <button
        onClick={onCancel}
        className="mt-4 text-sm text-slate-400 hover:text-slate-300"
      >
        Cancel
      </button>
    </div>
  );
}
