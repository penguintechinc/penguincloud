import { registerPageExtension } from "../ExtensionRegistry";
import { registerDetailTabExtension } from "../ExtensionDetailTabRegistry";

/**
 * Nest's extension-slot registrations — imported once, for its side effect,
 * from `main.tsx` before the app renders (the same "imported once at app
 * start" contract `components/extensions/tobogganing/register.ts` follows
 * for its own cell-slot registration).
 *
 * Registers under `"nest.billing"` (page) and `"nest.health"` (detail_tab),
 * matching `adapters/nest/manifest.py`'s declared
 * `ExtensionSlot(slot="page", id="billing")` /
 * `ExtensionSlot(slot="detail_tab", id="health", resource="database")`.
 */
registerPageExtension("nest", "billing", () => import("./BillingPanel"));
registerDetailTabExtension(
  "nest",
  "health",
  () => import("./DatabaseHealthTab"),
);
