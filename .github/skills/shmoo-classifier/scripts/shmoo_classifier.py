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


def rows_to_matrix(rows):
    """Convert rows list to binary matrix: 1=fail, 0=pass."""
    matrix = []
    for row in rows:
        matrix.append([0 if ch == '*' else 1 for ch in row])
    return matrix


def compute_features(matrix):
    """Compute spatial features from a binary fail matrix."""
    if not matrix or not matrix[0]:
        return None

    num_rows = len(matrix)
    num_cols = len(matrix[0])
    total_cells = num_rows * num_cols

    if total_cells == 0:
        return None

    # Total fail ratio
    total_fails = sum(sum(row) for row in matrix)
    total_fail_ratio = total_fails / total_cells

    # Row splits
    mid_row = num_rows // 2
    mid_col = num_cols // 2

    # Top half (high Y = high voltage, later rows in the array correspond to higher Y)
    # In shmoo_parsed.json, rows[0] = lowest Y, rows[-1] = highest Y
    top_cells = sum(len(row) for row in matrix[mid_row:])
    top_fails = sum(sum(row) for row in matrix[mid_row:])
    top_fail_ratio = top_fails / top_cells if top_cells > 0 else 0

    # Bottom half (low Y)
    bot_cells = sum(len(row) for row in matrix[:mid_row])
    bot_fails = sum(sum(row) for row in matrix[:mid_row])
    bot_fail_ratio = bot_fails / bot_cells if bot_cells > 0 else 0

    # Left half (low X = low timing)
    left_fails = sum(sum(row[:mid_col]) for row in matrix)
    left_cells = mid_col * num_rows
    left_fail_ratio = left_fails / left_cells if left_cells > 0 else 0

    # Right half (high X = high timing)
    right_fails = sum(sum(row[mid_col:]) for row in matrix)
    right_cells = (num_cols - mid_col) * num_rows
    right_fail_ratio = right_fails / right_cells if right_cells > 0 else 0

    # Center region (middle 50% of rows and cols)
    r_start = num_rows // 4
    r_end = num_rows - num_rows // 4
    c_start = num_cols // 4
    c_end = num_cols - num_cols // 4
    center_fails = sum(
        sum(matrix[r][c_start:c_end]) for r in range(r_start, r_end)
    )
    center_cells = (r_end - r_start) * (c_end - c_start)
    center_fail_ratio = center_fails / center_cells if center_cells > 0 else 0

    # Edge region (everything NOT in center)
    edge_fails = total_fails - center_fails
    edge_cells = total_cells - center_cells
    edge_fail_ratio = edge_fails / edge_cells if edge_cells > 0 else 0

    # Quadrant fail ratios
    q_tl_fails = sum(sum(matrix[r][:mid_col]) for r in range(mid_row, num_rows))
    q_tr_fails = sum(sum(matrix[r][mid_col:]) for r in range(mid_row, num_rows))
    q_bl_fails = sum(sum(matrix[r][:mid_col]) for r in range(0, mid_row))
    q_br_fails = sum(sum(matrix[r][mid_col:]) for r in range(0, mid_row))

    q_tl_cells = (num_rows - mid_row) * mid_col
    q_tr_cells = (num_rows - mid_row) * (num_cols - mid_col)
    q_bl_cells = mid_row * mid_col
    q_br_cells = mid_row * (num_cols - mid_col)

    q_tl_ratio = q_tl_fails / q_tl_cells if q_tl_cells > 0 else 0
    q_tr_ratio = q_tr_fails / q_tr_cells if q_tr_cells > 0 else 0
    q_bl_ratio = q_bl_fails / q_bl_cells if q_bl_cells > 0 else 0
    q_br_ratio = q_br_fails / q_br_cells if q_br_cells > 0 else 0

    # Per-row fail ratio (for diagonal detection)
    per_row_fail_ratio = []
    for row in matrix:
        row_total = len(row)
        row_fails = sum(row)
        per_row_fail_ratio.append(row_fails / row_total if row_total > 0 else 0)

    # Boundary detection: find first passing column per row (left-to-right)
    # Used to detect diagonal boundaries
    boundary_cols = []
    for row in matrix:
        first_pass = None
        for c, val in enumerate(row):
            if val == 0:
                first_pass = c
                break
        boundary_cols.append(first_pass)  # None if entire row fails

    # Check if boundary is monotonically increasing (diagonal shape)
    is_diagonal = _check_diagonal(boundary_cols, num_cols)

    return {
        "total_fail_ratio": round(total_fail_ratio, 4),
        "top_fail_ratio": round(top_fail_ratio, 4),
        "bot_fail_ratio": round(bot_fail_ratio, 4),
        "left_fail_ratio": round(left_fail_ratio, 4),
        "right_fail_ratio": round(right_fail_ratio, 4),
        "center_fail_ratio": round(center_fail_ratio, 4),
        "edge_fail_ratio": round(edge_fail_ratio, 4),
        "q_tl_ratio": round(q_tl_ratio, 4),
        "q_tr_ratio": round(q_tr_ratio, 4),
        "q_bl_ratio": round(q_bl_ratio, 4),
        "q_br_ratio": round(q_br_ratio, 4),
        "is_diagonal": is_diagonal,
        "num_rows": num_rows,
        "num_cols": num_cols,
    }


