#!/usr/bin/env python3
"""
Build a label set (training seed) from one or more ``shmoo_parsed.json`` files.

For every shmoo it:
  * recomputes the numeric feature vector with the shared feature module
    (so training features exactly match what the rule classifier / model use),
  * records the current rule-based category as the *suggested* label, and
  * emits a stable key so labels can be merged / re-imported later.

Two outputs are written next to ``-o`` (an output directory):

  labels.csv        Canonical, human-editable label store. One row per shmoo with
                    a ``label`` column pre-filled from the rule suggestion. Edit
                    this file (or use ``label_tool.html``) to correct labels, then
                    feed it to ``train_model.py``.

  labels_data.json  Companion payload consumed by ``label_tool.html`` so the
                    browser labeler can render each shmoo grid. Not used for
                    training directly.

Usage:
  python build_label_set.py PARSED_JSON [PARSED_JSON ...] -o OUT_DIR
  python build_label_set.py runs/ -o OUT_DIR --per-class 40 --seed 7

Pure stdlib (imports the shared feature module which is also stdlib-only).
"""

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

# Make the shared feature module importable whether run as a script or module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    rows_to_matrix,
    compute_features,
    features_to_vector,
)


# ---------------------------------------------------------------------------
# Input gathering
# ---------------------------------------------------------------------------
def _resolve_input_files(inputs):
    """Expand files/folders into a list of shmoo_parsed.json paths."""
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.rglob("shmoo_parsed.json")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"[build_label_set] WARNING: not found, skipping: {item}")
    # De-dup while keeping order.
    seen = set()
    unique = []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(f)
    return unique


def _iter_shmoo_entries(shmoos):
    """Iterate entries for both flat and nested shmoos structures."""
    for _vid_key, val in shmoos.items():
        if isinstance(val, list):
            for entry in val:
                yield entry
        elif isinstance(val, dict):
            for _src, entries in val.items():
                if isinstance(entries, list):
                    for entry in entries:
                        yield entry


def _stable_key(entry, dup_counter):
    """Build a stable, reproducible key for a shmoo entry."""
    src = entry.get("source_file", "") or ""
    vid = entry.get("visual_id") or "NO_VID"
    inst = entry.get("instance", "") or ""
    plist = entry.get("plist", "") or ""
    base = f"{Path(src).name}|{vid}|{inst}|{plist}"
    n = dup_counter[base]
    dup_counter[base] += 1
    return f"{base}|{n}"


