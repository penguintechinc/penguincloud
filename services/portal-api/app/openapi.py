"""OpenAPI documents: one public, one authenticated.

backend.md requires that a live spec and docs UI be gated behind the same
JWT middleware as the rest of the API, with exactly one exception — the
login endpoint, which a client legitimately needs to read *before* it has a
token. quart-schema mounts ``/openapi.json``, ``/docs``, ``/redocs`` and
``/scalar`` fully unauthenticated by default, covering every endpoint.

Why gating matters more than it first appears: a complete spec is a map of
the entire attack surface — every path, every parameter name, every request
schema, every error shape. It is the first thing an attacker enumerates, and
serving it anonymously hands over the reconnaissance step for free. Note
that committing ``openapi/v1.yaml`` to the repository is unaffected; source
control is not the open internet. What needs a gate is the *running
service*.

Two documents, not one route with a toggle
------------------------------------------
The standard is explicit that this is implemented as two separate
documents. A single spec with a conditional filter is one boolean away from
serving everything anonymously, and that boolean is evaluated on a code
path that only anonymous callers exercise — precisely the path least likely
to be covered by anyone's manual testing.

* :func:`build_public_spec` — derived by FILTERING the full document down to
  the login path. Derivation matters: a hand-written public stub would drift
  from the real endpoint silently, and the drift would only be visible to
  unauthenticated clients.
* :func:`build_full_spec` — everything, served only to a caller with a valid
  token. Any authenticated caller may read it; the goal is keeping the API
  map off the open internet, not restricting it among legitimate clients.
"""

from __future__ import annotations

import copy
from typing import Any, Final

from quart import Quart, current_app, jsonify
from quart_schema import hide
from quart_schema.extension import QuartSchema, _build_openapi_schema

from .middleware import auth_required

__all__ = [
    "PUBLIC_PATHS",
    "build_full_spec",
    "build_public_spec",
    "register_openapi_routes",
]

#: The only operations an unauthenticated caller may see documented. A client
#: cannot obtain a token without knowing how to call login, so this one path
#: is published in the clear; everything else requires a token to discover.
#:
#: Deliberately a fixed, tiny allowlist rather than a pattern. A pattern such
#: as "anything under /auth" would silently publish password-reset, refresh
#: and MFA-enrolment operations the moment they were added.
PUBLIC_PATHS: Final[frozenset[str]] = frozenset({"/api/v1/auth/login"})

#: Served in place of descriptions/schemas that the public document must not
#: carry through from the full one.
_PUBLIC_TITLE_SUFFIX: Final[str] = " (public)"


def build_full_spec(app: Quart) -> dict[str, Any]:
    """Generate the complete OpenAPI document from the live routes.

    Generated from the app's own route table and type annotations rather
    than hand-maintained, so the document cannot drift from the
    implementation it describes.
    """
    extension = app.extensions["QUART_SCHEMA"]
    assert isinstance(extension, QuartSchema)
    schema: dict[str, Any] = _build_openapi_schema(app, extension)
    _fix_security_scheme_casing(schema)
    _ensure_documented_responses(schema)
    _drop_null_defaults(schema)
    _bound_arrays(schema)
    return schema


#: Declared upper bound on any array in this API contract.
#:
#: An array with no ``maxItems`` tells a client to be prepared for an
#: unbounded collection, which is why checkov's CKV_OPENAPI_21 flags it: a
#: generated client sizes buffers from the contract, and "no limit" is not
#: something a caller can allocate against.
#:
#: Every array currently in the document is a RESPONSE array, and each is
#: already constrained below this ceiling by something real:
#:   * members  — the tenant's ``max_users`` quota, enforced on insert
#:   * products — the tenant's ``max_products`` quota, enforced on insert
#:   * scope    — the fixed size of a role's scope bundle
#:   * tenants / rollup — the size of the caller's tenant subtree
#: The first three are hard invariants. The last two are bounded by the
#: hierarchy rather than by an explicit cap, so this ceiling is deliberately
#: far above any plausible fleet; pagination on those two endpoints is
#: tracked separately and would replace this with a real page size.
MAX_ARRAY_ITEMS: Final[int] = 10_000


def _bound_arrays(node: Any) -> None:
    """Declare an upper bound on every array schema in the document.

    Applied to the generated document rather than written onto each
    dataclass: the bound is a property of the API contract, and attaching it
    per-DTO would leave any newly added collection silently unbounded until
    somebody remembered.
    """
    if isinstance(node, dict):
        if node.get("type") == "array" and "maxItems" not in node:
            node["maxItems"] = MAX_ARRAY_ITEMS
        for value in node.values():
            _bound_arrays(value)
    elif isinstance(node, list):
        for value in node:
            _bound_arrays(value)