def _check_diagonal(boundary_cols, num_cols):
    """
    Check if the pass/fail boundary follows a roughly monotonic diagonal.
    boundary_cols[i] = first passing column in row i (None if all-fail row).
    Rows go from low Y (index 0) to high Y (index -1).
    A classic diagonal: lower rows fail more (boundary further right),
    upper rows pass more (boundary further left).
    """
    valid = [(i, c) for i, c in enumerate(boundary_cols) if c is not None]
    if len(valid) < 4:
        return False

    # Check if boundary columns are roughly monotonically decreasing
    # (as Y increases, the fail region shrinks from the left)
    cols = [c for _, c in valid]

    # Allow some noise: count how many pairs are monotonically decreasing
    monotone_count = 0
    for i in range(len(cols) - 1):
        if cols[i] >= cols[i + 1]:
            monotone_count += 1

    monotone_ratio = monotone_count / (len(cols) - 1)

    # Also check: is there meaningful spread in boundary positions?
    col_range = max(cols) - min(cols)
    spread_ratio = col_range / num_cols if num_cols > 0 else 0

    return monotone_ratio >= 0.65 and spread_ratio >= 0.3


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
    q_tl = features["q_tl_ratio"]
    q_tr = features["q_tr_ratio"]
    q_bl = features["q_bl_ratio"]
    q_br = features["q_br_ratio"]
    is_diag = features["is_diagonal"]

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

    # 4. Ceiling — fails at high Y (top), passes at low Y (bottom)
    if top >= 0.75 and bot <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (top - bot))
        return "ceiling", round(confidence, 3)

    # 5. Floor — fails at low Y (bottom), passes at high Y (top)
    if bot >= 0.75 and top <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (bot - top))
        return "floor", round(confidence, 3)

    # 6. Speed limit — fails at high X (right), passes at low X (left)
    if right >= 0.70 and left <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (right - left))
        return "speed_limit", round(confidence, 3)

    # 7. Slow limit — fails at low X (left), passes at high X (right)
    if left >= 0.70 and right <= 0.35 and tfr > 0.1:
        confidence = min(1.0, (left - right))
        return "slow_limit", round(confidence, 3)

    # 8. Corner — one quadrant dominates
    quadrants = [q_tl, q_tr, q_bl, q_br]
    max_q = max(quadrants)
    others = [q for q in quadrants if q != max_q]
    avg_others = sum(others) / len(others) if others else 0
    if max_q >= 0.70 and avg_others <= 0.30 and tfr > 0.1:
        corner_names = ["top_left", "top_right", "bottom_left", "bottom_right"]
        corner_idx = quadrants.index(max_q)
        confidence = min(1.0, max_q - avg_others)
        return f"corner_{corner_names[corner_idx]}", round(confidence, 3)

    # 9. Crack/Island — fails in center, passes on edges
    if center >= 0.55 and edge <= 0.35 and tfr > 0.05:
        confidence = min(1.0, center - edge)
        return "crack", round(confidence, 3)

    # 10. Island (inverse) — passes in center, fails on edges
    if edge >= 0.55 and center <= 0.35 and tfr > 0.1:
        confidence = min(1.0, edge - center)
        return "island", round(confidence, 3)

    # 11. Mixed/Unknown
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


def classify_parsed_json(data):
    """
    Process the full shmoo_parsed.json structure.
    Returns a list of classification results.
    """
    results = []
    shmoos = data.get("shmoos", {})

    for entry in _iter_shmoo_entries(shmoos):
            rows = entry.get("failing_data", {}).get("rows", [])
            if not rows:
                results.append({
                    "visual_id": entry.get("visual_id"),
                    "instance": entry.get("instance", ""),
                    "plist": entry.get("plist", ""),
                    "classification": {"category": "unknown", "confidence": 0.0, "features": None},
                })
                continue

            matrix = rows_to_matrix(rows)
            features = compute_features(matrix)
            category, confidence = classify_shmoo(features)

            results.append({
                "visual_id": entry.get("visual_id"),
                "instance": entry.get("instance", ""),
                "plist": entry.get("plist", ""),
                "classification": {
                    "category": category,
                    "confidence": confidence,
                    "features": features,
                },
            })

            # Also inject classification into the entry itself
            entry["classification"] = {
                "category": category,
                "confidence": confidence,
                "features": features,
            }

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
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = classify_parsed_json(data)
    print_summary(results)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / "shmoo_classified.json"

    # Save augmented JSON (original structure + classification injected)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Classified JSON saved to: {output_path}")

    # Also save a summary CSV for quick review
    csv_path = output_path.with_suffix(".csv")
    import csv
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["visual_id", "instance", "plist", "category", "confidence",
                         "total_fail_ratio", "top_fail_ratio", "bot_fail_ratio",
                         "left_fail_ratio", "right_fail_ratio", "is_diagonal"])
        for r in results:
            feat = r["classification"]["features"] or {}
            writer.writerow([
                r["visual_id"] or "NO_VID",
                r["instance"],
                r["plist"],
                r["classification"]["category"],
                r["classification"]["confidence"],
                feat.get("total_fail_ratio", ""),
                feat.get("top_fail_ratio", ""),
                feat.get("bot_fail_ratio", ""),
                feat.get("left_fail_ratio", ""),
                feat.get("right_fail_ratio", ""),
                feat.get("is_diagonal", ""),
            ])
    print(f"Summary CSV saved to: {csv_path}")


if __name__ == "__main__":
    main()
