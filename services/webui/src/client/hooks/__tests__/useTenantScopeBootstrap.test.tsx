/**
 * Tenant scope bootstrap tests.
 *
 * Without this hook a freshly logged-in operator lands on the dashboard with
 * no active tenant and sees the "create or select a tenant" prompt instead of
 * their own data — which is exactly what happened when the roster moved out of
 * the store and took its auto-select side effect with it.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { useTenantScopeBootstrap } from "../useTenantScopeBootstrap";
import { useTenantStore } from "../../stores/tenantStore";
import { useTenants } from "../useTenants";
import { useAuth } from "../useAuth";
import type { Tenant } from "../../types";

jest.mock("../../stores/tenantStore");
jest.mock("../useTenants");
jest.mock("../useAuth");

const setCurrentTenant = jest.fn();
const switchTenant = jest.fn(() => Promise.resolve(true));

const tenants = [
  { id: 1, name: "Provider A" },
  { id: 11, name: "Customer One" },
] as unknown as Tenant[];

function setStore(currentTenant: Tenant | null) {
  (useTenantStore as unknown as jest.Mock).mockImplementation(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector({ currentTenant, setCurrentTenant, switchTenant }),
  );
}

describe("useTenantScopeBootstrap", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setStore(null);
    (useTenants as jest.Mock).mockReturnValue({ data: tenants });
    (useAuth as jest.Mock).mockReturnValue({ user: { home_tenant_id: 1 } });
  });

  it("adopts the home tenant without a round trip", async () => {
    renderHook(() => useTenantScopeBootstrap());

    await waitFor(() =>
      expect(setCurrentTenant).toHaveBeenCalledWith(tenants[0]),
    );
    expect(switchTenant).not.toHaveBeenCalled();
  });

  it("switches into the first tenant when the home tenant is absent", async () => {
    (useAuth as jest.Mock).mockReturnValue({ user: { home_tenant_id: 999 } });

    renderHook(() => useTenantScopeBootstrap());

    // The token is not scoped to this tenant, so it must be re-issued.
    await waitFor(() => expect(switchTenant).toHaveBeenCalledWith(1));
    expect(setCurrentTenant).not.toHaveBeenCalled();
  });

  it("switches when the user has no home tenant at all", async () => {
    (useAuth as jest.Mock).mockReturnValue({ user: {} });

    renderHook(() => useTenantScopeBootstrap());

    await waitFor(() => expect(switchTenant).toHaveBeenCalledWith(1));
  });

  it("leaves an already-active scope alone", () => {
    setStore(tenants[1]);

    renderHook(() => useTenantScopeBootstrap());

    expect(setCurrentTenant).not.toHaveBeenCalled();
    expect(switchTenant).not.toHaveBeenCalled();
  });

  it("waits for the roster to load", () => {
    (useTenants as jest.Mock).mockReturnValue({ data: undefined });

    renderHook(() => useTenantScopeBootstrap());

    expect(setCurrentTenant).not.toHaveBeenCalled();
    expect(switchTenant).not.toHaveBeenCalled();
  });

  it("does nothing when the roster is empty", () => {
    (useTenants as jest.Mock).mockReturnValue({ data: [] });

    renderHook(() => useTenantScopeBootstrap());

    expect(setCurrentTenant).not.toHaveBeenCalled();
    expect(switchTenant).not.toHaveBeenCalled();
  });

  it("tolerates no signed-in user", () => {
    (useAuth as jest.Mock).mockReturnValue({ user: null });

    renderHook(() => useTenantScopeBootstrap());

    expect(switchTenant).toHaveBeenCalledWith(1);
  });
});
