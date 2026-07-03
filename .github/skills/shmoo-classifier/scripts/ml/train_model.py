#!/usr/bin/env python3
"""
Train an interpretable shmoo classifier from a labeled ``labels.csv``.

Pipeline: StandardScaler -> RandomForestClassifier (class_weight="balanced").
Evaluation: StratifiedKFold cross-validation with per-class precision / recall /
F1, a confusion matrix, and feature importances. The trained model is then
refit on all data and saved alongside a metadata sidecar so inference
(``shmoo_classifier.py --model``) can validate the feature order.

Inputs:
  labels.csv  Produced/edited via build_label_set.py + label_tool.html. Must
              contain a ``label`` column plus the FEATURE_NAMES columns.

Outputs (next to --out-dir, default = labels.csv folder):
  model.joblib      Serialized sklearn Pipeline.
  model_meta.json   feature_names, class list, CV metrics, training info.
  report.txt        Human-readable evaluation report.

Usage:
  python train_model.py labels.csv
  python train_model.py labels.csv -o models/ --folds 5 --trees 300 --min-per-class 5
"""

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import joblib

# Shared feature definition (single source of truth for column order).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.feature_extraction import FEATURE_NAMES  # noqa: E402


def load_labels(csv_path):
    """
    Read labels.csv -> (X, y1, y2, keys).

    ``y1`` holds the primary label, ``y2`` the optional secondary label
    (empty string when absent). Rows with a blank primary ``label`` are skipped.
    A missing ``label2`` column is treated as all-empty (single-label data).
    """
    X, y1, y2, keys = [], [], [], []
    missing_cols = None
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
        missing = [c for c in (["label"] + list(FEATURE_NAMES)) if c not in cols]
        if missing:
            missing_cols = missing
        for row in reader:
            label = (row.get("label") or "").strip()
            if not label:
                continue
            label2 = (row.get("label2") or "").strip()
            if label2 == label:
                label2 = ""  # ignore a redundant duplicate secondary
            try:
                vec = [float(row[name]) for name in FEATURE_NAMES]
            except (KeyError, ValueError):
                continue
            X.append(vec)
            y1.append(label)
            y2.append(label2)
            keys.append(row.get("key", ""))
    if missing_cols:
        raise ValueError(
            f"labels.csv is missing required columns: {missing_cols}"
        )
    return np.array(X, dtype=float), np.array(y1), np.array(y2), keys


def drop_rare_classes(X, y, keys, min_per_class):
    """Remove classes with fewer than ``min_per_class`` samples (CV needs them)."""
    counts = Counter(y)
    keep_mask = np.array([counts[label] >= min_per_class for label in y])
    dropped = sorted({lab for lab in y if counts[lab] < min_per_class})
    return X[keep_mask], y[keep_mask], [k for k, m in zip(keys, keep_mask) if m], dropped


def build_pipeline(trees, seed):
    return Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=trees,
            class_weight="balanced",
            random_state=seed,
            n_jobs=-1,
        )),
    ])


def cross_validate(pipe, X, y, folds, seed):
    """Run stratified CV, return (y_pred, n_folds_used)."""
    min_count = min(Counter(y).values())
    n_splits = max(2, min(folds, min_count))
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    y_pred = cross_val_predict(pipe, X, y, cv=skf, n_jobs=-1)
    return y_pred, n_splits


def format_confusion(y_true, y_pred, labels):
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    width = max((len(l) for l in labels), default=4)
    width = min(width, 18)
    header = " " * (width + 2) + "  ".join(f"{l[:6]:>6s}" for l in labels)
    lines = [header]
    for i, lab in enumerate(labels):
        cells = "  ".join(f"{cm[i, j]:>6d}" for j in range(len(labels)))
        lines.append(f"{lab[:width]:<{width}s}  {cells}")
    return "\n".join(lines), cm


