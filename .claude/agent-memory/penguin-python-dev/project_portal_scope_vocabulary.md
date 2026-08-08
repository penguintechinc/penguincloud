---
name: project-portal-scope-vocabulary
description: penguincloud portal scope vocabulary — coarse products:* plus per-product products:{type}:{action} (added 4G); a scope no minter issues is a dead 403
metadata:
  type: project
---

The portal's product scopes are minted by `resolve_scopes` in
`services/portal-api/app/tenancy/authz.py`. Since Task 4G there are two
forms, and **both are really minted**:

* **Coarse** — `products:read` / `products:manage`, from the role bundle.
* **Per-product** — `products:{product_type}:{read|manage}`, expanded from
  the coarse grant across the product types the tenant is actually connected
  to. Build with `product_scope()` (defined in BOTH `tenancy/authz.py` and
  `adapters/base.py`; the duplication avoids an import cycle and
  `tests/api/test_product_scopes.py` asserts they agree).

`RBACEnforcer._satisfies` (`adapters/base.py`) makes the coarse form satisfy
the per-product one, confined to three-segment `products:` scopes. So adapter
`route_allowlist` rules should name the **narrow** form — it costs nothing
today and is what allows a narrower grant later.

**The per-product form applies to TYPED portal routes too, not just the proxy
allowlist.** `operations_api._resolve` takes an action (`read`/`manage`) and
derives `products:{product_type}:{action}` from the connection's own type. It
originally gated on the coarse scope, which meant the model's motivating
principal — an operator holding `products:gough:manage` and nothing else —
could start a deploy through the proxy and was then refused permission to poll,
cancel or log it. When adding a product-scoped route, derive the scope; do not
reach for `SCOPE_PRODUCTS_READ`.

**The rule this exists for, still true:** a scope that nothing mints makes
every rule requiring it answer **403 to every token the portal can issue** —
a dead integration that looks *more* precisely secured. Phase-4 briefs
specify `{product}:{resource}:{read|write}` (e.g. `gough:nodes:read`);
nothing mints a `gough:*` scope, and per-*resource* granularity has no grant
surface either. Task 4G hit this: 25 `test_proxy_boundary` tests went red,
which is the only reason it was caught. **If you add a scope, add the test
that decodes a real JWT and finds it there.**

Not yet solved: there is no per-product *grant* surface, so every tenant
admin still holds the coarse scope and therefore all per-product ones.
Dropping `products:manage` from a role bundle is the remaining step, and it
needs no adapter change. Licence entitlement could not be folded in —
`LicenseManager` is a process-wide feature check, not per-tenant
per-product.

`app/authz.py` imports `app.adapters.base`, so an adapter module **cannot**
import `app.authz` (circular via `app.adapters.__init__`). Duplicate the
literals and assert equality in a test.

See [[adapter-contract-boundaries]].
