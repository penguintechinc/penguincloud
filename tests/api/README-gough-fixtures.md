# Regenerating the Gough live fixtures

`fixtures/gough_real_payloads.json` holds payloads captured from a **running
Gough**, not hand-written ones. `test_gough_real_payloads.py` asserts the
adapter's mappers against them, so they are only worth what their provenance
is worth — regenerate them the same way, or they stop meaning anything.

Captured 2026-08-08 against the checkout at `/home/penguin/code/gough`.

## Bringing Gough up

Gough's own `make dev` does **not** work: it shells out to the removed v1
`docker-compose` binary (`make: docker-compose: No such file or directory`).
Use the compose plugin directly, plus an override for four defects in Gough's
own build that stop the container starting. The override lives outside the
Gough tree — Gough is read-only here.

```yaml
# /tmp/gough-override.yml
services:
  postgres:
    # Gough pins postgres with a DOUBLED digest (@sha256:...@sha256:...),
    # which docker rejects as an invalid reference.
    image: postgres:16-bookworm@sha256:7858a1a43bb2e3decc07650c8989ba526e0a8164f212c9bb88b622cdbd71c4be
  api-manager:
    volumes:
      # app/__init__.py imports penguin_aaa and app/db/database.py imports
      # penguintechinc_utils, but neither package is in requirements.txt nor in
      # the Dockerfile's penguin-libs copy list.
      - /home/penguin/code/penguin-libs/packages/python-aaa/src:/opt/penguin-aaa/src:ro
      - /home/penguin/code/penguin-libs/packages/python-utils/src:/opt/penguin-utils/src:ro
    environment:
      - PYTHONPATH=/opt/penguin-aaa/src:/opt/penguin-utils/src:/tmp/extra-site-packages
      - SECRET_KEY=local-verification-only-secret-key-value
      - SECURITY_PASSWORD_SALT=local-verification-only-salt-value
    command:
      - sh
      - -c
      # run.py imports pydal, which nothing under app/ imports any more and
      # which is absent from requirements.txt. --user is refused inside the
      # image's venv, and the venv is root-owned while the container runs as
      # appuser, so install to a writable target dir on PYTHONPATH instead.
      - pip install --quiet --no-cache-dir --target /tmp/extra-site-packages pydal==20260520.0 && exec python run.py
```

```bash
cd /home/penguin/code/gough
docker compose -f docker-compose.yml -f /tmp/gough-override.yml up -d postgres api-manager
curl -s localhost:5001/healthz     # {"database":"connected","status":"healthy"}
```

Gough creates its schema and seeds 4 biomes on first boot.

## Why the payloads come from serializers, not HTTP

Gough's `scope_enforcement_middleware` denies **every** authenticated route in
this build, so no adapter call past `health()` can reach a real payload over
HTTP. Two independent causes, both verified live:

1. `POST /api/v1/auth/login` is in neither `ANONYMOUS_PATHS` nor
   `SCOPE_POLICY`, so it 403s — the adapter cannot obtain a token at all.
2. Routes that *are* in `SCOPE_POLICY` 401 with `Authentication required`
   regardless of token, because the middleware is a `before_request` hook
   reading `g.current_user`, which the `@auth_required` **view decorator** sets
   later.

So the resource payloads are captured by calling Gough's **own serializer
functions** (`app.api.nodes._serialize_node`, `app.api.biomes.serialize_biome`,
`serialize_biome_group`) over its **own database rows**. The shapes are Gough's;
only the transport is bypassed. The fixture labels which captures are
HTTP-level and which are serializer-level — keep that distinction when adding
to it.

```bash
docker exec gough-postgres psql -U gough -d gough -c "INSERT INTO nodes (...) VALUES (...)"
docker exec gough-api-manager python -c "...import the serializer, dump JSON..."
```

Full commands are in the live-verification report under
`.superpowers/sdd/create-a-plan-to-jazzy-cupcake/`.

## Re-verifying the route parser

`gough_route_source.py` reproduces Quart's blueprint-prefix join in `ast`.
Confirm it still matches reality by diffing it against a running Gough:

```bash
docker exec gough-api-manager python -c "
import asyncio, json, sys; sys.path.insert(0,'/app')
from app import create_app
async def m():
    app = await create_app()
    out = {}
    for r in app.url_map.iter_rules():
        out.setdefault(str(r.rule), set()).update(set(r.methods) - {'HEAD','OPTIONS'})
    print(json.dumps({k: sorted(v) for k, v in out.items()}))
asyncio.run(m())" | tail -1 > /tmp/live_urlmap.json
```

Then compare with `gough_source_routes()`. It matched exactly on 2026-08-08:
154 routes each side, no differences.

## Teardown

```bash
cd /home/penguin/code/gough && docker compose -f docker-compose.yml -f /tmp/gough-override.yml down -v
```
