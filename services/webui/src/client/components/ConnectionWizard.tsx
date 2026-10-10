/**
 * Two-step wizard for registering a product connection.
 * Step bodies live in ./connectionWizard/; this file owns wizard state and the
 * registration mutation.
 */

import { useState } from "react";
import { useProductTypes, useRegisterProduct } from "../hooks/useProducts";
import ProductTypePicker from "./connectionWizard/ProductTypePicker";
import ConnectionDetailsForm from "./connectionWizard/ConnectionDetailsForm";
import {
  EMPTY_CONNECTION_FORM,
  type ConnectionFormData,
} from "./connectionWizard/types";
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
  const registerProduct = useRegisterProduct();
  const [step, setStep] = useState(1);
  const [selectedType, setSelectedType] = useState<ProductType | null>(null);
  const [formData, setFormData] = useState<ConnectionFormData>(
    EMPTY_CONNECTION_FORM,
  );
  const [error, setError] = useState("");

  const handleSelectType = (pt: ProductType) => {
    setSelectedType(pt);
    setFormData((prev) => ({
      ...prev,
      display_name: pt.display_name,
      health_endpoint: pt.default_health_endpoint,
      api_version: pt.default_api_version,
    }));
    setStep(2);
  };

  const handleSubmit = async () => {
    if (!selectedType) return;
    setError("");
    try {
      const product = await registerProduct.mutateAsync({
        tenant_id: tenantId,
        product_type: selectedType.product_type,
        ...formData,
      });
      onComplete(product);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to register product",
      );
    }
  };

  return (
    <div className="card p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-bold text-amber-400 mb-4">
        Connect a Product — Step {step} of 2
      </h2>

      {step === 1 && (
        <ProductTypePicker
          productTypes={productTypes}
          selectedType={selectedType}
          onSelect={handleSelectType}
        />
      )}

      {step === 2 && (
        <ConnectionDetailsForm
          formData={formData}
          onChange={(patch) => setFormData((prev) => ({ ...prev, ...patch }))}
          onBack={() => setStep(1)}
          onSubmit={handleSubmit}
          isSubmitting={registerProduct.isPending}
          error={error}
        />
      )}

      <button
        onClick={onCancel}
        className="mt-4 text-sm text-slate-400 hover:text-slate-300 focus:ring-2 focus:ring-sky-500 rounded"
      >
        Cancel
      </button>
    </div>
  );
}
