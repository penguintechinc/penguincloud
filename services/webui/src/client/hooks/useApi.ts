/**
 * Re-export surface for the API resource modules.
 *
 * The implementations live in `src/client/api/resources/*` — one module per
 * backend resource — and this barrel keeps the long-standing
 * `hooks/useApi` import path stable for the ~27 call sites that use it.
 * Add new endpoints to the resource module, never here.
 */

export { usersApi } from "../api/resources/users";
export { tenantsApi } from "../api/resources/tenants";
export { productsApi, discoveryApi, proxyApi } from "../api/resources/products";
export { dashboardApi, auditApi } from "../api/resources/dashboard";
export { helloApi, goApi } from "../api/resources/platform";