# ---------------------------------------------------------------------------
# Multi-label (two-category) helpers
# ---------------------------------------------------------------------------
def build_indicator(y1, y2, classes):
    """Build an (n_samples x n_classes) 0/1 indicator matrix from y1 + y2."""
    index = {c: i for i, c in enumerate(classes)}
    Y = np.zeros((len(y1), len(classes)), dtype=int)
    for r in range(len(y1)):
        Y[r, index[y1[r]]] = 1
        sec = y2[r]
        if sec and sec in index:
            Y[r, index[sec]] = 1
    return Y


def drop_rare_multilabel(X, Y, keys, classes, min_per_class):
    """
    Drop label columns whose positive support < ``min_per_class``, then drop any
    sample row left with no positive label. Returns filtered (X, Y, keys,
    classes, dropped).
    """
    support = Y.sum(axis=0)
    keep_cols = support >= min_per_class
    dropped = [c for c, k in zip(classes, keep_cols) if not k]
    Y = Y[:, keep_cols]
    classes = [c for c, k in zip(classes, keep_cols) if k]
    # Drop rows with no remaining positive label.
    row_keep = Y.sum(axis=1) > 0
    X = X[row_keep]
    Y = Y[row_keep]
    keys = [k for k, m in zip(keys, row_keep) if m]
    return X, Y, keys, classes, dropped


