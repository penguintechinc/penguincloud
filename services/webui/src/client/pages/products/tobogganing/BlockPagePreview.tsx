/**
 * Rendered preview of a block page.
 *
 * **The HTML is never injected into the portal's own document.** It arrives
 * from `POST /sase/blockpages/pages/{id}/preview`, which runs the product's
 * markdown renderer over operator-authored source. `dangerouslySetInnerHTML`
 * would execute anything that renderer emits — including a `<script>` or an
 * `onerror` handler surviving from the markdown — inside the portal's origin,
 * with the portal operator's session. A block page is authored by whoever can
 * write SASE config for a tenant, which is not the same trust level as the
 * portal itself, and the page is proxied through a connection whose upstream
 * the portal does not control.
 *
 * It is rendered in a fully sandboxed iframe instead: `sandbox=""` grants
 * nothing back, so scripts do not run and the frame is a unique opaque origin
 * with no access to the parent document, cookies or storage. `srcDoc` keeps
 * the content in-memory rather than fetching a URL, so no second request is
 * made and no referrer leaks.
 *
 * Omitting `allow-scripts` is the load-bearing part. `sandbox="allow-scripts
 * allow-same-origin"` would be strictly WORSE than no sandbox, because the two
 * together let framed content remove its own sandbox attribute.
 */

interface BlockPagePreviewProps {
  html: string | null;
  isLoading: boolean;
  error: Error | null;
}

export function BlockPagePreview({
  html,
  isLoading,
  error,
}: BlockPagePreviewProps) {
  if (isLoading) {
    return (
      <div
        className="animate-pulse h-64 bg-slate-700 rounded"
        data-testid="tobogganing-preview-loading"
      />
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className="bg-red-900 border border-red-700 text-red-100 px-4 py-3 rounded"
        data-testid="tobogganing-preview-error"
      >
        <p className="font-semibold">Could not render a preview</p>
        <p className="text-sm mt-1">{error.message}</p>
      </div>
    );
  }

  if (html === null) {
    return (
      <p
        className="text-slate-400 text-sm"
        data-testid="tobogganing-preview-idle"
      >
        Choose Preview to render this page with sample values.
      </p>
    );
  }

  return (
    <iframe
      title="Block page preview"
      data-testid="tobogganing-preview-frame"
      // Empty sandbox: no scripts, no same-origin, no forms, no popups.
      // Never add allow-scripts alongside allow-same-origin — together they
      // let the frame drop its own sandbox.
      sandbox=""
      srcDoc={html}
      className="w-full h-96 bg-white rounded border border-slate-600"
    />
  );
}
