/**
 * Step 2 of the connection wizard: endpoint and credential details.
 * Credential inputs are type=password and are never logged.
 */

import type { ConnectionFormData } from "./types";

interface ConnectionDetailsFormProps {
  formData: ConnectionFormData;
  onChange: (patch: Partial<ConnectionFormData>) => void;
  onBack: () => void;
  onSubmit: () => void;
  isSubmitting: boolean;
  error: string;
}

export default function ConnectionDetailsForm({
  formData,
  onChange,
  onBack,
  onSubmit,
  isSubmitting,
  error,
}: ConnectionDetailsFormProps) {
  return (
    <div className="space-y-4">
      <div>
        <label htmlFor="cw-name" className="block text-sm text-slate-400 mb-1">
          Display Name
        </label>
        <input
          id="cw-name"
          type="text"
          value={formData.display_name}
          onChange={(e) => onChange({ display_name: e.target.value })}
          className="input w-full"
        />
      </div>
      <div>
        <label htmlFor="cw-url" className="block text-sm text-slate-400 mb-1">
          Base URL
        </label>
        <input
          id="cw-url"
          type="url"
          placeholder="https://product.example.com"
          value={formData.base_url}
          onChange={(e) => onChange({ base_url: e.target.value })}
          className="input w-full"
        />
      </div>
      <div>
        <label htmlFor="cw-auth" className="block text-sm text-slate-400 mb-1">
          Auth Type
        </label>
        <select
          id="cw-auth"
          value={formData.auth_type}
          onChange={(e) => onChange({ auth_type: e.target.value })}
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
          <label htmlFor="cw-key" className="block text-sm text-slate-400 mb-1">
            API Key / Token
          </label>
          <input
            id="cw-key"
            type="password"
            value={formData.api_key}
            onChange={(e) => onChange({ api_key: e.target.value })}
            className="input w-full"
          />
        </div>
      )}
      {formData.auth_type === "basic" && (
        <div>
          <label
            htmlFor="cw-secret"
            className="block text-sm text-slate-400 mb-1"
          >
            API Secret / Password
          </label>
          <input
            id="cw-secret"
            type="password"
            value={formData.api_secret}
            onChange={(e) => onChange({ api_secret: e.target.value })}
            className="input w-full"
          />
        </div>
      )}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label
            htmlFor="cw-health"
            className="block text-sm text-slate-400 mb-1"
          >
            Health Endpoint
          </label>
          <input
            id="cw-health"
            type="text"
            value={formData.health_endpoint}
            onChange={(e) => onChange({ health_endpoint: e.target.value })}
            className="input w-full"
          />
        </div>
        <div>
          <label
            htmlFor="cw-version"
            className="block text-sm text-slate-400 mb-1"
          >
            API Version
          </label>
          <input
            id="cw-version"
            type="text"
            value={formData.api_version}
            onChange={(e) => onChange({ api_version: e.target.value })}
            className="input w-full"
          />
        </div>
      </div>

      {error && (
        <p role="alert" className="text-red-400 text-sm">
          {error}
        </p>
      )}

      <div className="flex gap-3 pt-2">
        <button onClick={onBack} className="btn btn-secondary">
          Back
        </button>
        <button
          onClick={onSubmit}
          disabled={isSubmitting || !formData.base_url}
          className="btn btn-primary flex-1"
        >
          {isSubmitting ? "Connecting..." : "Connect Product"}
        </button>
      </div>
    </div>
  );
}