def train_multilabel(X, Y, keys, classes, args, csv_path, out_dir):
    """Train + evaluate a multi-label RandomForest and save artifacts."""
    n_samples = X.shape[0]
    print(f"[train_model] Multi-label mode: {n_samples} samples, "
          f"{len(classes)} classes.")
    support = Y.sum(axis=0)
    for c, s in sorted(zip(classes, support), key=lambda p: -p[1]):
        print(f"    {c:<22s} {int(s):>4d}")

    pipe = build_pipeline(args.trees, args.seed)

    # CV: KFold (StratifiedKFold does not support multi-label targets).
    n_splits = max(2, min(args.folds, n_samples))
    print("[train_model] Running cross-validation (KFold)...")
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=args.seed)
    Y_pred = cross_val_predict(pipe, X, Y, cv=kf, n_jobs=-1)

    report_txt = classification_report(
        Y, Y_pred, target_names=classes, zero_division=0
    )
    report_dict = classification_report(
        Y, Y_pred, target_names=classes, zero_division=0, output_dict=True
    )
    subset_acc = float((Y_pred == Y).all(axis=1).mean())

    print("[train_model] Refitting final model on all labeled data...")
    pipe.fit(X, Y)
    importances = pipe.named_steps["rf"].feature_importances_
    imp_pairs = sorted(zip(FEATURE_NAMES, importances), key=lambda p: -p[1])

    model_path = out_dir / "model.joblib"
    meta_path = out_dir / "model_meta.json"
    report_path = out_dir / "report.txt"
    joblib.dump(pipe, model_path)

    meta = {
        "trained_utc": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(csv_path),
        "feature_names": list(FEATURE_NAMES),
        "multilabel": True,
        "label_classes": list(classes),
        "classes": list(classes),
        "n_samples": int(n_samples),
        "n_features": int(X.shape[1]),
        "cv_folds": int(n_splits),
        "subset_accuracy": subset_acc,
        "per_class": {
            c: {
                "precision": report_dict[c]["precision"],
                "recall": report_dict[c]["recall"],
                "f1": report_dict[c]["f1-score"],
                "support": report_dict[c]["support"],
            }
            for c in classes
        },
        "macro_f1": report_dict["macro avg"]["f1-score"],
        "weighted_f1": report_dict["weighted avg"]["f1-score"],
        "feature_importances": {name: float(imp) for name, imp in imp_pairs},
        "model": "StandardScaler + RandomForestClassifier(multilabel, class_weight=balanced)",
        "n_estimators": int(args.trees),
        "seed": int(args.seed),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    lines = []
    lines.append("=" * 64)
    lines.append("  Shmoo ML Classifier — Training Report (MULTI-LABEL)")
    lines.append("=" * 64)
    lines.append(f"  Source           : {csv_path}")
    lines.append(f"  Samples          : {n_samples}")
    lines.append(f"  Classes          : {len(classes)}")
    lines.append(f"  CV folds         : {n_splits}")
    lines.append(f"  Subset accuracy  : {subset_acc:.3f}  (exact 2-label match)")
    lines.append(f"  Macro F1         : {meta['macro_f1']:.3f}")
    lines.append(f"  Weighted F1      : {meta['weighted_f1']:.3f}")
    lines.append("")
    lines.append("  Per-class metrics (cross-validated, one-vs-rest):")
    lines.append("-" * 64)
    lines.append(report_txt)
    lines.append("  Top feature importances:")
    lines.append("-" * 64)
    for name, imp in imp_pairs[:15]:
        bar = "#" * int(round(imp * 60))
        lines.append(f"  {name:<24s} {imp:6.3f}  {bar}")
    lines.append("=" * 64)
    report_str = "\n".join(lines)
    report_path.write_text(report_str, encoding="utf-8")

    print("\n" + report_str + "\n")
    print(f"[train_model] Saved model     -> {model_path}")
    print(f"[train_model] Saved metadata  -> {meta_path}")
    print(f"[train_model] Saved report    -> {report_path}")


def main():
    ap = argparse.ArgumentParser(description="Train shmoo ML classifier from labels.csv")
    ap.add_argument("labels_csv", help="Path to labels.csv")
    ap.add_argument("-o", "--out-dir", default=None,
                    help="Output dir for model files (default: labels.csv folder).")
    ap.add_argument("--folds", type=int, default=5, help="Max CV folds.")
    ap.add_argument("--trees", type=int, default=300, help="RandomForest n_estimators.")
    ap.add_argument("--min-per-class", type=int, default=3,
                    help="Drop classes with fewer than this many labeled samples.")
    ap.add_argument("--seed", type=int, default=42, help="Random seed.")
    args = ap.parse_args()

    csv_path = Path(args.labels_csv)
    if not csv_path.is_file():
        print(f"[train_model] ERROR: labels file not found: {csv_path}")
        sys.exit(1)
    out_dir = Path(args.out_dir) if args.out_dir else csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[train_model] Loading labels from {csv_path}")
    X, y1, y2, keys = load_labels(csv_path)
    if len(y1) == 0:
        print("[train_model] ERROR: no labeled rows found in labels.csv.")
        sys.exit(1)
    n_secondary = int(np.count_nonzero([bool(s) for s in y2]))
    print(f"[train_model] Loaded {len(y1)} labeled samples, {X.shape[1]} features, "
          f"{n_secondary} with a second category.")

    # ---- Multi-label path (two categories per shmoo) ----
    if n_secondary > 0:
        classes = sorted(set(y1) | {s for s in y2 if s})
        Y = build_indicator(y1, y2, classes)
        X, Y, keys, classes, dropped = drop_rare_multilabel(
            X, Y, keys, classes, args.min_per_class
        )
        if dropped:
            print(f"[train_model] Dropped rare classes (< {args.min_per_class}): {dropped}")
        if len(classes) < 2:
            print(f"[train_model] ERROR: need >=2 classes after filtering, got {classes}.")
            sys.exit(1)
        train_multilabel(X, Y, keys, classes, args, csv_path, out_dir)
        return

    # ---- Single-label path (unchanged) ----
    y = y1
    X, y, keys, dropped = drop_rare_classes(X, y, keys, args.min_per_class)
    if dropped:
        print(f"[train_model] Dropped rare classes (< {args.min_per_class} samples): {dropped}")
    classes = sorted(set(y))
    if len(classes) < 2:
        print(f"[train_model] ERROR: need >=2 classes after filtering, got {classes}.")
        sys.exit(1)
    print(f"[train_model] Training on {len(y)} samples across {len(classes)} classes:")
    for lab, n in sorted(Counter(y).items(), key=lambda x: -x[1]):
        print(f"    {lab:<22s} {n:>4d}")

    pipe = build_pipeline(args.trees, args.seed)

    # ---- Cross-validated evaluation ----
    print("[train_model] Running stratified cross-validation...")
    y_pred, n_splits = cross_validate(pipe, X, y, args.folds, args.seed)
    accuracy = float((y_pred == y).mean())
    report_txt = classification_report(y, y_pred, labels=classes, zero_division=0)
    report_dict = classification_report(
        y, y_pred, labels=classes, zero_division=0, output_dict=True
    )
    cm_str, cm = format_confusion(y, y_pred, classes)

    # ---- Refit on all data + feature importances ----
    print("[train_model] Refitting final model on all labeled data...")
    pipe.fit(X, y)
    importances = pipe.named_steps["rf"].feature_importances_
    imp_pairs = sorted(zip(FEATURE_NAMES, importances), key=lambda p: -p[1])

    # ---- Save artifacts ----
    model_path = out_dir / "model.joblib"
    meta_path = out_dir / "model_meta.json"
    report_path = out_dir / "report.txt"

    joblib.dump(pipe, model_path)

    meta = {
        "trained_utc": datetime.now(timezone.utc).isoformat(),
        "source_csv": str(csv_path),
        "feature_names": list(FEATURE_NAMES),
        "classes": classes,
        "n_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "cv_folds": int(n_splits),
        "cv_accuracy": accuracy,
        "per_class": {
            lab: {
                "precision": report_dict[lab]["precision"],
                "recall": report_dict[lab]["recall"],
                "f1": report_dict[lab]["f1-score"],
                "support": report_dict[lab]["support"],
            }
            for lab in classes
        },
        "macro_f1": report_dict["macro avg"]["f1-score"],
        "weighted_f1": report_dict["weighted avg"]["f1-score"],
        "feature_importances": {name: float(imp) for name, imp in imp_pairs},
        "dropped_rare_classes": dropped,
        "model": "StandardScaler + RandomForestClassifier(class_weight=balanced)",
        "n_estimators": int(args.trees),
        "seed": int(args.seed),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # ---- Human-readable report ----
    lines = []
    lines.append("=" * 64)
    lines.append("  Shmoo ML Classifier — Training Report")
    lines.append("=" * 64)
    lines.append(f"  Source           : {csv_path}")
    lines.append(f"  Samples          : {len(y)}")
    lines.append(f"  Classes          : {len(classes)}")
    lines.append(f"  CV folds         : {n_splits}")
    lines.append(f"  CV accuracy      : {accuracy:.3f}")
    lines.append(f"  Macro F1         : {meta['macro_f1']:.3f}")
    lines.append(f"  Weighted F1      : {meta['weighted_f1']:.3f}")
    if dropped:
        lines.append(f"  Dropped classes  : {', '.join(dropped)}")
    lines.append("")
    lines.append("  Per-class metrics (cross-validated):")
    lines.append("-" * 64)
    lines.append(report_txt)
    lines.append("  Confusion matrix (rows = true, cols = predicted):")
    lines.append("-" * 64)
    lines.append(cm_str)
    lines.append("")
    lines.append("  Top feature importances:")
    lines.append("-" * 64)
    for name, imp in imp_pairs[:15]:
        bar = "#" * int(round(imp * 60))
        lines.append(f"  {name:<24s} {imp:6.3f}  {bar}")
    lines.append("=" * 64)
    report_str = "\n".join(lines)
    report_path.write_text(report_str, encoding="utf-8")

    print("\n" + report_str + "\n")
    print(f"[train_model] Saved model     -> {model_path}")
    print(f"[train_model] Saved metadata  -> {meta_path}")
    print(f"[train_model] Saved report    -> {report_path}")


if __name__ == "__main__":
    main()