# ---------------------------------------------------------------------------
# Record building
# ---------------------------------------------------------------------------
def build_records(files):
    """Return a list of per-shmoo records with features + suggested label."""
    records = []
    dup_counter = defaultdict(int)

    for fpath in files:
        try:
            data = json.loads(Path(fpath).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[build_label_set] WARNING: cannot read {fpath}: {exc}")
            continue

        shmoos = data.get("shmoos", {})
        for entry in _iter_shmoo_entries(shmoos):
            rows = entry.get("failing_data", {}).get("rows", [])
            if not rows:
                continue  # no grid -> nothing to label / featurize

            matrix = rows_to_matrix(rows)
            features = compute_features(matrix)

            existing = entry.get("classification") or {}
            suggested = existing.get("category") or "unknown"

            axis = entry.get("axis", {}) or {}
            key = _stable_key(entry, dup_counter)

            records.append({
                "key": key,
                "source_file": entry.get("source_file", ""),
                "visual_id": entry.get("visual_id") or "",
                "instance": entry.get("instance", ""),
                "plist": entry.get("plist", ""),
                "die_id": entry.get("die_id", ""),
                "vmin_found": entry.get("vmin_found", ""),
                "num_rows": features.get("num_rows", len(matrix)),
                "num_cols": features.get("num_cols", len(matrix[0]) if matrix else 0),
                "suggested_label": suggested,
                "features": features,
                # kept only for labels_data.json (not written to CSV)
                "_rows": rows,
                "_xlabel": axis.get("xlabel", ""),
                "_ylabel": axis.get("ylabel", ""),
            })

    return records


def stratified_sample(records, per_class, seed):
    """Cap the number of records per suggested label for balanced labeling."""
    if not per_class or per_class <= 0:
        return records
    rng = random.Random(seed)
    by_class = defaultdict(list)
    for r in records:
        by_class[r["suggested_label"]].append(r)
    sampled = []
    for label, group in by_class.items():
        if len(group) > per_class:
            sampled.extend(rng.sample(group, per_class))
        else:
            sampled.extend(group)
    sampled.sort(key=lambda r: (r["suggested_label"], r["key"]))
    return sampled


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------
def write_labels_csv(records, out_csv):
    """Write the canonical, editable labels.csv."""
    meta_cols = [
        "key", "label", "label2", "suggested_label",
        "source_file", "visual_id", "instance", "plist", "die_id",
        "vmin_found", "num_rows", "num_cols",
    ]
    header = meta_cols + list(FEATURE_NAMES)

    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for r in records:
            vec = features_to_vector(r["features"])
            row = [
                r["key"],
                r["suggested_label"],  # primary label pre-filled from rule suggestion
                "",                     # label2: optional second category (blank)
                r["suggested_label"],
                r["source_file"],
                r["visual_id"],
                r["instance"],
                r["plist"],
                r["die_id"],
                r["vmin_found"],
                r["num_rows"],
                r["num_cols"],
            ]
            row.extend(f"{v:.6g}" for v in vec)
            writer.writerow(row)


def write_labels_data_json(records, out_json):
    """Write the companion payload used by label_tool.html for rendering."""
    payload = {
        "feature_names": list(FEATURE_NAMES),
        "shmoos": [
            {
                "key": r["key"],
                "suggested_label": r["suggested_label"],
                "visual_id": r["visual_id"],
                "instance": r["instance"],
                "plist": r["plist"],
                "die_id": r["die_id"],
                "vmin_found": r["vmin_found"],
                "num_rows": r["num_rows"],
                "num_cols": r["num_cols"],
                "xlabel": r["_xlabel"],
                "ylabel": r["_ylabel"],
                "rows": r["_rows"],
                "features": r["features"],
            }
            for r in records
        ],
    }
    Path(out_json).write_text(
        json.dumps(payload, separators=(",", ":")), encoding="utf-8"
    )


def print_summary(records):
    counts = defaultdict(int)
    for r in records:
        counts[r["suggested_label"]] += 1
    total = len(records)
    print(f"\n{'='*60}")
    print(f"  Label Set — {total} shmoos (suggested labels)")
    print(f"{'='*60}")
    for label, n in sorted(counts.items(), key=lambda x: -x[1]):
        pct = (n / total * 100) if total else 0
        print(f"  {label:<22s} : {n:>4d}  ({pct:5.1f}%)")
    print(f"{'='*60}\n")


def main():
    ap = argparse.ArgumentParser(
        description="Build a label set (labels.csv + labels_data.json) from "
                    "shmoo_parsed.json files."
    )
    ap.add_argument("inputs", nargs="+",
                    help="shmoo_parsed.json file(s) and/or folder(s) to scan.")
    ap.add_argument("-o", "--out-dir", required=True,
                    help="Output directory for labels.csv and labels_data.json.")
    ap.add_argument("--per-class", type=int, default=0,
                    help="Cap shmoos per suggested label (stratified). 0 = all.")
    ap.add_argument("--seed", type=int, default=13,
                    help="Random seed for stratified sampling.")
    args = ap.parse_args()

    files = _resolve_input_files(args.inputs)
    if not files:
        print("[build_label_set] No input shmoo_parsed.json files found.")
        sys.exit(1)
    print(f"[build_label_set] Reading {len(files)} parsed file(s):")
    for f in files:
        print(f"    {f}")

    records = build_records(files)
    if not records:
        print("[build_label_set] No shmoos with grids found; nothing to label.")
        sys.exit(1)

    records = stratified_sample(records, args.per_class, args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "labels.csv"
    out_json = out_dir / "labels_data.json"

    write_labels_csv(records, out_csv)
    write_labels_data_json(records, out_json)

    print_summary(records)
    print(f"[build_label_set] Wrote {out_csv}")
    print(f"[build_label_set] Wrote {out_json}")
    print("[build_label_set] Edit labels.csv (or open label_tool.html) to "
          "correct the 'label' column, then run train_model.py.")


if __name__ == "__main__":
    main()
