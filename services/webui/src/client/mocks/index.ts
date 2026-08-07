/**
 * MSW mock setup exports.
 */

export { handlers } from "./handlers";
export { server } from "./server";
export {
  MOCK_TENANTS,
  MOCK_DASHBOARD_ROLLUP,
  MOCK_PRODUCTS_BY_TENANT,
  PROVIDER_ONE,
  PROVIDER_TWO,
  generateMockToken,
} from "./fixtures";
export { worker, startMocks } from "./browser";
export type {
  MockTenant,
  MockProduct,
  MockDashboardRollup,
  MockTokenPayload,
} from "./fixtures";
