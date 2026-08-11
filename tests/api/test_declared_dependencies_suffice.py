"""The app must run on the dependencies it declares — asserted, not assumed.

``app/licensing.py`` imported a PRIVATE name from a third-party package::

    from penguin_licensing.decorators import _is_bypass_domain

It worked for the whole phase because an editable ``~/code/penguin-libs``
checkout happened to be importable. The RELEASED ``penguin-licensing==0.1.0``
that ``requirements.txt`` hash-pins exports no such name — and no bypass
logic at all — so the container, which installs with
``uv pip install --require-hashes``, failed at import. Thirty collection
errors, and the broken module was the one that decides whether the licence
paywall applies.

This is the same shape as every path-drift defect this migration has paid
for: an assumption about code on the other side of a boundary, with nothing
pinning it. Both checks below are mechanical and would have failed at
authoring time.

Scope, stated honestly
======================
* :class:`TestNoPrivateCrossPackageImports` is STATIC — it reads import
  statements. It cannot see a private attribute reached at runtime
  (``getattr(mod, "_thing")``) or through a module alias.
* :class:`TestTheAppImportsAgainstDeclaredDependencies` is DYNAMIC and
  catches anything that breaks ``import app`` — including the runtime case
  above — but only for modules the package actually imports at import time.
  A private name touched lazily inside a function body is invisible to both
  until that line runs.

Together they cover the failure that actually happened. Neither is a
substitute for running the suite in the venv, which is what
``make test-api`` does.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
from pathlib import Path
from typing import Final

import pytest

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_APP_DIR: Final[Path] = _REPO_ROOT / "services" / "portal-api" / "app"

#: Top-level packages that are OURS. A private name inside the app package
#: is a normal Python convention; a private name reached ACROSS a
#: distribution boundary is a promise nobody made.
_FIRST_PARTY_ROOTS: Final[frozenset[str]] = frozenset({"app", "tests"})

#: Names that look private but are language/stdlib protocol, not another
#: package's internals.
_PROTOCOL_NAMES: Final[frozenset[str]] = frozenset(
    {"__version__", "__all__", "__file__", "__name__", "__doc__", "__path__"}
)

#: Private third-party imports that are accepted, each with the reason and
#: — the load-bearing part — a runtime assertion below that the symbol is
#: still present in the PINNED distribution.
#:
#: An entry here is not a waiver. It converts "vanishes silently on
#: upgrade, discovered at deploy" into "fails a test on upgrade", which is
#: the only difference that mattered in the defect this file exists for.
#:
#: ``quart_schema.extension._build_openapi_schema`` is how the spec
#: exporter renders the document; quart-schema exposes no public equivalent
#: (it builds the schema for its own ``/openapi.json`` route and returns
#: nothing reusable). Reimplementing it would mean reimplementing
#: quart-schema's model introspection, and the blast radius is bounded:
#: this module is used by ``make openapi``, not on any request path, so a
#: future removal breaks spec generation in CI rather than the service.
PRIVATE_IMPORT_EXCEPTIONS: Final[dict[str, tuple[str, str]]] = {
    "quart_schema.extension._build_openapi_schema": (
        "quart_schema.extension",
        "_build_openapi_schema",
    ),
}


def _imported_private_names() -> list[str]:
    """Every ``from <third-party> import _private`` in the app package."""
    offenders: list[str] = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            # A relative import (`from .licensing import ...`) is inside our
            # own package: level > 0 means dots, and it cannot cross a
            # distribution boundary.
            if node.level:
                continue
            module = node.module or ""
            root = module.split(".", 1)[0]
            if root in _FIRST_PARTY_ROOTS:
                continue
            for alias in node.names:
                if alias.name.startswith("_") and alias.name not in _PROTOCOL_NAMES:
                    offenders.append(
                        f"{path.relative_to(_REPO_ROOT)}:{node.lineno} "
                        f"from {module} import {alias.name}"
                    )
    return offenders


class TestNoPrivateCrossPackageImports:
    """A leading underscore is the author saying "this may vanish"."""

    def test_the_app_imports_no_private_third_party_names(self) -> None:
        """It vanished. The released wheel does not carry it at all."""
        offenders = [
            offender
            for offender in _imported_private_names()
            if not any(
                offender.endswith(f"from {module} import {name}")
                for module, name in PRIVATE_IMPORT_EXCEPTIONS.values()
            )
        ]
        assert not offenders, (
            "private names imported across a distribution boundary:\n  "
            + "\n  ".join(offenders)
            + "\nThese resolve only against whatever happens to be on the "
            "path. Ship a local implementation with an upstream-compatible "
            "signature instead — see app/licensing.py::_is_bypass_domain."
        )

    def test_the_scanner_sees_the_imports_it_is_meant_to_check(self) -> None:
        """A set-difference check passes vacuously on an empty left side."""
        modules = 0
        third_party_imports = 0
        for path in sorted(_APP_DIR.rglob("*.py")):
            modules += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and not node.level:
                    root = (node.module or "").split(".", 1)[0]
                    if root and root not in _FIRST_PARTY_ROOTS:
                        third_party_imports += 1
        assert modules > 20, modules
        assert third_party_imports > 20, third_party_imports

    @pytest.mark.parametrize("key", sorted(PRIVATE_IMPORT_EXCEPTIONS))
    def test_an_accepted_private_import_still_exists_upstream(self, key: str) -> None:
        """The exception's whole purpose: fail on upgrade, not on deploy.

        ``_is_bypass_domain`` was accepted implicitly, by nobody checking.
        An accepted private name must be asserted present in the installed
        distribution, so bumping the pin turns a silent removal into a red
        test.
        """
        module_name, attribute = PRIVATE_IMPORT_EXCEPTIONS[key]
        module = importlib.import_module(module_name)
        assert hasattr(module, attribute), (
            f"{key} is gone from the installed {module_name.split('.')[0]}. "
            f"The import in app/ will fail at runtime — replace it or pin "
            f"the previous version deliberately."
        )

    def test_every_exception_is_actually_imported(self) -> None:
        """A stale exception silently re-opens the hole it documented."""
        imported = set(_imported_private_names())
        for module, name in PRIVATE_IMPORT_EXCEPTIONS.values():
            assert any(
                line.endswith(f"from {module} import {name}") for line in imported
            ), f"{module}.{name} is excepted but no longer imported — drop it"

    def test_the_scanner_would_flag_a_private_import(self) -> None:
        """Proves the detector fires, without relying on a live offender."""
        tree = ast.parse("from penguin_licensing.decorators import _is_bypass_domain")
        node = tree.body[0]
        assert isinstance(node, ast.ImportFrom)
        assert not node.level
        assert (node.module or "").split(".", 1)[0] not in _FIRST_PARTY_ROOTS
        assert node.names[0].name.startswith("_")


class TestTheAppImportsAgainstDeclaredDependencies:
    """A container that will not boot becomes a test failure, not a deploy."""

    def test_importing_the_app_package_succeeds(self) -> None:
        """The suite already imports app, but says so here explicitly.

        When this fails the message names the missing symbol, instead of 30
        collection errors that have to be read backwards.
        """
        module = importlib.import_module("app")
        assert module is not None

    def test_every_app_module_imports(self) -> None:
        """A module nothing imports yet can still be broken.

        ``import app`` only executes what the package pulls in. A module
        reached lazily — the pattern this codebase uses for cycles — would
        break in production and nowhere else.
        """
        failures: list[str] = []
        for path in sorted(_APP_DIR.rglob("*.py")):
            if path.name == "__init__.py":
                continue
            relative = path.relative_to(_APP_DIR).with_suffix("")
            name = "app." + ".".join(relative.parts)
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001 - reporting, not handling
                failures.append(f"{name}: {type(exc).__name__}: {exc}")
        assert not failures, "app modules that do not import:\n  " + "\n  ".join(failures)

    @pytest.mark.skipif(
        not (_REPO_ROOT / ".venv" / "bin" / "python").exists(),
        reason="isolated venv not built (make venv-portal-api)",
    )
    def test_the_app_imports_in_the_isolated_venv(self) -> None:
        """The check that would actually have caught this.

        The ambient interpreter has an editable ~/code/penguin-libs on its
        path; the venv has only what requirements.txt pins, which is what
        the Dockerfile installs. Running the same import there is the whole
        difference between "passes here" and "starts in production".
        """
        venv_python = _REPO_ROOT / ".venv" / "bin" / "python"
        # S603: the argv is entirely literal — an interpreter path derived
        # from this file's own location and a fixed `-c import app`. No
        # caller input reaches it.
        result = subprocess.run(  # noqa: S603
            [str(venv_python), "-c", "import app"],
            cwd=_REPO_ROOT / "services" / "portal-api",
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            "`import app` fails against the PINNED dependencies, so the "
            "container cannot start:\n" + result.stderr.strip()[-1500:]
        )

    def test_this_test_is_not_running_against_an_editable_penguin_libs(self) -> None:
        """Says out loud which penguin-libs the current run resolved.

        Not an assertion about which one is correct — the ambient run is
        legitimately editable. It exists so a failure elsewhere can be
        attributed instead of guessed at, which cost this project a
        37-failure false alarm earlier in the phase.
        """
        import penguin_licensing

        origin = str(Path(penguin_licensing.__file__).resolve())
        editable = "/penguin-libs/" in origin
        print(f"penguin_licensing resolved from: {origin} (editable={editable})")
        assert "penguin_licensing" in origin
