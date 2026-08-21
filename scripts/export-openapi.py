#!/usr/bin/env python3
"""Export the portal's OpenAPI document to openapi/v{major}.yaml.

The committed spec is GENERATED, never hand-edited. It is derived from the
live Quart route table and the type annotations on each view, so it cannot
describe an endpoint the service does not serve, or miss one it does.

Run via ``make openapi``. CI re-runs it and fails if the working tree
changes, which is what stops the committed document drifting from the code
between releases — the failure mode a hand-maintained spec has no defence
against.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "services" / "portal-api"

# The app package is imported as top-level `app`, matching tests/conftest.py.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

#: Major version of the API this document describes. The filename encodes it
#: (openapi/v1.yaml) because a breaking change ships a NEW document rather
#: than mutating this one — see backend.md API Versioning.
API_MAJOR = 1


def _build_spec() -> dict[str, Any]:
    """Construct the app in test configuration and generate its document.

    TestingConfig is used deliberately: generating the spec must not require
    a reachable database, a license server, or real signing keys. Only the
    route table and annotations matter, and those are identical across
    configurations.
    """
    os.environ.setdefault("TESTING", "true")

    from app import create_app  # noqa: E402 — sys.path is set above
    from app.config import TestingConfig  # noqa: E402
    from app.openapi import build_full_spec  # noqa: E402

    app = create_app(config_class=TestingConfig)
    return build_full_spec(app)


#: Paths excluded from the published document. Quart registers a static
#: file route on every app; it is not part of the API contract and would
#: appear in every generated client SDK as a first-class operation.
EXCLUDED_PATHS = frozenset({"/static/{filename}"})


def _normalise(node: Any) -> Any:
    """Make the generated structure safe and stable to serialise.

    Three concrete problems with the raw output:

    * ``defaultdict`` — quart-schema builds paths as one, and
      ``yaml.safe_dump`` refuses any type it does not have a representer
      for. Using ``yaml.dump`` instead would "fix" it by emitting Python
      object tags into a document other tools then reject.
    * Integer response keys — OpenAPI status codes are strings. PyYAML
      would emit a bare ``200:``, which parses as an integer key and makes
      the document fail schema validation.
    * Set-typed values, if any ever appear, serialise unordered and would
      churn the committed file between runs.
    """
    if isinstance(node, dict):
        return {str(key): _normalise(value) for key, value in node.items()}
    if isinstance(node, list | tuple):
        return [_normalise(value) for value in node]
    if isinstance(node, set | frozenset):
        return sorted(_normalise(value) for value in node)
    return node


def main() -> int:
    """Write the spec, or verify the committed copy is current."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Do not write. Exit non-zero if the committed spec differs from "
            "what the current code would generate (for CI)."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "openapi" / f"v{API_MAJOR}.yaml",
        help="Destination path for the generated document.",
    )
    args = parser.parse_args()

    try:
        import yaml
    except ImportError:  # pragma: no cover - PyYAML is a declared dependency
        print("PyYAML is required: pip install pyyaml", file=sys.stderr)
        return 1

    # This used to carry `# type: ignore[misc]`: on a PEP 668 interpreter
    # types-PyYAML could not be installed, `yaml.SafeDumper` resolved to Any,
    # and mypy rejects subclassing an Any base. The mypy hook now runs from
    # the project venv, where types-PyYAML is pinned, so the stubs resolve
    # and the ignore became `unused-ignore` — removed rather than kept as
    # debris. If mypy is ever pointed back at an ambient interpreter this
    # will fail again, which is the correct signal: fix the interpreter.
    class _IndentedDumper(yaml.SafeDumper):
        """SafeDumper that indents block sequences under their parent key.

        PyYAML writes a sequence flush with the mapping key that owns it.
        That is valid YAML, but the repo's yamllint configuration (and most
        readers) expect the nested form, so the generated file would fail
        `make lint` on every regeneration.
        """

        def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
            super().increase_indent(flow, False)

    spec = _normalise(_build_spec())
    spec["paths"] = {
        path: item for path, item in spec.get("paths", {}).items() if path not in EXCLUDED_PATHS
    }
    rendered = yaml.dump(
        spec,
        Dumper=_IndentedDumper,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
        # PyYAML's width is a soft break-at-or-after-this-column preference,
        # not a hard cap -- it can overshoot to the next space by the length
        # of one word. .yamllint.yml's line-length max is 130. width=120
        # overshot it twice independently: a 131-char line from a docstring,
        # and GET /api/v1/products/health's description. 90 leaves a 40-char
        # margin -- more headroom than either overshoot needed -- so the
        # class of failure is closed rather than one line being shortened.
        width=90,
    )
    header = (
        "# GENERATED FILE — DO NOT EDIT.\n"
        "# Regenerate with: make openapi\n"
        f"# Source: services/portal-api route table (API v{API_MAJOR}).\n"
    )
    document = header + rendered

    if args.check:
        if not args.output.exists():
            print(f"{args.output} is missing; run `make openapi`", file=sys.stderr)
            return 1
        if args.output.read_text() != document:
            print(
                f"{args.output} is stale; run `make openapi` and commit the result",
                file=sys.stderr,
            )
            return 1
        print(f"{args.output} is up to date")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document)
    paths = len(spec.get("paths", {}))
    print(f"Wrote {args.output} ({paths} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
