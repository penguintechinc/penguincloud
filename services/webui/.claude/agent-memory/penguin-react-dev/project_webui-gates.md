---
name: webui-gates
description: Which quality gates in penguincloud/services/webui are real, and the ones that silently pass while enforcing nothing
metadata:
  type: project
---

Gates in `services/webui` have a history of appearing green while enforcing nothing. Check the gate itself before trusting its result.

**Why:** Fix wave 1 found `npm run typecheck` had *never* executed (referenced `tsconfig.server.json` lacked `composite: true` → TS6306 aborted before checking any file), three eslint rules globally disabled, and `collectCoverageFrom` scoped to all of `src/client` while `coverageThreshold` gated only kit + api — so the headline coverage number was enforced by nothing.

**How to apply:**
- The pre-commit hook runs **gitleaks + prettier only** — not eslint, not tsc, not jest. Passing pre-commit says nothing about lint or types. Run `npm run lint`, `npm run typecheck`, `npm test` yourself.
- `react-hooks` rules only run if `eslint-plugin-react-hooks` is registered in the flat config. It ships no flat-config export at 5.1.0, so it needs explicit `plugins: { "react-hooks": reactHooks }`. Setting one of its rules to `"off"` when unregistered is a no-op that *looks* like a suppression.
- Keep `collectCoverageFrom` and `coverageThreshold` scoped identically, or the reported percentage is decorative.
- `argsIgnorePattern: "^_"` on `no-unused-vars` is required, not a weakening: Express detects error middleware by arity (`fn.length === 4`), so removing `_next` silently demotes it to ordinary middleware.
- House cap is 5,000 chars per file; the kit directory sits close to it, so re-check `wc -c` after adding comments — ConfirmDialog crossed the cap purely from a corrected comment.

See [[verify-by-running]].
