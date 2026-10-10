import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

/** One selectable tab inside a drawer. */
export interface DetailDrawerTab {
  id: string;
  label: string;
  content: ReactNode;
}

export interface DetailDrawerProps {
  isOpen: boolean;
  title: string;
  subtitle?: string;
  tabs: DetailDrawerTab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  onClose: () => void;
  /** Rendered in the footer — destructive actions belong here. */
  actions?: ReactNode;
  testId?: string;
}

/**
 * Slide-over panel showing one row's detail, with tabbed sections.
 *
 * Companion to DataTable: the table answers "what is there", the drawer
 * answers "what is this one", without navigating away and losing the
 * operator's filter and scroll position.
 *
 * Escape closes, as in ConfirmDialog. The close button takes focus on open
 * so a keyboard user is never stranded behind the backdrop.
 */
export function DetailDrawer({
  isOpen,
  title,
  subtitle,
  tabs,
  activeTab,
  onTabChange,
  onClose,
  actions,
  testId = "detail-drawer",
}: DetailDrawerProps) {
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", handleKeyDown);
    closeBtnRef.current?.focus();

    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const current = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  return (
    <>
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
        data-testid={`${testId}-backdrop`}
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${testId}-title`}
        className="fixed inset-y-0 right-0 z-50 w-full max-w-xl bg-slate-800 border-l border-slate-700 shadow-lg flex flex-col"
        data-testid={testId}
      >
        <div className="flex items-start justify-between gap-4 p-6 border-b border-slate-700">
          <div className="min-w-0">
            <h2
              id={`${testId}-title`}
              className="text-lg font-semibold text-amber-400 truncate"
            >
              {title}
            </h2>
            {subtitle && (
              <p className="text-sm text-slate-400 truncate">{subtitle}</p>
            )}
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            aria-label="Close details"
            data-testid={`${testId}-close`}
            className="p-1 rounded text-slate-400 hover:text-amber-400 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        {tabs.length > 1 && (
          <div
            role="tablist"
            aria-label="Detail sections"
            className="flex gap-1 px-6 border-b border-slate-700"
          >
            {tabs.map((tab) => {
              const isActive = tab.id === current?.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => onTabChange(tab.id)}
                  data-testid={`${testId}-tab-${tab.id}`}
                  className={`px-3 py-2 text-sm border-b-2 transition-colors focus:ring-2 focus:ring-sky-500 focus:outline-none ${
                    isActive
                      ? "border-sky-500 text-sky-400"
                      : "border-transparent text-amber-500 hover:text-amber-400"
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        )}

        <div
          role="tabpanel"
          className="flex-1 overflow-y-auto p-6"
          data-testid={`${testId}-panel`}
        >
          {current?.content}
        </div>

        {actions && (
          <div className="flex flex-wrap gap-2 justify-end p-6 border-t border-slate-700">
            {actions}
          </div>
        )}
      </div>
    </>
  );
}
