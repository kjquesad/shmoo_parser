#!/usr/bin/env python3
"""
Shmoo Shape Classifier — Rule-Based Spatial Heuristic (Option A)

Reads shmoo_parsed.json and classifies each shmoo into a shape category
based on spatial fail distribution analysis.

Categories:
  - red        : Failing across nearly all points (>=95% fail)
  - clean      : Passing across nearly all points (<=2% fail)
  - ceiling    : Fails concentrated at high Y (top rows = high voltage)
  - floor      : Fails concentrated at low Y (bottom rows = low voltage)
  - speed_limit: Fails concentrated at high X (right columns = high timing)
  - slow_limit : Fails concentrated at low X (left columns = low timing)
  - diagonal   : Pass/fail boundary follows monotonic line (V-T tradeoff)
  - corner     : Fails concentrated in one quadrant
  - crack      : Fails concentrated in center, passes on edges
  - island     : Passes concentrated in center, fails on edges (inverse crack)
  - mixed      : Doesn't match above rules

Usage:
  python shmoo_classifier.py <path_to_shmoo_parsed.json> [--output <path>]

Output:
  shmoo_classified.json — same structure as input with added "classification" field
"""

import json
import sys
import argparse
from pathlib import Path

# Feature extraction is shared with the ML pipeline so training and the
# rule-based classifier always use identical features.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ml.feature_extraction import (  # noqa: E402
    FEATURE_NAMES,
    rows_to_matrix,
    compute_features,
    features_to_vector,
    _check_diagonal,
)


def _progress(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Optional ML model inference
# ---------------------------------------------------------------------------
def load_model(model_path):
    """
    Load a trained model + its metadata sidecar.

    Returns (model, meta) or (None, None) on any failure (so the caller can
    transparently fall back to the rule-based classifier).
    """
    try:
        import joblib  # local import: only needed on the ML path
    except ImportError:
        _progress("[classifier] joblib not installed; using rule-based classifier.")
        return None, None

    mpath = Path(model_path)
    if not mpath.is_file():
        _progress(f"[classifier] Model not found ({mpath}); using rule-based classifier.")
        return None, None

    meta_path = mpath.parent / "model_meta.json"
    meta = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}

    # Validate feature order matches what this code produces.
    trained_features = meta.get("feature_names")
    if trained_features and list(trained_features) != list(FEATURE_NAMES):
        _progress(
            "[classifier] WARNING: model feature order differs from current "
            "FEATURE_NAMES; falling back to rule-based classifier."
        )
        return None, None

    try:
        model = joblib.load(mpath)
    except Exception as exc:  # noqa: BLE001 - any load error -> rule fallback
        _progress(f"[classifier] Failed to load model ({exc}); using rule-based classifier.")
        return None, None

    _progress(f"[classifier] Loaded ML model: {mpath}")
    return model, meta


def predict_with_model(model, features, min_confidence, secondary_confidence=None, meta=None):
    """
    Predict category + confidence for one shmoo's feature dict.

    Returns ``(category, confidence, secondary)`` where ``secondary`` is a list
    of ``(category, confidence)`` tuples for additional labels whose probability
    is at least ``secondary_confidence`` (empty when ``secondary_confidence`` is
    None or no other class qualifies).

    Supports both single-label models (one category per shmoo) and multi-label
    models (trained with two categories); for multi-label, ``meta`` must carry
    ``label_classes`` describing the output column order.

    When the top-class probability is below ``min_confidence`` the primary
    category is reported as ``"uncertain"`` (the raw confidence is still returned
    so it can be surfaced for active learning), and no secondary is emitted.
    """
    import numpy as np  # local import: only needed on the ML path

    vec = np.asarray(features_to_vector(features), dtype=float).reshape(1, -1)

    if meta and meta.get("multilabel"):
        ranked = _multilabel_ranked(model, vec, meta.get("label_classes", []))
    elif hasattr(model, "predict_proba"):
        proba = model.predict_proba(vec)[0]
        classes = list(model.classes_)
        order = list(np.argsort(proba)[::-1])
        ranked = [(classes[i], float(proba[i])) for i in order]
    else:
        ranked = [(str(model.predict(vec)[0]), 1.0)]

    if not ranked:
        return "uncertain", 0.0, []

    category, confidence = ranked[0]

    if confidence < min_confidence:
        return "uncertain", confidence, []

    secondary = []
    if secondary_confidence is not None:
        for cat, conf in ranked[1:]:
            if conf >= secondary_confidence:
                secondary.append((cat, conf))
    return category, confidence, secondary


