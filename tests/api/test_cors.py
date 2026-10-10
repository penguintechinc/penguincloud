"""CORS exposes the upstream-provenance marker header.

Today the webui always reaches this API same-origin through the Express BFF,
where a browser never strips response headers regardless of CORS config. But
the CORS allowlist in app/__init__.py exists because cross-origin access was
once intended, and a browser hides any response header not explicitly
exposed via Access-Control-Expose-Headers — including
UPSTREAM_RESPONSE_HEADER, the provenance marker
services/webui/src/client/lib/mutationError.ts trusts to decide whether a
body is safe to show verbatim. If the client is ever pointed at this origin
directly, an unexposed header would make every upstream-forwarded body read
as "trusted" with no code change on either side to notice.
"""

from typing import Any

import pytest
from app.adapters.base import UPSTREAM_RESPONSE_HEADER

# Matches TestingConfig's default (app.config.CORS_ORIGINS_ENV), which the
# test app does not override — see conftest.py's app fixture.
_ALLOWED_ORIGIN = "http://localhost:3000"


@pytest.mark.asyncio
async def test_upstream_marker_is_in_the_exposed_header_list(client: Any) -> None:
    """A cross-origin response advertises the marker as readable by fetch."""
    response = await client.get("/api/v1/status", headers={"Origin": _ALLOWED_ORIGIN})

    exposed = response.headers.get("Access-Control-Expose-Headers", "")
    exposed_names = {name.strip().lower() for name in exposed.split(",")}
    assert UPSTREAM_RESPONSE_HEADER.lower() in exposed_names
