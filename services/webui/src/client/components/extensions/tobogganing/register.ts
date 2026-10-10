import { registerCellExtension } from "../ExtensionCellRegistry";
import { SwgPolicyScopeCell } from "./SwgPolicyScopeCell";

/**
 * Tobogganing's cell-slot registrations — imported once, for its
 * side effect, from `main.tsx` before the app renders (the same "imported
 * once at app start" contract `ExtensionRegistry.ts`'s module doc
 * describes for page extensions). Registers under `"tobogganing.scope_id"`,
 * matching `tobogganing/manifest.py`'s declared
 * `ExtensionSlot(slot="cell", id="scope_id", resource="swg_policy")`.
 */
registerCellExtension("tobogganing", "scope_id", SwgPolicyScopeCell);