def _multilabel_ranked(model, vec, label_classes):
    """
    Return [(class, prob_present), ...] sorted descending for a multi-label
    model whose ``predict_proba`` yields one array per label column.
    """
    import numpy as np  # local import: only needed on the ML path

    proba_list = model.predict_proba(vec)  # list of (1, n_classes_i) arrays
    rf = model.named_steps["rf"] if hasattr(model, "named_steps") else model
    per_output_classes = getattr(rf, "classes_", None)
    ranked = []
    for i, cls_name in enumerate(label_classes):
        if i >= len(proba_list):
            break
        arr = np.asarray(proba_list[i])[0]
        classes_i = per_output_classes[i] if per_output_classes is not None else [0, 1]
        p_present = 0.0
        for j, cval in enumerate(classes_i):
            if int(cval) == 1:
                p_present = float(arr[j])
                break
        ranked.append((cls_name, p_present))
    ranked.sort(key=lambda p: -p[1])
    return ranked


def classify_shmoo(features):
    """
    Apply classification rules to features dict.
    Returns (category, confidence) tuple.
    """
    if features is None:
        return "unknown", 0.0

    tfr = features["total_fail_ratio"]
    top = features["top_fail_ratio"]
    bot = features["bot_fail_ratio"]
    left = features["left_fail_ratio"]
    right = features["right_fail_ratio"]
    center = features["center_fail_ratio"]
    edge = features["edge_fail_ratio"]
    left_edge = features["left_edge_fail_ratio"]
    right_edge = features["right_edge_fail_ratio"]
    center_band = features["center_band_fail_ratio"]
    q_tl = features["q_tl_ratio"]
    q_tr = features["q_tr_ratio"]
    q_bl = features["q_bl_ratio"]
    q_br = features["q_br_ratio"]
    is_diag = features["is_diagonal"]
    isolated = features["isolated_fail_ratio"]
    largest_cluster = features["largest_cluster_ratio"]
    avg_transitions = features["avg_row_transitions"]
    max_transitions = features["max_row_transitions"]

    # 1. Red/Dead — nearly all failing
    if tfr >= 0.95:
        return "red", min(1.0, tfr)

    # 2. Clean/Green — nearly all passing
    if tfr <= 0.02:
        return "clean", 1.0 - tfr

    # 3. Diagonal — classic V-T tradeoff boundary
    if is_diag and 0.15 < tfr < 0.85:
        confidence = 0.8
        return "diagonal", confidence

    # 4. Speckled — structured trend with noisy scattered fail pattern
    if (
        0.10 <= tfr <= 0.90
        and (avg_transitions >= 1.15 or max_transitions >= 4)
        and largest_cluster <= 0.95
        and (bot >= 0.45 or top >= 0.45)
    ):
        confidence = min(1.0, (avg_transitions / 2.0 + (1.0 - largest_cluster)) / 2)
        return "speckled", round(confidence, 3)

    # 5. Ceiling — fails at high Y (top), passes at low Y (bottom)
    if top >= 0.75 and bot <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (top - bot))
        return "ceiling", round(confidence, 3)

    # 6. Floor — fails at low Y (bottom), passes at high Y (top)
    if bot >= 0.75 and top <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (bot - top))
        return "floor", round(confidence, 3)

    # 7. Left wall — strong left-edge fail wall across Y
    if left_edge >= 0.90 and right <= 0.20 and tfr > 0.15:
        confidence = min(1.0, left_edge - right)
        return "left wall", round(confidence, 3)

    # 8. Right wall — strong right-edge fail wall across Y
    if right_edge >= 0.90 and left <= 0.20 and tfr > 0.15:
        confidence = min(1.0, right_edge - left)
        return "right wall", round(confidence, 3)

    # 9. Speed limit — fails at high X (right), passes at low X (left)
    if right >= 0.70 and left <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (right - left))
        return "speed_limit", round(confidence, 3)

    # 10. Slow limit — fails at low X (left), passes at high X (right)
    if left >= 0.70 and right <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (left - right))
        return "slow_limit", round(confidence, 3)

    # 11. Corner — one quadrant dominates
    quadrants = [q_tl, q_tr, q_bl, q_br]
    max_q = max(quadrants)
    others = [q for q in quadrants if q != max_q]
    avg_others = sum(others) / len(others) if others else 0
    if max_q >= 0.70 and avg_others <= 0.30 and tfr > 0.1:
        corner_names = ["top_left", "top_right", "bottom_left", "bottom_right"]
        corner_idx = quadrants.index(max_q)
        confidence = min(1.0, max_q - avg_others)
        return f"corner_{corner_names[corner_idx]}", round(confidence, 3)

    # 12. Crack/Island — fails in center, passes on edges
    if center >= 0.55 and edge <= 0.35 and tfr > 0.05:
        confidence = min(1.0, center - edge)
        return "crack", round(confidence, 3)

    # 13. Island (inverse) — passes in center, fails on edges
    if edge >= 0.55 and center <= 0.35 and tfr > 0.1:
        confidence = min(1.0, edge - center)
        return "island", round(confidence, 3)

    # 14. Mixed/Unknown
    return "mixed", round(0.5, 3)


