"""The token set pcli stores, plus a display-only (UNVERIFIED) JWT decoder.

`TokenSet` is the one object `TokenStore` persists and every command reads
credentials from. It is a superset of the portal's own `LoginResponse`
(`app.auth.LoginResponse`): it also carries the tenant context a
`/tenants/{id}/switch` call rotates in, and the absolute expiry time
computed from `expires_in` at the moment the token was issued.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

#: How much earlier than the JWT's real expiry pcli treats it as expired --
#: leaves headroom for the request itself plus any clock skew rather than
#: racing a token that expires mid-call.
EXPIRY_SKEW_SECONDS: float = 30.0


@dataclass(slots=True, frozen=True)
class TenantContext:
    """The tenant a stored token is currently scoped to, echoed by `/switch`."""

    id: int
    slug: str | None = None
    name: str | None = None


@dataclass(slots=True)
class TokenSet:
    """Credentials pcli persists between invocations.

    `expires_at` is an absolute UNIX timestamp computed once, at mint time
    (`time.time() + expires_in`) -- never recomputed relative to "now" on
    load, or every load would silently extend the token's apparent life by
    however long it sat on disk.
    """

    access_token: str
    refresh_token: str
    token_type: str
    expires_at: float
    tenant: TenantContext | None = None
    scope: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_expired(self) -> bool:
        """True once within `EXPIRY_SKEW_SECONDS` of the real expiry, or past it."""
        return time.time() >= (self.expires_at - EXPIRY_SKEW_SECONDS)

    @property
    def authorization_header(self) -> str:
        """The `Authorization` header value for this token."""
        return f"{self.token_type} {self.access_token}"

    def with_tenant(self, tenant: TenantContext) -> TokenSet:
        """A copy of this token set scoped to a new tenant (post-`/switch`)."""
        return TokenSet(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            token_type=self.token_type,
            expires_at=self.expires_at,
            tenant=tenant,
            scope=self.scope,
        )

    def to_json(self) -> str:
        """Serialize for keyring storage. Never called when PCLI_TOKEN supplied the token."""
        payload = asdict(self)
        return json.dumps(payload)

    @classmethod
    def from_json(cls, raw: str) -> TokenSet:
        """Deserialize a keyring-stored token set."""
        data = json.loads(raw)
        tenant_data = data.get("tenant")
        tenant = TenantContext(**tenant_data) if tenant_data else None
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data["token_type"],
            expires_at=float(data["expires_at"]),
            tenant=tenant,
            scope=tuple(data.get("scope", ())),
        )

    @classmethod
    def from_login_response(
        cls,
        body: dict[str, Any],
        *,
        issued_at: float | None = None,
        tenant: TenantContext | None = None,
    ) -> TokenSet:
        """Build a `TokenSet` from a portal `LoginResponse`/device-token body."""
        base_time = issued_at if issued_at is not None else time.time()
        return cls(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", ""),
            token_type=body.get("token_type", "Bearer"),
            expires_at=base_time + float(body["expires_in"]),
            tenant=tenant,
        )


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Best-effort, UNVERIFIED decode of a JWT's payload -- display only.

    Never used for an authorization decision: the portal is the sole
    verifier of signature/`exp`/`aud` (security.md). This exists purely so
    `pcli whoami` can show the caller their own `tenant`/`scope`/`teams`
    claims without a round trip. A malformed or non-JWT token degrades to
    an empty dict rather than raising -- informational-only, never fatal.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        claims = json.loads(decoded)
    except (ValueError, binascii.Error, json.JSONDecodeError, KeyError):
        return {}
    return claims if isinstance(claims, dict) else {}
