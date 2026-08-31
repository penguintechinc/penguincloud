/**
 * Drift guard: `CELL_KINDS`/`FIELD_TYPES` (this TS mirror) vs their Python
 * source of truth in `app/adapters/manifest.py`.
 *
 * Reads the Python file as TEXT rather than executing it — the same
 * technique `tests/api/test_webui_portal_paths.py` already uses in the
 * OTHER direction (a Python test parsing `portalPaths.ts` as text, per that
 * file's own module doc: "importing it would need a JS runtime in the
 * Python suite, and parsing the literal keeps the assertion in the suite
 * that owns the route it is comparing against"). Executing `manifest.py`
 * from a jest test would need a Python interpreter present in the webui CI
 * job (`test-webui` in `.github/workflows/ci.yml` sets up Node only, no
 * Python step) — parsing avoids that dependency entirely.
 */

import { readFileSync, existsSync } from "fs";
import { resolve } from "path";
import { CELL_KINDS, FIELD_TYPES } from "../manifestTypes";

const MANIFEST_PY = resolve(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "..",
  "..",
  "portal-api",
  "app",
  "adapters",
  "manifest.py",
);

const CELL_KINDS_BLOCK_RE =
  /CELL_KINDS:\s*Final\[frozenset\[str\]\]\s*=\s*frozenset\(\s*\{([\s\S]*?)\}\s*\)/;
// `[a-z0-9_-]` (not just `[a-z_]`) because `FIELD_TYPES` needs the same
// parser and one of its members is `"datetime-local"` — a hyphen the
// original CELL_KINDS-only pattern would silently drop.
const QUOTED_STRING_RE = /"([a-z0-9_-]+)"/g;

function pythonFrozensetMembers(
  source: string,
  blockRe: RegExp,
  name: string,
): string[] {
  const block = blockRe.exec(source);
  if (!block) {
    throw new Error(
      `${name} frozenset literal not found in manifest.py — update the ` +
        `block regex, do not delete this assertion`,
    );
  }
  return [...block[1].matchAll(QUOTED_STRING_RE)].map((m) => m[1]);
}

function pythonCellKinds(source: string): string[] {
  return pythonFrozensetMembers(source, CELL_KINDS_BLOCK_RE, "CELL_KINDS");
}

describe("CELL_KINDS <-> app/adapters/manifest.py", () => {
  it("finds the Python source this test compares against", () => {
    expect(existsSync(MANIFEST_PY)).toBe(true);
  });

  it("matches the Python CELL_KINDS frozenset exactly", () => {
    const source = readFileSync(MANIFEST_PY, "utf-8");
    const pythonKinds = pythonCellKinds(source);

    expect(pythonKinds.length).toBeGreaterThan(0);
    expect(new Set(CELL_KINDS)).toEqual(new Set(pythonKinds));
    // Also pins TS-side duplicates/typos the Set comparison alone would hide.
    expect(CELL_KINDS.length).toBe(new Set(CELL_KINDS).size);
  });

  it("falsifies: the parser actually reads the frozenset, not an empty match", () => {
    const fixture = `
CELL_KINDS: Final[frozenset[str]] = frozenset(
    {
        "alpha",
        "beta",
    }
)
`;
    expect(pythonCellKinds(fixture)).toEqual(["alpha", "beta"]);
  });
});

const FIELD_TYPES_BLOCK_RE =
  /FIELD_TYPES:\s*Final\[frozenset\[str\]\]\s*=\s*frozenset\(\s*\{([\s\S]*?)\}\s*\)/;

function pythonFieldTypes(source: string): string[] {
  return pythonFrozensetMembers(source, FIELD_TYPES_BLOCK_RE, "FIELD_TYPES");
}

describe("FIELD_TYPES <-> app/adapters/manifest.py", () => {
  it("matches the Python FIELD_TYPES frozenset exactly", () => {
    const source = readFileSync(MANIFEST_PY, "utf-8");
    const pythonTypes = pythonFieldTypes(source);

    expect(pythonTypes.length).toBeGreaterThan(0);
    expect(new Set(FIELD_TYPES)).toEqual(new Set(pythonTypes));
    expect(FIELD_TYPES.length).toBe(new Set(FIELD_TYPES).size);
  });

  it("includes the hyphenated member the CELL_KINDS-only pattern would have dropped", () => {
    const source = readFileSync(MANIFEST_PY, "utf-8");
    expect(pythonFieldTypes(source)).toContain("datetime-local");
  });
});