def _iter_shmoo_entries(shmoos):
    """
    Iterate over shmoo entries regardless of nesting format.
    Handles both:
      - flat:   { vid_key: [entry, ...] }
      - nested: { vid_key: { source_file: [entry, ...] } }
    """
    for vid_key, val in shmoos.items():
        if isinstance(val, list):
            # Flat format: vid_key -> [entries]
            for entry in val:
                yield entry
        elif isinstance(val, dict):
            # Nested format: vid_key -> { source_file: [entries] }
            for source_file, entries in val.items():
                if isinstance(entries, list):
                    for entry in entries:
                        yield entry


def classify_parsed_json(data, model=None, min_confidence=0.0, secondary_confidence=None, model_meta=None):
    """
    Process the full shmoo_parsed.json structure.

    If ``model`` is provided, each shmoo is classified by the ML model and the
    result is tagged with ``method="ml"``; predictions below ``min_confidence``
    are reported as ``"uncertain"``. When ``secondary_confidence`` is given, a
    second category is added whenever its probability is at least that value
    (useful for shmoos that show two patterns, e.g. floor + speckled). Without a
    model, the rule-based classifier is used and tagged ``method="rule"``.

    Returns a list of classification results.
    """
    results = []
    shmoos = data.get("shmoos", {})
    method = "ml" if model is not None else "rule"

    processed = 0
    total_hint = int(data.get("total_shmoos") or 0)
    if total_hint:
        _progress(f"[classifier] Starting classification for about {total_hint} shmoo(s)")
    else:
        _progress("[classifier] Starting classification")

    for entry in _iter_shmoo_entries(shmoos):
            processed += 1
            rows = entry.get("failing_data", {}).get("rows", [])
            if not rows:
                results.append({
                    "visual_id": entry.get("visual_id"),
                    "instance": entry.get("instance", ""),
                    "plist": entry.get("plist", ""),
                    "classification": {"category": "unknown", "confidence": 0.0,
                                       "features": None, "method": method},
                })
                continue

            matrix = rows_to_matrix(rows)
            features = compute_features(matrix)
            secondary = []
            if model is not None:
                category, confidence, secondary = predict_with_model(
                    model, features, min_confidence, secondary_confidence, model_meta
                )
            else:
                category, confidence = classify_shmoo(features)

            classification = {
                "category": category,
                "confidence": confidence,
                "features": features,
                "method": method,
            }
            # Ordered list of all assigned categories (primary first), plus a
            # convenience secondary_* pair for the top extra label.
            categories = [{"category": category, "confidence": confidence}]
            for sec_cat, sec_conf in secondary:
                categories.append({"category": sec_cat, "confidence": sec_conf})
            if len(categories) > 1:
                classification["categories"] = categories
                classification["secondary_category"] = categories[1]["category"]
                classification["secondary_confidence"] = categories[1]["confidence"]

            results.append({
                "visual_id": entry.get("visual_id"),
                "instance": entry.get("instance", ""),
                "plist": entry.get("plist", ""),
                "classification": dict(classification),
            })

            # Also inject classification into the entry itself
            entry["classification"] = classification

            if processed % 200 == 0:
                if total_hint:
                    _progress(f"[heartbeat] classifier processed {processed}/{total_hint}")
                else:
                    _progress(f"[heartbeat] classifier processed {processed}")

    _progress(f"[classifier] Completed classification for {processed} shmoo(s)")
    return results


def print_summary(results):
    """Print classification summary to stdout."""
    from collections import Counter
    counts = Counter(r["classification"]["category"] for r in results)
    total = len(results)

    print(f"\n{'='*60}")
    print(f"  Shmoo Classification Summary — {total} shmoos")
    print(f"{'='*60}")
    for cat, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f"  {cat:<20s} : {count:>4d}  ({pct:5.1f}%)")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Classify shmoo shapes from shmoo_parsed.json")
    parser.add_argument("input", help="Path to shmoo_parsed.json")
    parser.add_argument("--output", "-o", help="Output path for classified JSON (default: shmoo_classified.json next to input)")
    parser.add_argument("--model", help="Path to a trained model.joblib. When given, uses ML classification with rule-based fallback on load failure.")
    parser.add_argument("--min-confidence", type=float, default=0.0,
                        help="ML only: predictions below this probability are tagged 'uncertain' (default: 0.0).")
    parser.add_argument("--secondary-confidence", type=float, default=None,
                        help="ML only: also assign a second category when its probability is at least this value (e.g. 0.2). Off by default.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    _progress(f"[classifier] Loaded input JSON: {input_path}")

    model = None
    model_meta = None
    if args.model:
        model, model_meta = load_model(args.model)

    results = classify_parsed_json(data, model=model, min_confidence=args.min_confidence,
                                   secondary_confidence=args.secondary_confidence,
                                   model_meta=model_meta)
    print_summary(results)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / "shmoo_classified.json"

    # Save augmented JSON (original structure + classification injected)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    _progress(f"Classified JSON saved to: {output_path}")


if __name__ == "__main__":
    main()
