import { useDevMode } from "../lib/featureGates";

/**
 * Persistent notice that this deployment is running unlicensed in `--dev`.
 *
 * Deliberately NOT dismissible. general.md requires a persistent banner
 * rather than a toast because the person who needs to see it is usually not
 * the person who started the process — someone opening the portal has no
 * other way to learn that every premium capability they are looking at is
 * unlocked without a licence. A dismissible banner is a banner that is gone
 * by the time it matters.
 *
 * The signal is server-side only (`dev_mode` from `GET /api/v1/features`).
 * The browser never infers it: two of the three activation conditions are
 * the deployment domain and the user count, and a count a client could
 * influence is not a count.
 */
export default function DevModeBanner() {
  const { active, maxUsers } = useDevMode();

  if (!active) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="dev-mode-banner"
      className="w-full bg-amber-500/15 border-b border-amber-500/60 px-4 py-2 text-amber-300"
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
        <span className="font-semibold uppercase tracking-wide">
          Development mode
        </span>
        <span className="text-amber-200/90">
          All premium features are unlocked for evaluation, limited to{" "}
          {maxUsers} user. Using this mode to obtain licensed functionality
          without a valid commercial licence breaches the PenguinTech licence
          terms.
        </span>
      </div>
    </div>
  );
}