#: Placeholder for an operation quart-schema produced no responses for —
#: i.e. a view not yet annotated with @validate_response. OpenAPI forbids an
#: empty `responses` object, so without this the document is invalid.
_UNDECLARED_RESPONSE_DESCRIPTION: Final[str] = (
    "Response shape is not yet declared for this operation. The view has no "
    "@validate_response annotation, so no schema is published for it; do not "
    "rely on a specific body until one is."
)


def _ensure_documented_responses(schema: dict[str, Any]) -> None:
    """Give every operation at least one documented response.

    Deliberately honest rather than convenient: the placeholder says the
    shape is UNDECLARED instead of inventing a plausible 200 schema.
    Fabricating one would put a shape in the published contract — and into
    every generated client — that nothing in the service actually
    guarantees, which is worse than admitting the gap.
    """
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if isinstance(responses, dict) and responses:
                continue
            operation["responses"] = {
                "default": {"description": _UNDECLARED_RESPONSE_DESCRIPTION}
            }


def _drop_null_defaults(node: Any) -> Any:
    """Remove ``default: null`` entries from schema objects.

    An optional field whose default is None carries no information — its
    absence already means the same thing — and the explicit null is not
    portable: OpenAPI 3.1 permits it, but tooling built on JSON Schema
    draft-07 (including current Spectral) crashes on it rather than
    reporting a diagnostic.
    """
    if isinstance(node, dict):
        if "default" in node and node["default"] is None:
            del node["default"]
        for value in node.values():
            _drop_null_defaults(value)
    elif isinstance(node, list):
        for value in node:
            _drop_null_defaults(value)
    return node


#: OpenAPI field names quart-schema 0.19 emits in snake_case despite asking
#: its own serialiser to camelize. Left uncorrected, the document fails
#: OpenAPI 3.1 schema validation and every generated client drops the field.
_SECURITY_SCHEME_KEY_FIXES: Final[dict[str, str]] = {
    "bearer_format": "bearerFormat",
    "open_id_connect_url": "openIdConnectUrl",
}


def _fix_security_scheme_casing(schema: dict[str, Any]) -> None:
    """Rename snake_case keys quart-schema leaves in securitySchemes.

    ``_build_full_schema`` calls ``value.schema(camelize=True)``, but the
    conversion does not reach these fields in quart-schema 0.19, so the
    document it produces is not a valid OpenAPI 3.1 document. Corrected here
    rather than in the export script so the LIVE ``/api/v1/openapi.json``
    and the committed ``openapi/v1.yaml`` cannot disagree — a fix applied
    only on the export path would leave the served document invalid.

    Remove once the upstream serialiser handles it; the tests assert the
    correct key, so they will keep passing when this becomes a no-op.
    """
    schemes = schema.get("components", {}).get("securitySchemes")
    if not isinstance(schemes, dict):
        return
    for definition in schemes.values():
        if not isinstance(definition, dict):
            continue
        for wrong, right in _SECURITY_SCHEME_KEY_FIXES.items():
            if wrong in definition:
                definition[right] = definition.pop(wrong)


def build_public_spec(full: dict[str, Any]) -> dict[str, Any]:
    """Reduce a full document to the publicly-documented operations.

    Filters rather than rebuilds, so the public description of login is
    byte-for-byte the one the service actually implements.

    Component schemas are pruned to those the surviving paths reference.
    Without that, ``components.schemas`` still enumerates every request and
    response model in the service — the field names of every DTO — which
    gives away most of what gating the paths was meant to withhold.
    """
    public: dict[str, Any] = {
        key: copy.deepcopy(value)
        for key, value in full.items()
        if key not in ("paths", "components")
    }

    info = public.setdefault("info", {})
    title = str(info.get("title", "API"))
    if not title.endswith(_PUBLIC_TITLE_SUFFIX):
        info["title"] = f"{title}{_PUBLIC_TITLE_SUFFIX}"
    info["description"] = (
        "Public API documentation. Only the login endpoint is documented "
        "here; authenticate and request the full specification for the rest."
    )

    public["paths"] = {
        path: copy.deepcopy(item)
        for path, item in full.get("paths", {}).items()
        if path in PUBLIC_PATHS
    }

    referenced = _referenced_schema_names(public["paths"], full)
    all_schemas = full.get("components", {}).get("schemas", {})
    kept = {
        name: copy.deepcopy(schema)
        for name, schema in all_schemas.items()
        if name in referenced
    }
    components = {
        key: copy.deepcopy(value)
        for key, value in full.get("components", {}).items()
        if key != "schemas"
    }
    if kept:
        components["schemas"] = kept
    if components:
        public["components"] = components

    return public


