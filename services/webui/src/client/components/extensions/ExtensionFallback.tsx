import { EmptyState } from "../kit/EmptyState";

export interface ExtensionFallbackProps {
  /**
   * The slot's declared label, or the raw extension id from the URL when no
   * matching manifest slot could be resolved at all (e.g. a stale link).
   */
  label: string;
}

/**
 * The generic "extension not available" panel — Design §3.4: a `page` slot
 * with no matching registry entry, or a URL naming a slot the active
 * manifest no longer declares, degrades to THIS, never a blank page.
 * "Silence must never read as success."
 *
 * Reuses `EmptyState` rather than a bespoke panel so this reads exactly like
 * every other gated/empty state already in the console (`ProductScreen`'s
 * flag/connection gates, `ProductResourceRoute`'s fallback shell).
 */
export function ExtensionFallback({ label }: ExtensionFallbackProps) {
  return (
    <EmptyState
      title={`${label} is not available`}
      description="This extension is not installed in this deployment."
      dataTestId="extension-fallback"
    />
  );
}
