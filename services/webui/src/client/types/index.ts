// User types
export type UserRole = "admin" | "maintainer" | "viewer";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
  home_tenant_id?: number; // Introduced in Phase 2B
}

export interface CreateUserData {
  email: string;
  password: string;
  full_name: string;
  role: UserRole;
}

export interface UpdateUserData {
  email?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}

// Auth types
export interface LoginCredentials {
  email: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

// API Response types
export interface ApiResponse<T> {
  data?: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// Navigation types
export interface NavItem {
  label: string;
  path: string;
  icon?: string;
  roles?: UserRole[];
}

export interface NavCategory {
  label: string;
  items: NavItem[];
  roles?: UserRole[];
}

// Tab types
export interface Tab {
  id: string;
  label: string;
  content?: React.ReactNode;
}

// Tenant types
export type TenantPlan = "free" | "starter" | "business" | "enterprise";
export type TenantRole = "owner" | "admin" | "member" | "viewer";
export type HealthStatus = "healthy" | "degraded" | "unhealthy" | "unknown";

export type TenantKind = "provider" | "customer";

export interface Tenant {
  id: number;
  name: string;
  slug: string;
  display_name: string;
  owner_id: number;
  plan: TenantPlan;
  max_users: number;
  max_products: number;
  settings: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  user_role?: TenantRole;
  // Introduced in Phase 2B (hierarchical tenancy)
  parent_tenant_id?: number | null;
  kind?: TenantKind;
  depth?: number;
}

export interface TenantMember {
  id: number;
  tenant_id: number;
  user_id: number;
  role: TenantRole;
  invited_by_id: number | null;
  joined_at: string;
  user_email?: string;
  user_full_name?: string;
}

export interface ProductType {
  product_type: string;
  display_name: string;
  category: string;
  icon: string;
  default_health_endpoint: string;
  default_api_version: string;
  discovery_ports: number[];
}

export interface ProductConnection {
  id: number;
  tenant_id: number;
  product_type: string;
  display_name: string;
  base_url: string;
  api_key: string;
  api_secret: string;
  auth_type: string;
  health_endpoint: string;
  api_version: string;
  is_active: boolean;
  last_health_check: string | null;
  health_status: HealthStatus;
  discovered: boolean;
  metadata_json: string | null;
  created_at: string;
  updated_at: string;
}

export interface TenantUsage {
  tenant_id: number;
  plan: TenantPlan;
  usage: {
    members: { current: number; max: number };
    products: { current: number; max: number };
  };
}

export interface DashboardOverview {
  tenant: { id: number; name: string; plan: string };
  stats: {
    total_products: number;
    total_members: number;
    health: Record<HealthStatus, number>;
    categories: Record<string, number>;
  };
  products: ProductConnection[];
}

/**
 * One row of the provider rollup: a customer tenant and the status of every
 * product connected to it. Shape per Task 2B `GET /api/v1/dashboard/rollup`.
 */
export interface DashboardRollupRow {
  tenant_id: string;
  tenant_name: string;
  products: Array<{
    connection_id: string;
    product: string;
    status: HealthStatus;
  }>;
}

export interface AuditLog {
  id: number;
  user_id: number;
  action: string;
  resource_type: string;
  resource_id: string;
  tenant_id: number | null;
  product_connection_id: number | null;
  ip_address: string;
  created_at: string;
}

export interface DiscoveredProduct {
  id: number;
  product_type: string;
  display_name: string;
  base_url: string;
  health_endpoint: string;
  status_code: number;
  response_time_ms: number;
  unconfirmed?: boolean;
}

export interface ProductManagementSchema {
  product_type: string;
  display_name: string;
  sections: Array<{
    id: string;
    label: string;
    type?: string;
    endpoint?: string;
  }>;
}
