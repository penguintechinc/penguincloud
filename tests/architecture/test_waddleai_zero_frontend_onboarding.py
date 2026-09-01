"""Mechanical proof of Phase 8 §8.1's zero-frontend-onboarding claim.

This is the acceptance test itself. Onboarding WaddleAI onto the console —
list-browsable in the webui, a full ``pcli`` command tree — used ONLY
backend artifacts: an adapter package, a manifest, and two registry lines
(``app.adapters.ADAPTER_REGISTRY``/``MANIFEST_REGISTRY`` gaining a
``waddleai`` entry, ``PLANNED_PRODUCTS`` losing one). The webui's
``ProductResourceRoute``/``manifestCapabilities.ts`` and ``pcli`` are already
generic: a read-only manifest auto-routes and auto-discovers with no
per-product frontend or CLI code.

Structural invariant, not a git diff
=====================================
This module used to diff HEAD against ``merge-base(HEAD, origin/release/
v0.1.x)`` via a ``git`` subprocess. Two problems killed that approach: CI's
shallow checkout never fetches ``origin/release/v0.1.x``, so the subprocess
raised ``CalledProcessError`` before a single assertion ran; and even where
the ref resolved, the check was inherently PR-scoped — once this branch
merges and HEAD *is* release, the diff against release is empty, which
would have made "this branch changed something" fail *permanently* on every
release CI run from then on. A merged acceptance test that goes red on the
branch it was proving is unacceptable.

The fix drops git entirely and states the same claim as a fact about the
tree's current shape, checked by walking the filesystem from
:data:`_REPO_ROOT`: WaddleAI is a real, active registry entry (the
non-vacuous half — "no forbidden paths" is true and meaningless for a
product that was never onboarded), and no file anywhere under
``pages/products/``, ``components/kit/``, ``api/resources/``, or a CLI
``commands/`` directory names or references this product outside a comment
or a generic test's fixture data. Every assertion below holds identically
whether HEAD is this feature branch, the release branch after merge, or a
one-commit-deep shallow clone of either — there is nothing left to resolve.

Falsifiability, proven and then reverted
=========================================
A guard nobody has ever seen fail is indistinguishable from a guard that
cannot fail (see ``critical-rules.md``'s Verification Integrity). Before
this rewrite was committed, a throwaway file was added at
``services/webui/src/client/pages/products/waddleai/_falsifiability_probe.tsx``
and the suite was re-run — :func:`test_zero_forbidden_frontend_or_cli_paths_exist`
went red, naming the exact offending path — then the probe file was deleted
and the suite re-run green again. That manual round-trip is not automated
here (a self-reverting probe committed alongside the guard would prove
nothing about a FUTURE violation), but the same mechanism — a synthetic
path or line matching a real forbidden shape — is what
:func:`test_a_deliberately_placed_probe_file_would_be_caught` and
:func:`test_a_product_name_branch_inside_a_generic_file_would_be_caught`
exercise directly and non-destructively, by asserting the two classifiers
(:func:`_touches_forbidden_path`, :func:`_line_names_product`) answer True
for inputs no one added to the tree.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from app.adapters import MANIFEST_REGISTRY, PLANNED_PRODUCTS

#: tests/architecture/this_file.py -> repo root.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: The product this whole module is about. A constant, not a hardcoded
#: literal repeated at every call site, so a future product's copy of this
#: test is a one-line diff.
_PRODUCT: Final[str] = "waddleai"

_WEBUI_CLIENT_ROOT: Final[Path] = _REPO_ROOT / "services/webui/src/client"
_WEBUI_PAGES_PRODUCTS: Final[Path] = _WEBUI_CLIENT_ROOT / "pages/products"
_WEBUI_KIT: Final[Path] = _WEBUI_CLIENT_ROOT / "components/kit"
_CLI_SRC_COMMANDS: Final[Path] = _REPO_ROOT / "services/cli/src/pcli/commands"
_CLI_TEST_COMMANDS: Final[Path] = _REPO_ROOT / "services/cli/tests/commands"

#: Design §8.1's forbidden paths — a per-product webui screen, a per-product
#: kit/cell registry entry, a per-product api-resource client, or a
#: per-product CLI command file are each, on their own, evidence the
#: "manifest-only onboarding" thesis is false for this product. Single
#: source of truth for the literal prefixes/markers both classifiers below
#: are built from.
_FORBIDDEN_PREFIXES: Final[tuple[str, str]] = (
    "services/webui/src/client/pages/products/",
    "services/webui/src/client/components/kit/",
)
_FORBIDDEN_SUBSTRING: Final[str] = "services/cli/"
_COMMANDS_MARKER: Final[str] = "/commands/"
_WEBUI_PREFIX: Final[str] = "services/webui/"

#: Comment prefixes for the three languages under the trees this module
#: walks (TS/TSX line and block comments, Python line comments). A stripped
#: line starting with one of these is documentation, not code — see
#: :func:`_line_names_product`.
_COMMENT_LINE_PREFIXES: Final[tuple[str, ...]] = ("//", "/*", "*", "#")

#: Noise directories to skip while walking — a populated ``node_modules``
#: (not present in this checkout, but not guaranteed) must not inflate,
#: slow, or false-positive this walk.
_NOISE_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {"node_modules", "dist", "build", ".next", "coverage", "__pycache__", ".pytest_cache", ".git"}
)

#: A generic test proving the renderer/CLI works for ANY product — including
#: this one, as one example among several — is not itself per-product
#: production code; a real per-product test FILE (``test_waddleai.py``) is
#: already caught by :func:`_touches_forbidden_path`'s filename check.
_TEST_FILE_SUFFIXES: Final[tuple[str, ...]] = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")


def _iter_files(root: Path) -> list[Path]:
    """Every regular file under ``root``, deterministically ordered, noise excluded."""
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not _NOISE_DIR_NAMES & set(path.relative_to(root).parts)
    )


def _touches_forbidden_path(path: str) -> bool:
    """True if ``path`` (repo-root-relative, POSIX) is itself Design §8.1's forbidden shape.

    Four independent shapes, checked in order: a screen dir/file directly
    under ``pages/products/`` named for this product, a ``components/kit/``
    file naming it anywhere in the filename, a CLI ``commands/`` file
    (source or test, any depth under ``services/cli/``) naming it, and any
    other webui file naming it (the broadest of the four — a superset of
    the literal ``api/resources/waddleai*`` case, deliberately, since a
    stray per-product file named for this product anywhere under
    ``services/webui/`` is exactly as much a violation as one in
    ``api/resources/``). Existing generic files that merely LIVE under
    these directories — ``ProductPage.tsx``, ``manifestCapabilities.ts``,
    the ``gough``/``nest``/``tobogganing`` product dirs — match none of
    these: only a path segment or filename actually naming this product
    does.
    """
    name = Path(path).name.lower()

    pages_products_prefix = _FORBIDDEN_PREFIXES[0]
    if path.startswith(pages_products_prefix):
        first_segment = path[len(pages_products_prefix) :].split("/", 1)[0]
        if first_segment.lower().startswith(_PRODUCT):
            return True

    kit_prefix = _FORBIDDEN_PREFIXES[1]
    if path.startswith(kit_prefix) and _PRODUCT in name:
        return True

    if path.startswith(_FORBIDDEN_SUBSTRING) and _COMMANDS_MARKER in path and _PRODUCT in name:
        return True

    if path.startswith(_WEBUI_PREFIX) and _PRODUCT in name:
        return True

    return False


def _is_test_file(rel_path: str) -> bool:
    """True if ``rel_path`` is itself a test file, not production source.

    A generic test's fixture data (e.g. ``ProductPage.test.tsx`` picking
    ``product_type: "waddleai"`` as one of several example products) is
    exempt from :func:`_line_names_product` scanning for the same reason a
    parametrized backend test using this product's name is not a
    violation: it proves genericness, it does not implement a per-product
    branch.
    """
    return (
        "__tests__/" in rel_path or "/tests/" in rel_path or rel_path.endswith(_TEST_FILE_SUFFIXES)
    )


def _line_names_product(line: str) -> bool:
    """True if ``line`` is genuine code naming this product — not a comment mentioning it.

    A JSDoc/block-comment line, a ``//`` comment, or a Python ``#`` comment
    referencing the product by name (as this file's own docstring, and the
    real ``manifestCapabilities.ts`` doc comment it describes, both do) is
    documentation, not "a product-name branch added inside an existing
    generic file" — only a live code line naming the product is that.
    """
    stripped = line.strip()
    if stripped.startswith(_COMMENT_LINE_PREFIXES):
        return False
    return _PRODUCT in line.lower()


def _real_forbidden_path_offenders() -> list[str]:
    """Every real file on disk whose PATH matches a Design §8.1 forbidden shape."""
    offenders: set[str] = set()
    for root in (_WEBUI_CLIENT_ROOT, _CLI_SRC_COMMANDS, _CLI_TEST_COMMANDS):
        for path in _iter_files(root):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            if _touches_forbidden_path(rel):
                offenders.add(rel)
    return sorted(offenders)


def _real_forbidden_content_offenders() -> list[tuple[str, int, str]]:
    """Every real ``(path, line_no, line)`` naming this product inside a generic forbidden file.

    Reads straight off disk — no git, no diff — so this holds identically
    before and after merge, and on a checkout of any depth.
    """
    offenders: list[tuple[str, int, str]] = []
    for root in (_WEBUI_PAGES_PRODUCTS, _WEBUI_KIT, _CLI_SRC_COMMANDS, _CLI_TEST_COMMANDS):
        for path in _iter_files(root):
            rel = path.relative_to(_REPO_ROOT).as_posix()
            if _is_test_file(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            offenders.extend(
                (rel, lineno, line.strip())
                for lineno, line in enumerate(text.splitlines(), start=1)
                if _line_names_product(line)
            )
    return offenders


def test_waddleai_is_registered_and_not_merely_planned() -> None:
    """The non-vacuous guard every assertion below rests on.

    "Zero waddleai frontend/CLI paths" is true — but meaningless — for a
    product that was never onboarded at all. This pins down that WaddleAI
    is a real, active manifest/adapter registry entry, not a
    ``PLANNED_PRODUCTS`` catalogue-only stub.
    """
    assert _PRODUCT in MANIFEST_REGISTRY, f"{_PRODUCT!r} missing from MANIFEST_REGISTRY"
    assert _PRODUCT not in PLANNED_PRODUCTS, f"{_PRODUCT!r} still listed as merely planned"


def test_a_deliberately_placed_probe_file_would_be_caught() -> None:
    """Falsifiability check: the path classifier, exercised against synthetic paths.

    Proves :func:`_touches_forbidden_path` is not vacuously True/False for
    every input — each assertion below names the exact §8.1 case it guards,
    matching the manual red/green probe recorded in the module docstring.
    """
    assert _touches_forbidden_path(
        "services/webui/src/client/pages/products/waddleai/WaddleAIScreen.tsx"
    )
    assert _touches_forbidden_path("services/webui/src/client/components/kit/waddleaiCells.tsx")
    assert _touches_forbidden_path("services/cli/src/pcli/commands/waddleai.py")
    assert _touches_forbidden_path("services/cli/tests/commands/test_waddleai.py")
    assert _touches_forbidden_path("services/webui/src/client/api/resources/waddleai.ts")
    # Negative cases: real files this PR does add, none of which is forbidden.
    assert not _touches_forbidden_path("services/portal-api/app/adapters/waddleai/adapter.py")
    assert not _touches_forbidden_path("tests/api/test_waddleai_adapter.py")
    # A pre-existing per-product webui api-resource file for ANOTHER product —
    # under services/webui/ but naming neither "waddleai" nor a forbidden
    # directory, so the filename-marker check must not over-match on the
    # shared "services/webui/" prefix alone.
    assert not _touches_forbidden_path("services/webui/src/client/api/resources/tobogganing.ts")
    # Two real files that DO exist in this tree today, under forbidden
    # prefixes, and DO mention this product — a generic test's __tests__
    # dir and a generic module's doc comment — neither is a per-product
    # screen or CLI command, so the path classifier must not flag either;
    # content-level exemption for these is a separate classifier, proven in
    # test_a_product_name_branch_inside_a_generic_file_would_be_caught.
    assert not _touches_forbidden_path(
        "services/webui/src/client/pages/products/__tests__/ProductPage.test.tsx"
    )
    assert not _touches_forbidden_path(
        "services/webui/src/client/components/kit/manifestCapabilities.ts"
    )


def test_a_product_name_branch_inside_a_generic_file_would_be_caught() -> None:
    """Falsifiability check: the content classifier, exercised against synthetic lines.

    :func:`_touches_forbidden_path` cannot see a branch added inside a file
    whose own name/location is unremarkable — this proves
    :func:`_line_names_product` can, while also proving it does not flag
    the two legitimate mentions this exact tree contains today (a doc
    comment and a generic test's fixture data).
    """
    assert _line_names_product('if (productType === "waddleai") return <Special />;')
    assert _line_names_product("WADDLEAI_SPECIAL_CASE = True")
    # Comments referencing the product by name are documentation, not a
    # branch — matches the real manifestCapabilities.ts doc comment.
    assert not _line_names_product(" * the mechanism WaddleAI acceptance test §8.1 requires")
    assert not _line_names_product("// see waddleai for an example")
    assert not _line_names_product("# waddleai is handled generically here")
    # No mention at all is trivially not a violation.
    assert not _line_names_product("export function genericRenderer() {}")
    # A generic test's fixture data — matches the real ProductPage.test.tsx
    # line — is filtered at the file level by _is_test_file, not by this
    # classifier, so taken alone it WOULD read as naming the product.
    assert _line_names_product('  product_type: "waddleai",')
    assert _is_test_file("services/webui/src/client/pages/products/__tests__/ProductPage.test.tsx")
    assert not _is_test_file("services/webui/src/client/components/kit/manifestCapabilities.ts")


def test_zero_forbidden_frontend_or_cli_paths_exist() -> None:
    """THE acceptance assertion, path half: no forbidden file/dir exists for this product.

    Reads the filesystem directly — no git — so this is exactly as true
    today, mid-review, and after this branch has merged into release and
    HEAD *is* release (when a git-diff-based version of this check would
    have gone permanently, vacuously green on an empty diff, or worse,
    permanently red for "nothing to check").
    """
    offenders = _real_forbidden_path_offenders()
    assert offenders == [], (
        f"{_PRODUCT!r} has a hand-written frontend/CLI path: {offenders!r} — "
        f"the whole point of this acceptance test is that onboarding this "
        f"product needed zero per-product webui/CLI code"
    )


def test_zero_forbidden_content_mentions_in_generic_files() -> None:
    """THE acceptance assertion, content half: no generic file has a live branch for this product.

    Catches the failure mode :func:`test_zero_forbidden_frontend_or_cli_paths_exist`
    cannot see, because that test only looks at paths: a product-name
    conditional or constant added INSIDE an already-generic file (e.g.
    ``ProductResourceRoute.tsx`` growing an ``if (productType ===
    "waddleai")`` branch). Doc comments and test fixtures naming the
    product are deliberately exempt — see :func:`_line_names_product` and
    :func:`_is_test_file`, and the two real examples of each already in
    this tree.
    """
    offenders = _real_forbidden_content_offenders()
    assert offenders == [], (
        f"a generic file under pages/products/, components/kit/, or a CLI "
        f"commands directory has a live code line naming {_PRODUCT!r}: "
        f"{offenders!r} — that is a per-product branch, not the generic "
        f"renderer/command-tree this test proves exists instead"
    )


@pytest.mark.parametrize(
    "expected_path",
    [
        "services/portal-api/app/adapters/waddleai/adapter.py",
        "services/portal-api/app/adapters/waddleai/manifest.py",
        "services/portal-api/app/adapters/waddleai/routes.py",
        "services/portal-api/app/adapters/waddleai/mapping.py",
    ],
)
def test_the_real_onboarding_files_exist(expected_path: str) -> None:
    """The positive control: the backend artifacts this product's onboarding needs are there.

    Without this, a tree that (incorrectly) had none of WaddleAI's backend
    adapter code would still pass every guard above — this proves the
    product was actually onboarded, not just that nothing forbidden exists.
    Checked by existence on disk, not by diff membership, so it holds
    identically before and after merge.
    """
    assert (
        _REPO_ROOT / expected_path
    ).is_file(), f"{expected_path!r} does not exist — WaddleAI onboarding incomplete"
