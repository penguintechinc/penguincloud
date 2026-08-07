/**
 * Dropdown body of the tenant scope switcher: search box plus the two-level
 * provider/customer option list. Presentational — selection is handled by the
 * parent switcher.
 */

import type { TenantGroup } from "./tenantGrouping";

interface TenantScopeMenuProps {
  groups: TenantGroup[];
  currentTenantId: number | undefined;
  searchQuery: string;
  onSearchChange: (value: string) => void;
  onSelect: (tenantId: number | string) => void;
}

function optionClasses(isCurrent: boolean, indent: boolean): string {
  return [
    "w-full text-left py-2 text-sm hover:bg-slate-700 transition-colors",
    "focus:outline-none focus:ring-2 focus:ring-sky-500",
    indent ? "px-6" : "px-3",
    isCurrent ? "text-amber-400 bg-slate-700/50 font-medium" : "text-slate-300",
  ].join(" ");
}

function CurrentMarker() {
  return (
    <span className="text-xs text-amber-400 inline-block mt-1">✓ Current</span>
  );
}

export function TenantScopeMenu({
  groups,
  currentTenantId,
  searchQuery,
  onSearchChange,
  onSelect,
}: TenantScopeMenuProps) {
  return (
    <div className="absolute top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-lg z-50 max-h-80 overflow-hidden flex flex-col">
      <div className="p-2 border-b border-slate-700">
        <input
          type="text"
          placeholder="Search tenants..."
          aria-label="Search tenants"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full px-2 py-1 text-sm bg-slate-700 border border-slate-600 rounded text-amber-400 placeholder-slate-500 focus:outline-none focus:border-amber-400"
          data-testid="tenant-switcher-search"
          autoFocus
        />
      </div>

      <div className="overflow-y-auto flex-1">
        {groups.length === 0 ? (
          <div className="px-3 py-2 text-sm text-slate-400">
            No tenants found
          </div>
        ) : (
          groups.map((group) => (
            <div
              key={group.tenantId}
              className="border-b border-slate-700 last:border-b-0"
            >
              <button
                onClick={() => onSelect(group.tenantId)}
                className={optionClasses(
                  currentTenantId === group.tenantId,
                  false,
                )}
                data-testid={`tenant-option-${group.tenantId}`}
              >
                <div className="font-semibold">{group.name}</div>
                {currentTenantId === group.tenantId && <CurrentMarker />}
              </button>

              {group.children.length > 0 && (
                <div className="bg-slate-800/50">
                  {/* "All customers" aggregate option — visible only to delegated admin */}
                  {group.userRole === "admin" && (
                    <button
                      onClick={() => onSelect(`aggregate:${group.tenantId}`)}
                      className={optionClasses(false, true)}
                      data-testid={`tenant-option-aggregate-${group.tenantId}`}
                    >
                      <div className="truncate italic text-sky-400">
                        All customers
                      </div>
                    </button>
                  )}

                  {group.children.map((child) => (
                    <button
                      key={child.tenantId}
                      onClick={() => onSelect(child.tenantId)}
                      className={optionClasses(
                        currentTenantId === child.tenantId,
                        true,
                      )}
                      data-testid={`tenant-option-${child.tenantId}`}
                    >
                      <div className="truncate">{child.name}</div>
                      {currentTenantId === child.tenantId && <CurrentMarker />}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
