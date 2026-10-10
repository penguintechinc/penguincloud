/**
 * Shared shapes for the two-step connection wizard.
 */

export interface ConnectionFormData {
  display_name: string;
  base_url: string;
  auth_type: string;
  api_key: string;
  api_secret: string;
  health_endpoint: string;
  api_version: string;
}

export const EMPTY_CONNECTION_FORM: ConnectionFormData = {
  display_name: "",
  base_url: "",
  auth_type: "bearer",
  api_key: "",
  api_secret: "",
  health_endpoint: "/healthz",
  api_version: "v1",
};
