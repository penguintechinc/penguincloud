---
name: tailwind-v4-webui
description: Tailwind v4 and Express 5 traps actually hit in penguincloud/services/webui, with the symptom each produced
metadata:
  type: project
---

Concrete failures hit while repairing this workspace's v4 setup. Each produced a *silent* wrong result rather than an error.

**Why:** These cost real debugging time and none of them fail loudly.

**How to apply:**
- **Pipeline:** this workspace uses `@tailwindcss/vite` (exact 4.1.17) in `vite.config.ts`. There is no `postcss.config.js` and `@tailwindcss/postcss` is intentionally absent — do not reintroduce a second mechanism. With no plugin at all, Vite still emits a CSS file (inlining `@import "tailwindcss"` as plain CSS) containing literal `@apply` and zero utilities, and the build stays green.
- **`@apply` of a custom class fails in v4** — it inlines only *registered* utilities. `.btn-primary { @apply btn ... }` errors with "Cannot apply unknown utility class `btn`". Declare the composable base with `@utility btn { ... }`.
- **v3 names still present in this repo's history:** `bg-gradient-to-r` → `bg-linear-to-r`, `flex-shrink-0` → `shrink-0`, and `bg-dark-*` / `text-gold-*` which have no v4 equivalent at all. `index.html` is outside `src/` — grep it too; it carried dead classes on `<body>`.
- **Express 5 + `res.sendFile`:** pass `{ root: clientDir }` with a relative filename, never one absolute path. `send` applies `dotfiles: "ignore"` to every segment given, so an absolute path 404s under any dot-directory — `.worktrees/`, CI workspaces, `/opt/.releases/`. Symptom is `/` working while all deep routes 500.
- SPA fallback must be `app.get("/*splat", ...)`; a bare `"*"` throws at registration under path-to-regexp v8.

The `styling-with-tailwind-v4` skill's Step 2 diagnostic is the fastest triage: count emitted utilities and check for `hover:` variants. Note `grep -c` on minified CSS counts *lines* — use `grep -o ... | wc -l`.

See [[verify-by-running]] and [[webui-gates]].