def _referenced_schema_names(paths: dict[str, Any], full: dict[str, Any]) -> set[str]:
    """Collect component schema names reachable from the given paths.

    Follows ``$ref`` transitively: a login response referencing a model that
    itself references another must keep both, or the published document is
    not resolvable.
    """
    all_schemas = full.get("components", {}).get("schemas", {})
    seen: set[str] = set()
    pending = _direct_refs(paths)

    while pending:
        name = pending.pop()
        if name in seen or name not in all_schemas:
            continue
        seen.add(name)
        pending.update(_direct_refs(all_schemas[name]))

    return seen


def _direct_refs(node: Any) -> set[str]:
    """Every component schema name named by a $ref anywhere under a node."""
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            prefix = "#/components/schemas/"
            if ref.startswith(prefix):
                found.add(ref[len(prefix) :])
        for value in node.values():
            found |= _direct_refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= _direct_refs(value)
    return found


# Swagger UI assets: EXACT version, with Subresource Integrity.
#
# Two separate requirements, both mandatory here:
#   - the version is pinned exactly (not `@5`), because a floating major tag
#     is a mutable reference — the repo forbids those for every external
#     dependency, and a CDN silently serving a new build into a page that
#     renders an authenticated API document is exactly why;
#   - `integrity` + `crossorigin` mean the browser refuses an asset whose
#     bytes do not match, so a compromised or hijacked CDN cannot execute
#     script in the origin that just served a valid access token.
#
# Regenerate after any version bump:
#   curl -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A
_SWAGGER_VERSION: Final[str] = "5.29.5"
_SWAGGER_CSS_SRI: Final[str] = (
    "sha384-++DMKo1369T5pxDNqojF1F91bYxYiT1N7b1M15a7oCzEodfljztKlApQoH6eQSKI"
)
_SWAGGER_JS_SRI: Final[str] = (
    "sha384-+//OXWv2MI+XGzCNZ1tyxL1lT/whLV95IujjmbHXUgGh80zv+9B0ii6pDIO3URWN"
)

_SWAGGER_TEMPLATE: Final[str] = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <link
      rel="stylesheet"
      href="https://unpkg.com/swagger-ui-dist@{version}/swagger-ui.css"
      integrity="{css_sri}"
      crossorigin="anonymous"
    />
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script
      src="https://unpkg.com/swagger-ui-dist@{version}/swagger-ui-bundle.js"
      integrity="{js_sri}"
      crossorigin="anonymous"
    ></script>
    <script>
      window.onload = () => {{
        window.ui = SwaggerUIBundle({{ url: "{spec_url}", dom_id: "#swagger-ui" }});
      }};
    </script>
  </body>
</html>
"""


def _render_docs(title: str, spec_url: str) -> str:
    """Render the Swagger UI page for a given specification URL."""
    return _SWAGGER_TEMPLATE.format(
        title=title,
        spec_url=spec_url,
        version=_SWAGGER_VERSION,
        css_sri=_SWAGGER_CSS_SRI,
        js_sri=_SWAGGER_JS_SRI,
    )


def register_openapi_routes(app: Quart) -> None:
    """Mount the public and authenticated specification endpoints.

    Called instead of, never alongside, quart-schema's own auto-mounted
    routes — those are disabled at QuartSchema construction (all four *_path
    arguments set to None). Leaving even one of them mounted would keep an
    unauthenticated copy of the full document available at a URL nobody
    remembered was there.
    """

    @app.route("/openapi.json")
    @hide
    async def public_openapi() -> Any:
        """Public specification: the login endpoint and nothing else."""
        return jsonify(build_public_spec(build_full_spec(current_app)))

    @app.route("/docs")
    @hide
    async def public_docs() -> Any:
        """Swagger UI for the public specification."""
        return _render_docs("PenguinCloud Portal API (public)", "/openapi.json")

    @app.route("/api/v1/openapi.json")
    @hide
    @auth_required
    async def full_openapi() -> Any:
        """Complete specification. Requires a valid access token.

        Not further gated by scope: any authenticated caller may read it.
        The objective is keeping the API map off the open internet, not
        partitioning it among legitimate clients — and a scope gate here
        would break SDK generation for ordinary users.
        """
        return jsonify(build_full_spec(current_app))

    @app.route("/api/v1/docs")
    @hide
    @auth_required
    async def full_docs() -> Any:
        """Swagger UI for the complete specification."""
        return _render_docs("PenguinCloud Portal API", "/api/v1/openapi.json")
