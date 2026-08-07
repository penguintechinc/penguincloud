/**
 * Two-level tenant scope switcher: provider org → customer tenants.
 *
 * The roster is server state (TanStack Query). Performing the switch — the
 * POST, the token swap, the new active scope — belongs to tenantStore, so this
 * component only decides *when* to switch and reflects the result in the URL.
 */

import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router";
import { useTenantStore } from "../../stores/tenantStore";
import { useTenants } from "../../hooks/useTenants";
import { groupTenants, filterGroups } from "./tenantGrouping";
import { TenantScopeMenu } from "./TenantScopeMenu";

export function TenantScopeSwitcher() {
  const [searchParams, setSearchParams] = useSearchParams();
  const currentTenant = useTenantStore((state) => state.currentTenant);
  const switchTenant = useTenantStore((state) => state.switchTenant);
  const tenantsQuery = useTenants();
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

  const tenants = tenantsQuery.data ?? [];

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

  const filteredGroups = filterGroups(groupTenants(tenants), searchQuery);

  async function handleSelect(tenantId: number) {
    const switched = await switchTenant(tenantId);
    if (!switched) {
      // Scope did not change — leave the menu open so the operator can retry
      // rather than silently appearing to have switched.
      console.log("[TenantScopeSwitcher] Switch rejected { id:", tenantId, "}");
      return;
    }

    const newParams = new URLSearchParams(searchParams);
    newParams.set("tenant", String(tenantId));
    setSearchParams(newParams);

    setIsOpen(false);
    setSearchQuery("");
  }

  return (
    <div
      className="relative"
      ref={dropdownRef}
      data-testid="tenant-scope-switcher"
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm bg-slate-800 border border-slate-700 rounded-lg hover:border-amber-400/50 transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500"
        data-testid="tenant-switcher-button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <span className="text-amber-400 truncate font-medium">
          {currentTenant?.display_name ||
            currentTenant?.name ||
            "Select Tenant"}
        </span>
        <span className="text-slate-400 ml-2" aria-hidden="true">
          {isOpen ? "▲" : "▼"}
        </span>
      </button>

      {isOpen && (
        <TenantScopeMenu
          groups={filteredGroups}
          currentTenantId={currentTenant?.id}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          onSelect={handleSelect}
        />
      )}
    </div>
  );
}
