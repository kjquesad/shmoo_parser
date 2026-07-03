#!/usr/bin/env python3
"""
Build a database of shmoo example grids for every class, at arbitrary grid
dimensions, from the extracted reference templates (+ hand-authored seeds).

Generalization to any dimension is done by **proportional nearest-neighbor
resampling** of a real 11x11 reference template onto the target rows x cols,
followed by **structure-preserving jitter** that only roughens pass/fail
boundaries (and, for speckle classes, injects a little interior noise). Solid
pass/fail interiors are preserved, so the class signature survives at any size.

Inputs:
  templates.json        {class_id: [grid_string, ...]}  (from extract_templates.py)
  seed_templates.json   {class_id: [grid_string, ...]}  (hand seeds for rule-only classes)

Output:
  shmoo_examples.json   {meta:{...}, examples:[{class_id, family, rows, cols,
                         grid, seed, method}, ...]}

grid_string = rows joined by '_', characters A (pass) / * (fail).

Usage:
  python build_database.py -o shmoo_examples.json --per-class 50 \
      --dims 11x11 18x6 6x18 21x21
"""

import argparse
import json
import random
from collections import OrderedDict, Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Per-family boundary jitter rate (fraction of boundary cells flipped).
FAMILY_JITTER = {
    "crack": 0.12,
    "marginal": 0.10,
    "near-solid": 0.08,
    "passing": 0.08,
    "speckles": 0.14,
}
# Extra interior speckle rate (fraction of interior pass cells flipped to fail).
CLASS_INTERIOR_NOISE = {
    "speckles_curve-BL-to-UR-noisy": 0.06,
    "speckles_curve-BL-to-UR-tight": 0.015,
    "speckles_inmarginal-curve": 0.05,
}


def family_of(class_id):
    return class_id.split("_", 1)[0]


def grid_to_rows(grid_string):
    return [list(r) for r in grid_string.split("_")]


def rows_to_grid(rows):
    return "_".join("".join(r) for r in rows)


def resample(src, H, W):
    """Proportional nearest-neighbor resample of src (list of char-lists) -> HxW."""
    SH = len(src)
    SW = len(src[0])
    out = []
    for r in range(H):
        sr = 0 if H == 1 else round(r / (H - 1) * (SH - 1))
        line = []
        for c in range(W):
            sc = 0 if W == 1 else round(c / (W - 1) * (SW - 1))
            line.append(src[sr][sc])
        out.append(line)
    return out


def jitter(rows, boundary_rate, interior_rate, rng, min_flips=2):
    """Flip boundary cells (roughen edges) and optionally inject interior noise.

    Guarantees at least ``min_flips`` cells change so small grids still yield
    enough unique variants; forced flips prefer boundary cells to preserve
    structure, falling back to random cells only when necessary.
    """
    H = len(rows)
    W = len(rows[0])
    boundary = []
    interior_pass = []
    for r in range(H):
        for c in range(W):
            v = rows[r][c]
            on_boundary = False
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < H and 0 <= cc < W and rows[rr][cc] != v:
                    on_boundary = True
                    break
            if on_boundary:
                boundary.append((r, c))
            elif v == "A":
                interior_pass.append((r, c))

    chosen = set()
    for cell in boundary:
        if rng.random() < boundary_rate:
            chosen.add(cell)
    if interior_rate > 0:
        for cell in interior_pass:
            if rng.random() < interior_rate:
                chosen.add(cell)

    if len(chosen) < min_flips:
        # If too few distinct boundary combinations exist, draw from the whole
        # grid so small grids can still produce enough unique variants. Boundary
        # cells are weighted higher to stay structure-preserving.
        pool = [c for c in boundary if c not in chosen] * 3
        pool += [(r, c) for r in range(H) for c in range(W)
                 if (r, c) not in chosen and (r, c) not in boundary]
        rng.shuffle(pool)
        while pool and len(chosen) < min_flips:
            chosen.add(pool.pop())

    for r, c in chosen:
        rows[r][c] = "A" if rows[r][c] == "*" else "*"
    return rows


def load_templates(templates_path, seeds_path):
    templates = json.loads(Path(templates_path).read_text(encoding="utf-8"))
    seeds = json.loads(Path(seeds_path).read_text(encoding="utf-8"))
    merged = OrderedDict()
    classes = list(templates.keys())
    for cls in classes:
        if cls.startswith("_"):
            continue
        grids = list(templates.get(cls, []))
        for g in seeds.get(cls, []):
            if g not in grids:
                grids.append(g)
        merged[cls] = grids
    # Include any seed-only classes not present in templates (shouldn't happen).
    for cls, grids in seeds.items():
        if cls.startswith("_") or cls in merged:
            continue
        merged[cls] = list(grids)
    return merged


def parse_dims(items):
    dims = []
    for it in items:
        r, _, c = it.lower().partition("x")
        dims.append((int(r), int(c)))
    return dims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", default=str(HERE / "shmoo_examples.json"))
    ap.add_argument("--templates", default=str(HERE / "templates.json"))
    ap.add_argument("--seeds", default=str(HERE / "seed_templates.json"))
    ap.add_argument("--per-class", type=int, default=50,
                    help="Examples per class PER dimension.")
    ap.add_argument("--dims", nargs="+", default=["11x11", "18x6", "6x18", "21x21"],
                    help="Target grid dimensions as ROWSxCOLS.")
    ap.add_argument("--seed", type=int, default=1276)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    templates = load_templates(args.templates, args.seeds)
    dims = parse_dims(args.dims)

    examples = []
    per_class_counts = Counter()
    for cls, grids in templates.items():
        fam = family_of(cls)
        if not grids:
            print(f"[build] WARNING: no templates for {cls}, skipping")
            continue
        b_rate = FAMILY_JITTER.get(fam, 0.10)
        i_rate = CLASS_INTERIOR_NOISE.get(cls, 0.0)
        seeds = [grid_to_rows(g) for g in grids]
        for (H, W) in dims:
            seen = set()
            made = 0
            attempts = 0
            max_attempts = args.per_class * 40
            while made < args.per_class and attempts < max_attempts:
                attempts += 1
                src = rng.choice(seeds)
                grid = resample(src, H, W)
                grid = jitter([row[:] for row in grid], b_rate, i_rate, rng)
                gs = rows_to_grid(grid)
                if gs in seen:
                    continue
                seen.add(gs)
                made += 1
                examples.append(OrderedDict([
                    ("class_id", cls),
                    ("family", fam),
                    ("rows", H),
                    ("cols", W),
                    ("grid", gs),
                    ("method", "resample+jitter"),
                ]))
            per_class_counts[cls] += made
            if made < args.per_class:
                print(f"[build] {cls} {H}x{W}: only {made}/{args.per_class} unique")

    meta = OrderedDict([
        ("generator", "shmoo_db/build_database.py"),
        ("source", "shmoos_descriptions.txt (Shmooify per-class notes)"),
        ("char_pass", "A"),
        ("char_fail", "*"),
        ("row_separator", "_"),
        ("dimensions", [f"{h}x{w}" for (h, w) in dims]),
        ("per_class_per_dim", args.per_class),
        ("num_classes", len([c for c in templates if templates[c]])),
        ("num_examples", len(examples)),
        ("families", sorted({family_of(c) for c in templates})),
    ])
    out = OrderedDict([("meta", meta), ("examples", examples)])
    Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"[build] wrote {args.output}")
    print(f"[build] {meta['num_classes']} classes x {len(dims)} dims -> "
          f"{len(examples)} examples")


if __name__ == "__main__":
    main()
