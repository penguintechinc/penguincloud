import { useState, useRef, useEffect } from 'react';
import { useTenantStore } from '../stores/tenantStore';

export default function TenantSwitcher() {
  const { tenants, currentTenant, switchTenant } = useTenantStore();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (tenants.length === 0) return null;

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm bg-dark-800 border border-dark-700 rounded-lg hover:border-gold-400/50 transition-colors"
      >
        <span className="text-gold-400 truncate">
          {currentTenant?.display_name || currentTenant?.name || 'Select Tenant'}
        </span>
        <span className="text-dark-400 ml-2">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-dark-800 border border-dark-700 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto">
          {tenants.map((tenant) => (
            <button
              key={tenant.id}
              onClick={() => {
                switchTenant(tenant.id);
                setIsOpen(false);
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-dark-700 transition-colors ${
                currentTenant?.id === tenant.id ? 'text-gold-400 bg-dark-700/50' : 'text-dark-300'
              }`}
            >
              <div className="font-medium truncate">{tenant.display_name || tenant.name}</div>
              <div className="text-xs text-dark-500">{tenant.slug} · {tenant.plan}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
