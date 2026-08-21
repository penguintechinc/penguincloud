# Regenerating and trusting the Tobogganing fixture

`fixtures/tobogganing_source.json` is not parsed from source like Gough's or
Nest's — it is produced by **booting** Tobogganing (`hub_api.app.create_app()`
inside `app.test_app()`) and reading `app.url_map`, because Tobogganing
assembles its final paths at runtime in a module registry. See
`tobogganing_route_source.py`'s module docstring for why a static parse would
be wrong, not just awkward, for this product.

## The boot needs Tobogganing's OWN dependencies, not just its source

The subprocess that boots Tobogganing runs under `sys.executable` — whatever
interpreter is running pytest — with only `$PYTHONPATH` pointed at the
checkout. It does **not** install or activate Tobogganing's own virtualenv.
That interpreter is normally the portal's own isolated `.venv`
(`services/portal-api/requirements.txt`), which is deliberately **not**
Tobogganing's dependency set. A refresh or a `REQUIRE_PRODUCT_SOURCE=1` run
needs Tobogganing's own runtime dependencies installed into that same
interpreter first:

```bash
cd path/to/portal-worktree
.venv/bin/pip install redis                              # undeclared upstream — see below
.venv/bin/pip install markdown==3.10.2 bleach==6.1.0      # declared, but installed nowhere by default
```

`redis` is imported by `hub_api/cache/client.py` but is **not** in
`hub_api/requirements.txt` at all — an upstream gap in Tobogganing itself, not
something to fix here.

`markdown` and `bleach` ARE declared (`hub_api/requirements.txt` pins
`markdown==3.10.2` and `bleach==6.1.0`) — they are only missing because
nothing installs Tobogganing's requirements file into the portal's
interpreter. Confirmed 2026-08-20 that a boot interpreter with `redis` alone
already exits 0 and produces a plausible-looking, self-consistent route
table — it does **not** fail loudly. See the next section for why that is
dangerous by itself.

If Tobogganing gains further runtime imports, expect this list to grow; a
`ModuleNotFoundError` surfaced through `ModuleRegistrationError` (see below)
names the exact package to add.

## Why a missing dependency looks exactly like a missing route

`hub_api/app.py` registers each of `hub_api.modules.__all__` inside:

```python
try:
    module_pkg = __import__(module_path, fromlist=["module"])
    if hasattr(module_pkg, "module"):
        contract = module_pkg.module()
        registry.register(contract)
except (ImportError, AttributeError) as e:
    logger.error(f"Failed to register module {module_name}: {e}")
```

That `except` only logs — it does not re-raise. So a boot interpreter missing
one of a module's dependencies still **boots successfully** (exit 0, a
parseable rule dump) with that entire module silently absent. On
2026-08-20, a boot run with `redis` installed but not `markdown`/`bleach`
produced exactly 99 routes against a vendored fixture of 108, missing
precisely the nine `/api/v1/sase/blockpages/*` and `/api/v1/sase/swg/*`
routes — indistinguishable, from the route table alone, from Tobogganing
having genuinely dropped those endpoints. It had not: `sase/__init__.py`'s
`module()` imports `hub_api.modules.sase.security.blockpages.render`, which
imports `markdown` and (transitively, via its HTML-sanitisation step)
`bleach`; once both were installed the live boot matched the vendored fixture
on routes, auth classes, and envelope keys **exactly** (108/108, zero drift).

**Before trusting a route diff produced by this boot, rule out an incomplete
environment first.** `tobogganing_route_source.py` now does this
automatically: the boot program re-derives which of
`hub_api.modules.__all__` (the product's own manifest, not a list
transcribed here) is missing from the live `app.registry`, re-imports it
outside `app.py`'s swallowing `except` to recover the real exception, and
reports it back. `_boot()` raises `ModuleRegistrationError` (a `BootError`
subclass) when that list is non-empty, with a message naming the module and
the underlying `ImportError` — distinct from a genuine route-table mismatch,
which raises the ordinary fixture-drift assertion instead. Every existing
`except BootError` fallback still catches it and degrades to the vendored
fixture, same as any other reason a live boot isn't trustworthy.

## Re-verifying after a refresh

```bash
make refresh-product-source-fixtures     # needs the deps above installed first
git diff tests/api/fixtures/tobogganing_source.json   # review: routes/auth/envelopes, not just provenance
REQUIRE_PRODUCT_SOURCE=1 make test-api-live
```
