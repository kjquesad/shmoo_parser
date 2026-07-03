#!/usr/bin/env python3
"""
Convert the generated shmoo example database (shmoo_examples.json) into a
labels.csv usable by the ML trainer (skills/shmoo-classifier/scripts/ml/
train_model.py).

Each example's ``class_id`` becomes the ground-truth ``label``; features are
computed with the shared feature module so columns match training/serving.

Usage:
  python examples_to_labels.py shmoo_examples.json -o labels.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ML_DIR = (HERE.parent / ".github" / "skills" / "shmoo-classifier"
          / "scripts" / "ml")
sys.path.insert(0, str(ML_DIR.parent))
from ml.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    rows_to_matrix,
    compute_features,
    features_to_vector,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default=str(HERE / "shmoo_examples.json"))
    ap.add_argument("-o", "--output", default=str(HERE / "labels.csv"))
    ap.add_argument("--data-json", default=None,
                    help="Path for labels_data.json (label_tool.html payload). "
                         "Defaults to labels_data.json next to --output.")
    args = ap.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    examples = data.get("examples", [])

    out_csv = Path(args.output)
    out_data = (Path(args.data_json) if args.data_json
                else out_csv.with_name("labels_data.json"))

    meta_cols = ["key", "label", "label2", "suggested_label",
                 "num_rows", "num_cols"]
    header = meta_cols + list(FEATURE_NAMES)

    written = 0
    skipped = 0
    data_shmoos = []
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i, ex in enumerate(examples):
            rows = ex["grid"].split("_")
            matrix = rows_to_matrix(rows)
            features = compute_features(matrix)
            if not features:
                skipped += 1
                continue
            cls = ex["class_id"]
            key = f"{cls}|{ex['rows']}x{ex['cols']}|{i}"
            vec = features_to_vector(features)
            row = [key, cls, "", cls, ex["rows"], ex["cols"]]
            row.extend(f"{v:.6g}" for v in vec)
            writer.writerow(row)
            written += 1

            data_shmoos.append({
                "key": key,
                "suggested_label": cls,
                "visual_id": "",
                "instance": "",
                "plist": ex.get("family", ""),
                "die_id": "",
                "vmin_found": "",
                "num_rows": ex["rows"],
                "num_cols": ex["cols"],
                "xlabel": "",
                "ylabel": "",
                "rows": rows,
                "features": features,
            })

    payload = {"feature_names": list(FEATURE_NAMES), "shmoos": data_shmoos}
    out_data.write_text(json.dumps(payload, separators=(",", ":")),
                        encoding="utf-8")

    print(f"[examples_to_labels] wrote {written} rows to {out_csv} "
          f"({skipped} skipped)")
    print(f"[examples_to_labels] wrote {len(data_shmoos)} shmoos to {out_data}")


if __name__ == "__main__":
    main()
