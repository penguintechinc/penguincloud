"""OpenAPI: the public/authenticated split, and spec/code agreement.

backend.md requires that a live specification and docs UI sit behind the
same JWT middleware as the API, with exactly one exception — the login
endpoint. quart-schema's defaults do the opposite: four unauthenticated
routes, each serving the complete API surface.

The property under test is not "the spec renders". It is that an
**unauthenticated** caller can discover the login endpoint and nothing
else — no other path, and no component schema naming the fields of any
other DTO.
"""

import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from quart import Quart

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "openapi" / "v1.yaml"
LOGIN_PATH = "/api/v1/auth/login"


async def _auth_headers(client: Any) -> dict[str, str]:
    """Register + log in; return Authorization headers."""
    email = f"spec-{uuid.uuid4().hex[:8]}@example.com"
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Spec User"},
    )
    assert registered.status_code in (200, 201), await registered.get_json()

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "testpass123"}
    )
    assert logged_in.status_code == 200, await logged_in.get_json()
    token = (await logged_in.get_json())["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.usefixtures("app_context")
class TestPublicSpecIsLoginOnly:
    """The anonymous document exposes one operation."""

    @pytest.mark.asyncio
    async def test_public_spec_served_without_a_token(self, client: Any) -> None:
        """A client with no credentials can still learn how to get one."""
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        spec = await response.get_json()
        assert spec["openapi"].startswith("3.")

    @pytest.mark.asyncio
    async def test_public_spec_contains_only_the_login_path(self, client: Any) -> None:
        """Exactly one path — asserted by equality, not membership.

        `in` would pass while the document also published thirty other
        endpoints. Equality is the assertion that actually holds the line.
        """
        response = await client.get("/openapi.json")
        spec = await response.get_json()

        assert set(spec["paths"]) == {LOGIN_PATH}
        assert set(spec["paths"][LOGIN_PATH]) == {"post"}

    @pytest.mark.asyncio
    async def test_public_spec_leaks_no_other_schemas(self, client: Any) -> None:
        """Pruned components: a DTO's field names are part of the API map.

        Filtering paths but shipping every schema would still hand over the
        shape of every request and response in the service.
        """
        response = await client.get("/openapi.json")
        spec = await response.get_json()

        published = set(spec.get("components", {}).get("schemas", {}))
        for leaked in ("TenantDetail", "TenantMemberResponse", "RollupResponse"):
            assert leaked not in published

    @pytest.mark.asyncio
    async def test_public_spec_names_no_other_route(self, client: Any) -> None:
        """No path string for a gated endpoint appears anywhere in the body.

        A whole-document scan, because a reference can hide in a
        description or an example as easily as in `paths`.
        """
        response = await client.get("/openapi.json")
        raw = (await response.get_data()).decode()

        for gated in (
            "/api/v1/tenants",
            "/api/v1/users",
            "/api/v1/products",
            "/api/v1/audit",
            "/proxy/",
        ):
            assert gated not in raw, f"public spec mentions {gated}"

    @pytest.mark.asyncio
    async def test_public_docs_ui_is_reachable(self, client: Any) -> None:
        """The public UI renders and points at the public spec."""
        response = await client.get("/docs")
        body = (await response.get_data()).decode()

        assert response.status_code == 200
        assert 'url: "/openapi.json"' in body

    @pytest.mark.asyncio
    async def test_docs_assets_are_pinned_with_integrity(self, client: Any) -> None:
        """CDN assets carry SRI and an exact version.

        This page renders a document fetched with the user's session. A
        CDN serving unexpected bytes into it would be script execution on
        an authenticated origin, and a floating version tag is a mutable
        reference the repo forbids anyway.
        """
        response = await client.get("/docs")
        body = (await response.get_data()).decode()

        assert body.count("integrity=") == 2
        assert body.count('crossorigin="anonymous"') == 2
        assert "swagger-ui-dist@5." in body
        assert "swagger-ui-dist@5/" not in body, "floating major version"


@pytest.mark.usefixtures("app_context")
class TestFullSpecRequiresAuth:
    """The complete document is gated by the ordinary JWT middleware."""

    @pytest.mark.asyncio
    async def test_full_spec_401s_without_a_token(self, client: Any) -> None:
        """The headline acceptance check."""
        response = await client.get("/api/v1/openapi.json")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_full_docs_401s_without_a_token(self, client: Any) -> None:
        """The UI is gated too — it embeds the same information."""
        response = await client.get("/api/v1/docs")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_full_spec_rejects_a_garbage_token(self, client: Any) -> None:
        """An unverifiable token is not a token."""
        response = await client.get(
            "/api/v1/openapi.json",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticated_caller_gets_the_whole_document(self, client: Any) -> None:
        """Any valid token suffices — no extra scope gate.

        Deliberate: the objective is keeping the API map off the open
        internet, not partitioning it among legitimate clients, and a scope
        gate here would break SDK generation for ordinary users.
        """
        headers = await _auth_headers(client)
        response = await client.get("/api/v1/openapi.json", headers=headers)

        assert response.status_code == 200
        spec = await response.get_json()
        assert len(spec["paths"]) > 30
        assert LOGIN_PATH in spec["paths"]
        assert "/api/v1/tenants" in spec["paths"]

    @pytest.mark.asyncio
    async def test_quart_schema_default_routes_are_not_mounted(self, app: Quart) -> None:
        """The library's own unauthenticated routes are gone.

        /redocs and /scalar are the easy ones to forget; either would keep
        an anonymous copy of the full document at a URL nobody remembers.
        """
        rules = {str(rule.rule) for rule in app.url_map.iter_rules()}

        assert "/redocs" not in rules
        assert "/scalar" not in rules

    @pytest.mark.asyncio
    async def test_public_and_full_specs_describe_login_identically(self, client: Any) -> None:
        """The public document is derived, not hand-written.

        If it were maintained separately it could drift, and the drift
        would be visible only to unauthenticated clients — the population
        least able to report it.
        """
        headers = await _auth_headers(client)
        public = await (await client.get("/openapi.json")).get_json()
        full = await (await client.get("/api/v1/openapi.json", headers=headers)).get_json()

        assert public["paths"][LOGIN_PATH] == full["paths"][LOGIN_PATH]


@pytest.mark.usefixtures("app_context")
class TestSpecDocumentValidity:
    """The generated document is a valid OpenAPI 3.1 document."""

    @pytest.mark.asyncio
    async def test_security_scheme_uses_the_camelcase_field(self, client: Any) -> None:
        """`bearerFormat`, not `bearer_format`.

        quart-schema 0.19 emits the snake_case key despite asking its own
        serialiser to camelize. Uncorrected, the document fails schema
        validation and generated clients drop the field. Asserted on the
        LIVE document, not just the exported file, so the served copy
        cannot regress independently.
        """
        headers = await _auth_headers(client)
        spec = await (await client.get("/api/v1/openapi.json", headers=headers)).get_json()

        scheme = spec["components"]["securitySchemes"]["bearerAuth"]
        assert scheme["bearerFormat"] == "JWT"
        assert "bearer_format" not in scheme

    @pytest.mark.asyncio
    async def test_every_operation_documents_a_response(self, client: Any) -> None:
        """OpenAPI forbids an empty `responses` object."""
        headers = await _auth_headers(client)
        spec = await (await client.get("/api/v1/openapi.json", headers=headers)).get_json()

        for path, item in spec["paths"].items():
            for method, operation in item.items():
                responses = operation.get("responses")
                assert responses, f"{method.upper()} {path} documents no response"

    @pytest.mark.asyncio
    async def test_no_null_defaults_survive(self, client: Any) -> None:
        """`default: null` is dropped — it means nothing and breaks tooling."""
        headers = await _auth_headers(client)
        spec = await (await client.get("/api/v1/openapi.json", headers=headers)).get_json()

        def walk(node: Any, trail: str = "") -> None:
            if isinstance(node, dict):
                if "default" in node and node["default"] is None:
                    raise AssertionError(f"null default at {trail}")
                for key, value in node.items():
                    walk(value, f"{trail}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{trail}[{index}]")

        walk(spec)


class TestCommittedSpecIsCurrent:
    """The file in the repo matches what the code generates."""

    def test_spec_file_exists_and_is_marked_generated(self) -> None:
        """A GENERATED banner stops someone hand-editing it."""
        assert SPEC_PATH.exists(), "openapi/v1.yaml is missing; run `make openapi`"
        assert "GENERATED FILE" in SPEC_PATH.read_text()

    def test_committed_spec_is_not_stale(self) -> None:
        """`make openapi` would be a no-op right now.

        This is the drift guard the whole generate-don't-hand-maintain rule
        depends on: without it the committed document silently describes an
        older version of the service, and every SDK built from it is wrong
        in a way nothing reports.
        """
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "export-openapi.py"),
                "--check",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, (
            f"openapi/v1.yaml is stale — run `make openapi` and commit.\n"
            f"{result.stdout}\n{result.stderr}"
        )

    def test_spec_documents_the_login_endpoint(self) -> None:
        """The committed spec is what the TS client is generated from."""
        import yaml

        spec = yaml.safe_load(SPEC_PATH.read_text())
        assert LOGIN_PATH in spec["paths"]
        assert spec["openapi"].startswith("3.")

    def test_spec_excludes_the_static_file_route(self) -> None:
        """Quart's static route is not part of the API contract.

        Left in, it appears in every generated client SDK as a first-class
        operation alongside the real endpoints.
        """
        import yaml

        spec = yaml.safe_load(SPEC_PATH.read_text())
        assert "/static/{filename}" not in spec["paths"]
