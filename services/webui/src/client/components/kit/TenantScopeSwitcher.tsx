/**
 * TenantScopeSwitcher — Two-level hierarchical dropdown for provider org → customer tenants.
 * Calls POST /api/v1/tenants/{id}/switch, updates token, syncs zustand store, reflects in URL.
 */

import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router";
import { useTenantStore } from "../../stores/tenantStore";
import api from "../../lib/api";

interface TenantGroup {
  tenantId: number;
  name: string;
  children: Array<{ tenantId: number; name: string }>;
}

export function TenantScopeSwitcher() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { tenants, currentTenant, setCurrentTenant } = useTenantStore();
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (tenants.length === 0) {
    return (
      <button
        className="w-full px-3 py-2 text-sm bg-slate-800 border border-slate-700 rounded-lg text-slate-400"
        disabled
        data-testid="tenant-switcher-empty"
      >
        No tenants available
      </button>
    );
  }

  // Group tenants by provider (parent_tenant_id: null = provider, children = customers)
  const groupedTenants: TenantGroup[] = tenants
    .filter((t) => !t.parent_tenant_id) // Only providers at top level
    .map((provider) => ({
      tenantId: provider.id,
      name: provider.display_name || provider.name,
      children: tenants
        .filter((t) => t.parent_tenant_id === provider.id)
        .map((customer) => ({
          tenantId: customer.id,
          name: customer.display_name || customer.name,
        })),
    }));

  // Filter based on search query
  const filteredGroups = groupedTenants
    .map((group) => ({
      ...group,
      children: group.children.filter((child) =>
        child.name.toLowerCase().includes(searchQuery.toLowerCase()),
      ),
    }))
    .filter(
      (group) =>
        group.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        group.children.length > 0,
    );

  async function switchTenant(tenantId: number) {
    try {
      const response = await api.post(`/tenants/${tenantId}/switch`);
      const { access_token, tenant } = response.data;

      // Update token in localStorage + api client
      const { setTokens } = await import("../../lib/api");
      const refreshToken =
        localStorage.getItem("penguincloud_refresh_token") || "";
      setTokens(access_token, refreshToken);

      // Update zustand store
      setCurrentTenant(tenant);

      // Update URL ?tenant= param
      const newParams = new URLSearchParams(searchParams);
      newParams.set("tenant", String(tenantId));
      setSearchParams(newParams);

      setIsOpen(false);
      setSearchQuery("");
    } catch (error) {
      console.error("[TenantScopeSwitcher] Failed to switch tenant:", error);
    }
  }

  return (
    <div
      className="relative"
      ref={dropdownRef}
      data-testid="tenant-scope-switcher"
    >
      {/* Trigger button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm bg-slate-800 border border-slate-700 rounded-lg hover:border-amber-400/50 transition-colors"
        data-testid="tenant-switcher-button"
      >
        <span className="text-amber-400 truncate font-medium">
          {currentTenant?.display_name ||
            currentTenant?.name ||
            "Select Tenant"}
        </span>
        <span className="text-slate-400 ml-2">{isOpen ? "▲" : "▼"}</span>
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50 max-h-80 overflow-hidden flex flex-col">
          {/* Search input */}
          <div className="p-2 border-b border-slate-700">
            <input
              type="text"
              placeholder="Search tenants..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-2 py-1 text-sm bg-slate-700 border border-slate-600 rounded text-amber-400 placeholder-slate-500 focus:outline-none focus:border-amber-400"
              data-testid="tenant-switcher-search"
              autoFocus
            />
          </div>

          {/* Tenant groups */}
          <div className="overflow-y-auto flex-1">
            {filteredGroups.length === 0 ? (
              <div className="px-3 py-2 text-sm text-slate-400">
                No tenants found
              </div>
            ) : (
              filteredGroups.map((group) => (
                <div
                  key={group.tenantId}
                  className="border-b border-slate-700 last:border-b-0"
                >
                  {/* Provider header (clickable) */}
                  <button
                    onClick={() => switchTenant(group.tenantId)}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-slate-700 transition-colors ${
                      currentTenant?.id === group.tenantId
                        ? "text-amber-400 bg-slate-700/50 font-medium"
                        : "text-slate-300"
                    }`}
                    data-testid={`tenant-option-${group.tenantId}`}
                  >
                    <div className="font-semibold">{group.name}</div>
                    {currentTenant?.id === group.tenantId && (
                      <span className="text-xs text-amber-400 inline-block mt-1">
                        ✓ Current
                      </span>
                    )}
                  </button>

                  {/* Customer tenants (indented) */}
                  {group.children.length > 0 && (
                    <div className="bg-slate-800/50">
                      {group.children.map((child) => (
                        <button
                          key={child.tenantId}
                          onClick={() => switchTenant(child.tenantId)}
                          className={`w-full text-left px-6 py-2 text-sm hover:bg-slate-700 transition-colors ${
                            currentTenant?.id === child.tenantId
                              ? "text-amber-400 bg-slate-700/50 font-medium"
                              : "text-slate-300"
                          }`}
                          data-testid={`tenant-option-${child.tenantId}`}
                        >
                          <div className="truncate">{child.name}</div>
                          {currentTenant?.id === child.tenantId && (
                            <span className="text-xs text-amber-400 inline-block mt-1">
                              ✓ Current
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
