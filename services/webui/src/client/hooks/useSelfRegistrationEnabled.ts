/**
 * Whether this deployment currently allows self-service signup — the one
 * boolean the login page needs before a visitor has a token.
 *
 * A plain effect, not a TanStack Query hook: every other data hook in this
 * app (`useFeatures`, `useTenants`, ...) assumes a `QueryClientProvider`
 * ancestor, which is true everywhere EXCEPT here — `/login` is the one
 * screen that renders before authentication resolves anything, and is
 * exercised in tests with no provider tree at all. Reaching for `useQuery`
 * here would mean either wrapping the whole app's provider around a page
 * that doesn't otherwise need it, or duplicating one just for this hook;
 * a bare `useEffect` avoids both for a single fire-once GET.
 */

import { useEffect, useState } from "react";
import { helloApi } from "../api/resources/platform";

/**
 * Fails CLOSED. The initial state, the still-loading state, and any error
 * (network failure, a portal that has not deployed this route yet) all
 * resolve to `false` — no sign-up button — and only an explicit `true` from
 * the server flips it. `Config.ALLOW_SELF_REGISTRATION` defaults closed
 * server-side for the same reason (`app/config.py`): an unreachable answer
 * must never be MORE permissive than the deployment's own default, or an
 * outage becomes a way to make a disabled sign-up button reappear.
 */
export function useSelfRegistrationEnabled(): boolean {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    let cancelled = false;

    helloApi
      .registrationStatus()
      .then((status) => {
        if (!cancelled) setEnabled(status.selfRegistrationEnabled);
      })
      .catch(() => {
        if (!cancelled) setEnabled(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return enabled;
}
