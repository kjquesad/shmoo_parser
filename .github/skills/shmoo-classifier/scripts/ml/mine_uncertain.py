#!/usr/bin/env python3
"""
Mine the most informative shmoos for the next labeling round (active learning).

Given parsed shmoo data and a trained model, this scores every shmoo with both
the rule-based classifier and the ML model, then surfaces the cases where the
model is least certain or the two methods disagree. Labeling these high-value
samples and retraining improves the model fastest.

A shmoo is flagged when ANY of:
  * ML top-class confidence < ``--min-confidence`` (uncertain), or
  * rule category != ML category (disagreement).

Outputs (into --out-dir):
  labels.csv        Same schema as build_label_set.py, restricted to the
                    flagged shmoos and sorted most-informative first. The
                    ``suggested_label`` column holds the ML prediction; correct
                    the ``label`` column, then feed back into train_model.py.
  labels_data.json  Companion payload for label_tool.html.

Usage:
  python mine_uncertain.py shmoo_parsed.json --model models/model.joblib -o round2/
  python mine_uncertain.py runs/ --model m/model.joblib -o round2/ --min-confidence 0.6 --top 200
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

# Shared feature module + classifier helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from ml.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    rows_to_matrix,
    compute_features,
    features_to_vector,
)
from shmoo_classifier import (  # noqa: E402
    classify_shmoo,
    load_model,
    predict_with_model,
)


def _resolve_input_files(inputs):
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.rglob("shmoo_parsed.json")))
        elif p.is_file():
            files.append(p)
        else:
            print(f"[mine_uncertain] WARNING: not found, skipping: {item}")
    seen, unique = set(), []
    for f in files:
        rp = f.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(f)
    return unique


def _iter_shmoo_entries(shmoos):
    for _vid, val in shmoos.items():
        if isinstance(val, list):
            yield from val
        elif isinstance(val, dict):
            for entries in val.values():
                if isinstance(entries, list):
                    yield from entries


def _stable_key(entry, dup_counter):
    src = entry.get("source_file", "") or ""
    vid = entry.get("visual_id") or "NO_VID"
    inst = entry.get("instance", "") or ""
    plist = entry.get("plist", "") or ""
    base = f"{Path(src).name}|{vid}|{inst}|{plist}"
    n = dup_counter[base]
    dup_counter[base] += 1
    return f"{base}|{n}"


def score_shmoos(files, model, min_confidence, model_meta=None):
    """Return list of flagged records sorted most-informative first."""
    flagged = []
    dup_counter = defaultdict(int)
    total = 0

    for fpath in files:
        try:
            data = json.loads(Path(fpath).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[mine_uncertain] WARNING: cannot read {fpath}: {exc}")
            continue

        for entry in _iter_shmoo_entries(data.get("shmoos", {})):
            rows = entry.get("failing_data", {}).get("rows", [])
            if not rows:
                continue
            total += 1

            features = compute_features(rows_to_matrix(rows))
            rule_cat, _ = classify_shmoo(features)
            # Raw ML prediction without uncertain-masking, so we know the real
            # top class AND its confidence.
            ml_cat, confidence, _secondary = predict_with_model(
                model, features, 0.0, None, model_meta
            )

            uncertain = confidence < min_confidence
            disagree = rule_cat != ml_cat
            if not (uncertain or disagree):
                continue

            reasons = []
            if uncertain:
                reasons.append("low_confidence")
            if disagree:
                reasons.append("rule_ml_disagree")

            axis = entry.get("axis", {}) or {}
            flagged.append({
                "key": _stable_key(entry, dup_counter),
                "source_file": entry.get("source_file", ""),
                "visual_id": entry.get("visual_id") or "",
                "instance": entry.get("instance", ""),
                "plist": entry.get("plist", ""),
                "die_id": entry.get("die_id", ""),
                "vmin_found": entry.get("vmin_found", ""),
                "num_rows": features.get("num_rows", len(rows)),
                "num_cols": features.get("num_cols", len(rows[0]) if rows else 0),
                "suggested_label": ml_cat,
                "rule_label": rule_cat,
                "ml_confidence": confidence,
                "reason": "+".join(reasons),
                "features": features,
                "_rows": rows,
                "_xlabel": axis.get("xlabel", ""),
                "_ylabel": axis.get("ylabel", ""),
            })

    # Most informative first: disagreements outrank agreements, then by lowest
    # confidence.
    flagged.sort(key=lambda r: (
        0 if "rule_ml_disagree" in r["reason"] else 1,
        r["ml_confidence"],
    ))
    return flagged, total


def write_outputs(records, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "labels.csv"
    out_json = out_dir / "labels_data.json"

    meta_cols = [
        "key", "label", "suggested_label", "rule_label", "ml_confidence", "reason",
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
                r["key"], r["suggested_label"], r["suggested_label"],
                r["rule_label"], f"{r['ml_confidence']:.4f}", r["reason"],
                r["source_file"], r["visual_id"], r["instance"], r["plist"],
                r["die_id"], r["vmin_found"], r["num_rows"], r["num_cols"],
            ]
            row.extend(f"{v:.6g}" for v in vec)
            writer.writerow(row)

    payload = {
        "feature_names": list(FEATURE_NAMES),
        "shmoos": [
            {
                "key": r["key"],
                "suggested_label": r["suggested_label"],
                "rule_label": r["rule_label"],
                "ml_confidence": r["ml_confidence"],
                "reason": r["reason"],
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
    out_json.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return out_csv, out_json


def main():
    ap = argparse.ArgumentParser(
        description="Mine uncertain / disagreeing shmoos for the next labeling round."
    )
    ap.add_argument("inputs", nargs="+",
                    help="shmoo_parsed.json file(s) and/or folder(s).")
    ap.add_argument("--model", required=True, help="Path to trained model.joblib.")
    ap.add_argument("-o", "--out-dir", required=True, help="Output directory.")
    ap.add_argument("--min-confidence", type=float, default=0.6,
                    help="Flag shmoos with ML confidence below this (default: 0.6).")
    ap.add_argument("--top", type=int, default=0,
                    help="Keep only the top-N most informative shmoos (0 = all).")
    args = ap.parse_args()

    model, _meta = load_model(args.model)
    if model is None:
        print("[mine_uncertain] ERROR: could not load model; aborting.")
        sys.exit(1)

    files = _resolve_input_files(args.inputs)
    if not files:
        print("[mine_uncertain] No input shmoo_parsed.json files found.")
        sys.exit(1)
    print(f"[mine_uncertain] Scoring shmoos in {len(files)} file(s)...")

    flagged, total = score_shmoos(files, model, args.min_confidence, _meta)
    if args.top and len(flagged) > args.top:
        flagged = flagged[:args.top]

    if not flagged:
        print(f"[mine_uncertain] No uncertain/disagreeing shmoos found "
              f"(scanned {total}). Model looks confident — nice!")
        sys.exit(0)

    out_csv, out_json = write_outputs(flagged, args.out_dir)

    # Summary.
    n_disagree = sum(1 for r in flagged if "rule_ml_disagree" in r["reason"])
    n_lowconf = sum(1 for r in flagged if "low_confidence" in r["reason"])
    print(f"\n{'='*60}")
    print(f"  Active-Learning Candidates — {len(flagged)} of {total} shmoos")
    print(f"{'='*60}")
    print(f"  rule/ML disagreements : {n_disagree}")
    print(f"  low confidence        : {n_lowconf}")
    print(f"{'='*60}")
    print(f"[mine_uncertain] Wrote {out_csv}")
    print(f"[mine_uncertain] Wrote {out_json}")
    print("[mine_uncertain] Open label_tool.html, load labels_data.json, "
          "correct labels, then append to your training labels.csv and retrain.")


if __name__ == "__main__":
    main()
