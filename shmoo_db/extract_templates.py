#!/usr/bin/env python3
"""
Extract the real reference-example shmoo grids for every class from the pasted
Shmooify docs dump, so they can be used as generation seed templates.

For each class section (delimited by ``Source: .../SKILL_<cls>.md``) it scans for
runs of ``Row N: <grid>`` lines, extracts the leading ``A``/``*`` token from each,
and keeps a run as one grid template when the rows share a common width and there
are enough of them. Schematic rows (``Row 3: ***..mixed..**``) are discarded
because their extracted tokens have inconsistent widths.

Output: templates.json  ->  { "<class_id>": ["grid_string", ...], ... }
where grid_string uses rows joined by '_' (chars A / *).
"""

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path

SOURCE_RE = re.compile(r"^Source:\s*static/training_data/.*/SKILL_(?P<cls>.+?)\.md\s*$")
# A grid line: optional "Row N:" prefix, then a leading run of A/* (the grid row),
# optionally followed by whitespace + annotation. Require >=5 cells to avoid prose.
GRID_LINE_RE = re.compile(r"^\s*(?:Row\s*\d+\s*:\s*)?(?P<tok>[A*]{5,})(?:\s.*)?$")
FOOTER = "Other apps from our team that you might like"

MIN_ROWS = 10   # full source grids are 11 rows; ignore short fragments
MAX_ROWS = 12


def split_sections(lines):
    """Yield (class_id, [section_lines])."""
    idxs = [i for i, ln in enumerate(lines) if SOURCE_RE.match(ln)]
    for n, i in enumerate(idxs):
        cls = SOURCE_RE.match(lines[i]).group("cls")
        end = len(lines)
        for k in range(i + 1, len(lines)):
            if lines[k].strip() == FOOTER:
                end = k
                break
        yield cls, lines[i:end]


def extract_grids(section):
    """Return list of grid strings found in a class section."""
    grids = []
    run = []  # list of tokens (current contiguous same-width run)

    def flush():
        nonlocal run
        rows = run
        run = []
        if not rows:
            return
        n = len(rows)
        if MIN_ROWS <= n <= MAX_ROWS:
            grids.append("_".join(rows))
        elif n > MAX_ROWS:
            # Two or more stacked grids with no separator: split into 11-row chunks.
            k = 11
            for s in range(0, n - k + 1, k):
                grids.append("_".join(rows[s:s + k]))

    for ln in section:
        m = GRID_LINE_RE.match(ln)
        if m:
            tok = m.group("tok")
            if run and len(tok) != len(run[0]):
                flush()  # width change starts a new grid
            run.append(tok)
        else:
            flush()
    flush()
    return grids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    lines = Path(args.input).read_text(encoding="utf-8", errors="replace").splitlines()
    out = OrderedDict()
    for cls, section in split_sections(lines):
        grids = extract_grids(section)
        # De-dup while preserving order.
        seen = set()
        uniq = []
        for g in grids:
            if g not in seen:
                seen.add(g)
                uniq.append(g)
        out[cls] = uniq

    Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    total = sum(len(v) for v in out.values())
    print(f"[extract] {len(out)} class(es), {total} template grid(s)")
    for cls, grids in out.items():
        dims = ""
        if grids:
            rows = grids[0].split("_")
            dims = f"{len(rows)}x{len(rows[0])}"
        print(f"    {cls:45s} {len(grids):2d} template(s)  {dims}")


if __name__ == "__main__":
    main()
