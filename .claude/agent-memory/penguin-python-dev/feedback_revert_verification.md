---
name: feedback-revert-verification
description: On penguincloud, prove a regression test fails with its fix reverted — several tests here were green against the bug they claimed to cover
metadata:
  type: feedback
---

**A regression test is not done until you have reverted the fix and watched it
go red.** Run it, paste the failure, restore, re-run.

**Why:** Task 4G shipped multiple tests that were green against the very defect
they existed to cover, and the pattern repeats because each one looks correct:

* the jest suite pinned `toBe("api/v1/nodes")` — the *broken* path — so the
  C1 slash defect had coverage that asserted the bug;
* `FakeGough` routed on the `(method, path)` keys the tests supplied, and those
  keys were copied from what the adapter sent, so any path shape the adapter
  chose was correct **by construction**;
* the `%2f`/`%5c` guard's only test went through the Gough allowlist, where
  `_INT_ID` refuses a non-numeric id anyway — deleting the guard changed
  nothing;
* a scope test used `inspect.getsource(handler)` and grepped for a constant
  NAME, so it passed the whole time the routes were gated on the wrong scope;
* an authz test asserted `status_code in (403, 404)`, which cannot detect the
  cross-tenant oracle that the choice between those two codes *is*.

Two of my own new tests in the same session also passed against the reverted
bug on first writing — an async isolation test that raced (`sleep(0)` returned
before the lock was acquired; fixed with an event set from inside the hang).
Writing the test does not mean it can fail.

**How to apply:**
- Prefer behavioural assertions over source inspection. Grepping a handler for
  a constant name tests spelling, not enforcement.
- Never assert a *set* of acceptable statuses where the distinction between
  them is the security property (`in (403, 404)` — pick one and pin it).
- A test double that mirrors the implementation's assumption cannot falsify it.
  Model the **product's** real behaviour instead — building `FakeGough` on a
  real `werkzeug.routing.Map` of Gough's registrations reproduced its 308/404
  slash asymmetry, which no hand-written description had.
- For a cross-language invariant, assert equality between the two sides
  directly (a Python test parsing the TS constant), because each side asserted
  against itself passes independently while disagreeing.

See [[adapter-contract-boundaries]], [[feedback-evidence-over-assumption]].
