---
name: verify-by-running
description: In penguincloud webui, every fix must be proven by running the thing and pasting its output — reading the code is not acceptance
metadata:
  type: feedback
---

Prove every claim by **executing** and reading the output. Never report a fix as done based on reading the diff.

**Why:** A Phase 1F review found multiple prior-session claims that were false when actually built — the report said the Tailwind v4 migration was "DONE" while the app shipped with **zero** generated utilities, and said `productsStore` had been trimmed when it was untouched. The reviewer's standard is explicit: build it, grep the artifact, start the server, curl it.

**How to apply:**
- CSS changes → `npm run build`, then grep the emitted `dist/client/assets/*.css` for expanded utilities and for raw `@apply` (must be 0). A green build proves nothing; Vite happily emits unprocessed CSS.
- Server changes → actually start it (`NODE_ENV=production node dist/server/index.js`) and curl `/` **plus a deep route**. `/` alone is served by `express.static` and passes even when the SPA fallback is broken.
- Config/gate changes → run the gate and paste the exit code. A gate that has never run is worse than a failing one.
- Claims about a dependency version → `npm view <pkg> version` rather than assuming a newer one exists.

Corollary that paid off repeatedly: running the fix surfaces defects static review cannot. Both the `sendFile` dotfile 404 and the `schema.capabilities` runtime throw were found this way, and neither was on the findings list.
