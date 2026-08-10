"""Feature-flag evaluation: degradation, and that flags meet what checks them.

Two failure classes this file exists to prevent.

**Crashing or hard-failing on a flag service that is down.** general.md is
unambiguous: "if the flag/license server is unreachable, fall back to the
last-known cached value (new/never-seen flags default OFF) — never crash".
An outage in `license.penguintech.io` must not take the portal with it, and
it must not silently switch every feature off for customers who had them on.

**A flag nothing declares, or a licensed feature with no flag.** Both are
the same defect the dead `gough:*` scopes were: a name spelled at one side
of a boundary that the other side never mints, producing a switch that
reads like it works and is permanently off. Asserted here mechanically
against ``PRODUCT_TYPES`` and ``FEATURE_MIN_TIER`` rather than by review.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from app import flags, licensing
from app.models import PRODUCT_TYPES


class _FakePosthog:
    """Stands in for the SDK client. Records calls, answers on script."""

    def __init__(self, answer: Any = True, raises: bool = False) -> None:
        self.answer = answer
        self.raises = raises
        self.calls: list[tuple[str, str]] = []

    def feature_enabled(self, key: str, distinct_id: str) -> Any:
        self.calls.append((key, distinct_id))
        if self.raises:
            raise RuntimeError("flag service unreachable")
        return self.answer


@pytest.fixture(autouse=True)
def _clean_flag_state() -> Any:
    """Every test starts with no client and an empty cache."""
    flags.reset_client()
    yield
    flags.reset_client()


class TestUnconfigured:
    """No POSTHOG_KEY means no flag server, and therefore no network."""

    def test_client_is_none_without_a_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("POSTHOG_KEY", raising=False)
        assert flags.get_client() is None

    def test_flags_default_off_without_a_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("POSTHOG_KEY", raising=False)
        assert flags.is_enabled_blocking("gough", "user-1") is False

    def test_an_explicit_default_is_honoured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("POSTHOG_KEY", raising=False)
        assert flags.is_enabled_blocking("gough", "user-1", default=True) is True


class TestClientConstruction:
    """The SDK call itself, so a signature break is loud rather than silent."""

    def test_a_configured_key_builds_a_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Guards the graceful-degradation path from hiding a real break.

        ``get_client`` catches construction failures and returns None, which
        is correct behaviour and also the perfect place for an SDK upgrade
        that renamed a kwarg to disappear: every flag would quietly resolve
        to its default and nothing would report why. This asserts the
        constructor actually accepts the arguments app/flags.py passes it.
        """
        monkeypatch.setenv("POSTHOG_KEY", "phc_test_key_not_a_real_secret")
        monkeypatch.setenv("POSTHOG_HOST", "https://license.penguintech.io")
        monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)

        assert flags.get_client() is not None, (
            "the PostHog client failed to construct — app/flags.py passes a "
            "kwarg this posthog version does not accept, and every flag is "
            "silently resolving to its default"
        )

    def test_client_construction_is_latched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One client per process, built once, not per evaluation."""
        monkeypatch.setenv("POSTHOG_KEY", "phc_test_key_not_a_real_secret")
        assert flags.get_client() is flags.get_client()


class TestDegradation:
    """Server down, flag unknown, SDK raising — none of them may crash."""

    def _install(self, monkeypatch: pytest.MonkeyPatch, fake: _FakePosthog) -> None:
        monkeypatch.setattr(flags, "get_client", lambda: fake)

    def test_last_known_value_survives_an_outage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A flag that was ON stays ON when the server stops answering.

        This is the requirement that makes the fallback worth having. A TTL
        applied to the fallback would turn a flag-service outage into a
        cluster-wide kill switch for every enabled feature.
        """
        live = _FakePosthog(answer=True)
        self._install(monkeypatch, live)
        assert flags.is_enabled_blocking("gough", "user-1") is True

        # Age the cached entry past the freshness window, then break the
        # server. The value must survive.
        monkeypatch.setattr(
            flags,
            "get_client",
            lambda: _FakePosthog(raises=True),
        )
        for entry in flags._CACHE.values():
            entry.fetched_at = time.monotonic() - (flags.FLAG_CACHE_TTL_SECONDS * 10)

        assert flags.is_enabled_blocking("gough", "user-1") is True

    def test_outage_with_no_cached_value_defaults_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never seen + unreachable = OFF. Not an exception, not ON."""
        self._install(monkeypatch, _FakePosthog(raises=True))
        assert flags.is_enabled_blocking("nest", "user-1") is False

    def test_unknown_flag_is_off_and_not_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PostHog answers None for a flag it does not know.

        Not cached, because "never seen" is not "known false" — caching it
        would delay a newly created flag by the whole TTL for no benefit.
        """
        self._install(monkeypatch, _FakePosthog(answer=None))
        assert flags.is_enabled_blocking("nest", "user-1") is False
        assert flags._CACHE == {}

    def test_undeclared_flag_is_refused_without_calling_the_server(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A key absent from KNOWN_FLAGS can never be granted."""
        fake = _FakePosthog(answer=True)
        self._install(monkeypatch, fake)

        assert flags.is_enabled_blocking("not_a_declared_flag", "user-1") is False
        assert fake.calls == []

    def test_a_fresh_value_is_reused_within_the_ttl(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The request path must not hit the flag server per evaluation."""
        fake = _FakePosthog(answer=True)
        self._install(monkeypatch, fake)

        for _ in range(5):
            assert flags.is_enabled_blocking("gough", "user-1") is True

        assert len(fake.calls) == 1

    def test_the_cache_is_partitioned_by_principal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Percentage rollouts differ per user; one cache slot would leak."""
        fake = _FakePosthog(answer=True)
        self._install(monkeypatch, fake)

        flags.is_enabled_blocking("gough", "user-1")
        flags.is_enabled_blocking("gough", "user-2")

        assert [call[1] for call in fake.calls] == ["user-1", "user-2"]


class TestKeyConvention:
    """`{product}.{feature-name}`, spelled in one place."""

    def test_keys_are_namespaced(self) -> None:
        assert flags.flag_key("gough") == "penguincloud.gough"

    @pytest.mark.parametrize("feature", sorted(flags.KNOWN_FLAGS))
    def test_every_declared_flag_namespaces_cleanly(self, feature: str) -> None:
        """A feature name carrying a dot would forge a different key."""
        assert "." not in feature
        assert flags.flag_key(feature).startswith(f"{flags.FLAG_NAMESPACE}.")

    @pytest.mark.asyncio
    async def test_evaluated_key_is_the_namespaced_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The server is asked for `penguincloud.gough`, not `gough`.

        A bare name would evaluate against a flag that does not exist —
        None, i.e. permanently OFF, with no error anywhere.
        """
        fake = _FakePosthog(answer=True)
        monkeypatch.setattr(flags, "get_client", lambda: fake)

        await flags.is_enabled("gough", "user-1")

        assert fake.calls == [("penguincloud.gough", "user-1")]


class TestFlagsMeetWhatChecksThem:
    """Declaration side and consumption side, asserted mechanically."""

    def test_product_flags_name_real_product_types(self) -> None:
        """A flag for a product the portal cannot connect is unreachable."""
        unknown = flags.PRODUCT_FLAGS - set(PRODUCT_TYPES)
        assert not unknown, (
            f"product flags naming no product_type: {sorted(unknown)}. "
            f"Nothing can ever be gated on them."
        )

    def test_every_licensed_feature_has_a_flag(self) -> None:
        """general.md: EVERY feature ships behind a flag, licensed or not.

        A licensed feature with no flag cannot be rolled out or killed
        without a redeploy, which is the whole reason the flag layer sits
        under the license layer.
        """
        unflagged = set(licensing.FEATURE_MIN_TIER) - flags.KNOWN_FLAGS
        assert not unflagged, (
            f"licensed features with no flag: {sorted(unflagged)}. Add them "
            f"to FEATURE_FLAGS — a tier gate alone is not a toggle."
        )

    def test_product_and_feature_flag_names_are_disjoint(self) -> None:
        """One key, one meaning.

        ``waddleai`` is a connectable product on every tier; the Enterprise
        entitlement is the portal-side assist (``waddleai_assist``). Sharing
        the name would put a product-enablement toggle and a licence gate on
        one switch, where turning the product on would read as turning the
        Enterprise capability on.
        """
        overlap = flags.PRODUCT_FLAGS & flags.FEATURE_FLAGS
        assert not overlap, sorted(overlap)

    def test_known_flags_is_the_union_and_is_not_empty(self) -> None:
        """Guards every set-difference check above from passing vacuously."""
        assert flags.KNOWN_FLAGS == flags.PRODUCT_FLAGS | flags.FEATURE_FLAGS
        assert flags.PRODUCT_FLAGS and flags.FEATURE_FLAGS


class TestFlagAndLicenseConjunction:
    """A flag alone must not unlock a licensed feature, and vice versa."""

    @pytest.mark.asyncio
    async def test_flag_on_but_unlicensed_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The exact hole a flag-only check would leave.

        ``sso_integration`` is Professional. With the flag forced ON and a
        community licence, ``is_feature_available`` must still refuse — a
        rollout toggle is not an entitlement.
        """
        monkeypatch.setattr(flags, "get_client", lambda: _FakePosthog(answer=True))
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        assert await flags.is_enabled("sso_integration", "user-1") is True
        assert await flags.is_feature_available("sso_integration", "user-1") is False

    @pytest.mark.asyncio
    async def test_licensed_but_flag_off_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other direction: an entitlement does not bypass the rollout."""
        monkeypatch.setattr(flags, "get_client", lambda: _FakePosthog(answer=False))
        monkeypatch.setattr(
            licensing, "is_feature_entitled_blocking", lambda feature: True
        )

        assert await flags.is_feature_available("sso_integration", "user-1") is False

    @pytest.mark.asyncio
    async def test_both_on_is_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """And the conjunction is reachable — not a gate that never opens."""
        monkeypatch.setattr(flags, "get_client", lambda: _FakePosthog(answer=True))
        monkeypatch.setattr(
            licensing, "is_feature_entitled_blocking", lambda feature: True
        )

        assert await flags.is_feature_available("sso_integration", "user-1") is True

    @pytest.mark.asyncio
    async def test_unlicensed_product_flag_needs_only_the_flag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Product enablement is not licensed, so the flag is the whole gate."""
        monkeypatch.setattr(flags, "get_client", lambda: _FakePosthog(answer=True))
        monkeypatch.delenv("LICENSE_KEY", raising=False)
        licensing.reset_client()

        assert await flags.is_feature_available("gough", "user-1") is True


class TestEvaluateAll:
    """The shape the /features endpoint publishes."""

    @pytest.mark.asyncio
    async def test_every_declared_flag_is_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No key may be absent: the webui must not read absence as false.

        An absent key rendering as "off" is the same defect as an absent
        envelope key rendering as "none" — indistinguishable from a shape
        the client does not understand.
        """
        monkeypatch.setattr(flags, "get_client", lambda: _FakePosthog(answer=False))

        result = await flags.evaluate_all("user-1")

        assert set(result) == flags.KNOWN_FLAGS
        assert all(value is False for value in result.values())

    @pytest.mark.asyncio
    async def test_an_outage_still_returns_every_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Degradation must not truncate the response shape."""
        monkeypatch.setattr(flags, "get_client", lambda: _FakePosthog(raises=True))

        result = await flags.evaluate_all("user-1")

        assert set(result) == flags.KNOWN_FLAGS
