---
name: feedback-webui-npm-audit-blocks-every-push
description: services/webui/package-lock.json carries pre-existing high-severity dev-only npm vulns (puppeteer chain) that fail osv-scanner + npm-audit-webui on EVERY push, regardless of what changed
metadata:
  type: project
---

Pre-push hooks `osv-scanner` and `npm-audit-webui` both fail on ANY push
that touches the repo right now — not something a given branch's changes
caused. `services/webui/package-lock.json` (last touched at `76d4eb5e`,
predates this) carries two high-severity advisories through `puppeteer`'s
dependency chain:

* `GHSA-jmr9-qjv8-65gv` (extract-zip, via `@puppeteer/browsers`) — CVSS 8.6
* `GHSA-2v37-7h3g-55p8` (nanoid) — CVSS 8.2

Both are dev-only (test tooling), not shipped. Confirmed via
`git diff HEAD~2 -- services/webui/package-lock.json services/webui/package.json`
returning empty on a branch that only touched `schema.d.ts` (generated,
via `npm run generate:api`) — the lockfile itself was untouched.

**Do not silently work around this** — `general.md`/`security.md` forbid
`--no-verify`, and `package-lock.json`/`package.json` are outside a
response-validation/route-module file set (likely owned by whichever
branch is doing dependency hygiene — `chore/dependency-hygiene` was active
in the same session this was found in).

**How to apply:** if your task's file set doesn't include `services/webui/
package*.json`, expect `git push` to fail on this every time until a
dependency-hygiene pass lands `npm audit fix`/`fix --force` (the latter is
a puppeteer major-version bump, so it's a deliberate upgrade, not a patch).
Commit locally (safety net intact — `git log` proves the work exists) and
report the push as blocked with the exact osv-scanner/npm-audit output,
rather than bypassing the hook or hand-editing the lockfile outside your
assigned scope.

See [[feedback-gates-block-push]] for the rest of this repo's pre-push gate
inventory.
