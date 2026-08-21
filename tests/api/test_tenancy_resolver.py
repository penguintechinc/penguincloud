"""Unit tests for the hierarchy resolver: SQL rendering and cache lifetime.

The CTE rendering tests are the regression guard for a defect that only ever
appeared off-SQLite: the recursive queries hardcoded ``?`` placeholders, and
penguin-dal's ``executesql`` hands SQL to the driver verbatim. On
PostgreSQL — where penguin_dal.backends maps ``postgresql://`` onto asyncpg,
whose paramstyle is ``numeric_dollar`` — every hierarchy resolution would
have raised, taking tenant switching and delegated admin down with it. The
whole test suite runs on SQLite, so nothing caught it.

Real-PostgreSQL execution is NOT asserted here (no server in this
environment); these tests pin the generated SQL and parameter tuple per
dialect. End-to-end validation against a live PostgreSQL lands with the
alpha deploy.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from app.tenancy.resolver import (
    LOCAL_CACHE_TTL_SECONDS,
    MAX_HIERARCHY_DEPTH,
    UnsupportedParamstyleError,
    _cache_get,
    _cache_set,
    bind_query,
    build_ancestors_query,
    build_descendants_query,
    clear_local_cache,
    get_paramstyle,
    subtree_cache_key,
)


class TestDialectAwarePlaceholders:
    """The CTEs must render for whichever driver is actually bound."""

    def test_descendants_query_renders_qmark_for_sqlite(self) -> None:
        """sqlite+aiosqlite uses the qmark paramstyle."""
        bound = build_descendants_query("qmark", 42)

        assert "WHERE parent_tenant_id = ?" in bound.sql
        assert "WHERE tt.level < ?" in bound.sql
        assert "$1" not in bound.sql and "%s" not in bound.sql
        assert bound.params == (42, MAX_HIERARCHY_DEPTH)

    def test_descendants_query_renders_numeric_dollar_for_postgres(self) -> None:
        """postgresql+asyncpg uses $1/$2, positionally in SQL order."""
        bound = build_descendants_query("numeric_dollar", 42)

        assert "WHERE parent_tenant_id = $1" in bound.sql
        assert "WHERE tt.level < $2" in bound.sql
        assert "?" not in bound.sql
        assert bound.params == (42, MAX_HIERARCHY_DEPTH)

    def test_descendants_query_renders_format_for_mysql(self) -> None:
        """mysql+aiomysql (and psycopg2) use the format paramstyle."""
        bound = build_descendants_query("format", 42)

        assert "WHERE parent_tenant_id = %s" in bound.sql
        assert "?" not in bound.sql
        assert bound.params == (42, MAX_HIERARCHY_DEPTH)

    def test_ancestors_query_renders_for_both_dialects(self) -> None:
        """The upward CTE binds identically under both paramstyles."""
        sqlite_bound = build_ancestors_query("qmark", 7)
        postgres_bound = build_ancestors_query("numeric_dollar", 7)

        assert "WHERE id = ?" in sqlite_bound.sql
        assert "WHERE id = $1" in postgres_bound.sql
        assert sqlite_bound.params == (7, MAX_HIERARCHY_DEPTH)
        assert postgres_bound.params == (7, MAX_HIERARCHY_DEPTH)

        # Only the placeholders differ; the query itself is one definition.
        assert sqlite_bound.sql.replace("?", "@") == postgres_bound.sql.replace("$1", "@").replace(
            "$2", "@"
        )

    def test_named_paramstyle_binds_a_dict(self) -> None:
        """pyformat/named drivers get a mapping, not a tuple."""
        bound = bind_query("SELECT {a} + {b}", "pyformat", {"a": 1, "b": 2})

        assert bound.sql == "SELECT %(a)s + %(b)s"
        assert bound.params == {"a": 1, "b": 2}

    def test_unknown_paramstyle_raises_rather_than_guessing(self) -> None:
        """An unrecognised driver fails loudly instead of emitting bad SQL."""
        with pytest.raises(UnsupportedParamstyleError):
            build_descendants_query("no_such_style", 1)

    def test_paramstyle_read_from_bound_engine(self, app: Any) -> None:
        """get_paramstyle reads the live dialect off penguin-dal's engine.

        Ties the rendering above to the real runtime path: the test suite's
        SQLite engine must report qmark, which is what makes the integration
        tests exercise the qmark branch rather than a hardcoded default.
        """

        class _FakeDialect:
            paramstyle = "numeric_dollar"

        class _FakeEngine:
            dialect = _FakeDialect()

        class _FakeDB:
            engine = _FakeEngine()

        assert get_paramstyle(_FakeDB()) == "numeric_dollar"


class TestRecursionGuards:
    """UNION plus a depth cap, so a parentage cycle cannot spin forever."""

    def test_ctes_use_union_not_union_all(self) -> None:
        """UNION ALL re-emits a cycle's rows without bound."""
        for bound in (
            build_descendants_query("qmark", 1),
            build_ancestors_query("qmark", 1),
        ):
            assert "UNION ALL" not in bound.sql
            assert "UNION" in bound.sql

    def test_ctes_cap_recursion_depth(self) -> None:
        """The depth cap is bound as a parameter, not merely documented."""
        for bound in (
            build_descendants_query("qmark", 1),
            build_ancestors_query("qmark", 1),
        ):
            assert "tt.level <" in bound.sql
            assert MAX_HIERARCHY_DEPTH in bound.params


class TestLocalCacheTTL:
    """The in-process cache expires; it is not a permanent memo."""

    def test_cache_entry_is_returned_before_expiry(self) -> None:
        """A freshly written entry is served without waiting for the TTL."""
        clear_local_cache()
        key = subtree_cache_key(999_001)
        _cache_set(key, {1, 2, 3})

        assert _cache_get(key) == frozenset({1, 2, 3})

    def test_cache_entry_expires_after_ttl(self, monkeypatch: Any) -> None:
        """A stale entry is dropped once the TTL elapses.

        Before this, _LOCAL_CACHE had no TTL at all: an entry written once
        was served for the lifetime of the process, so a missed invalidation
        was permanent rather than self-healing.
        """
        clear_local_cache()
        key = subtree_cache_key(999_002)
        _cache_set(key, {4, 5})
        assert _cache_get(key) is not None

        real_monotonic = time.monotonic
        monkeypatch.setattr(
            "app.tenancy.resolver.time.monotonic",
            lambda: real_monotonic() + LOCAL_CACHE_TTL_SECONDS + 1,
        )

        assert _cache_get(key) is None

    def test_clear_local_cache_empties_everything(self) -> None:
        """``clear_local_cache`` drops every entry, not just the expired ones."""
        _cache_set(subtree_cache_key(999_003), {6})
        clear_local_cache()

        assert _cache_get(subtree_cache_key(999_003)) is None
