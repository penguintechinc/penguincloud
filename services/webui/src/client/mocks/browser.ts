/**
 * MSW browser worker, used by the E2E smoke run and by `VITE_MOCKS=true` dev.
 *
 * Kept separate from mocks/server.ts (jest/node) because importing msw/browser
 * in a node test environment pulls in a service-worker registration that has
 * nowhere to attach.
 */

import { setupWorker } from "msw/browser";
import { handlers } from "./handlers";

export const worker = setupWorker(...handlers);

/**
 * Starts the worker when mocks are enabled, and resolves to whether it did.
 * Unhandled requests pass through so a missing handler surfaces as a real
 * (failing) request rather than being silently absorbed.
 */
export async function startMocks(enabled: boolean): Promise<boolean> {
  if (!enabled) return false;

  await worker.start({
    onUnhandledRequest: "bypass",
    quiet: true,
    serviceWorker: { url: "/mockServiceWorker.js" },
  });
  console.log("[Mocks] Worker started { handlers:", handlers.length, "}");
  return true;
}
