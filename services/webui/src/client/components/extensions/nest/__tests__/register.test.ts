/**
 * Nest's extension registrations — proves the actual wiring (the real
 * `register.ts` resolving against the real `BillingPanel`/`DatabaseHealthTab`
 * default exports), not a synthetic stand-in, mirroring
 * `tobogganing/register.ts`'s own registration proof.
 */
import { resolveExtension, clearPageExtensions } from "../../ExtensionRegistry";
import {
  resolveDetailTabExtension,
  clearDetailTabExtensions,
} from "../../ExtensionDetailTabRegistry";
import "../register";

afterAll(() => {
  clearPageExtensions();
  clearDetailTabExtensions();
});

it('registers the Billing panel under "nest.billing"', async () => {
  const loader = resolveExtension("nest", "billing");

  expect(loader).toBeDefined();
  const module = await loader?.();
  expect(module?.default.name).toBe("BillingPanel");
});

it('registers the Health tab under "nest.health"', async () => {
  const loader = resolveDetailTabExtension("nest", "health");

  expect(loader).toBeDefined();
  const module = await loader?.();
  expect(module?.default.name).toBe("DatabaseHealthTab");
});
