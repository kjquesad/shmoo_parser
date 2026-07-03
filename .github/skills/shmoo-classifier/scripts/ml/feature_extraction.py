#!/usr/bin/env python3
"""
Shared shmoo feature extraction.

Single source of truth for converting a shmoo's pass/fail grid (``rows``) into a
numeric feature vector. Both the rule-based classifier (`shmoo_classifier.py`)
and the ML pipeline (`train_model.py`, model inference) import from here so the
features stay identical across training and serving.

Pure Python / stdlib only — safe to import without numpy.
"""

from typing import Dict, List, Optional, Any

# Stable, ordered list of scalar feature names used for ML. The order here
# defines the column order of any feature vector produced by
# ``features_to_vector``. Boolean/derived features are coerced to floats.
FEATURE_NAMES: List[str] = [
    "total_fail_ratio",
    "top_fail_ratio",
    "bot_fail_ratio",
    "left_fail_ratio",
    "right_fail_ratio",
    "center_fail_ratio",
    "edge_fail_ratio",
    "left_edge_fail_ratio",
    "right_edge_fail_ratio",
    "center_band_fail_ratio",
    "q_tl_ratio",
    "q_tr_ratio",
    "q_bl_ratio",
    "q_br_ratio",
    "is_diagonal",
    "isolated_fail_ratio",
    "largest_cluster_ratio",
    "avg_row_transitions",
    "max_row_transitions",
    "num_rows",
    "num_cols",
    # Extended features (added for ML; rule classifier ignores them).
    "vertical_symmetry",
    "horizontal_symmetry",
    "vertical_gradient",
    "horizontal_gradient",
    "boundary_monotonicity",
    "boundary_spread",
    "aspect_ratio",
    "fail_row_fraction",
    "fail_col_fraction",
]


def rows_to_matrix(rows: List[str]) -> List[List[int]]:
    """Convert rows list to binary matrix: 1=fail, 0=pass."""
    matrix = []
    for row in rows:
        matrix.append([0 if ch == "*" else 1 for ch in row])
    return matrix


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

    cols = [c for _, c in valid]

    monotone_count = 0
    for i in range(len(cols) - 1):
        if cols[i] >= cols[i + 1]:
            monotone_count += 1

    monotone_ratio = monotone_count / (len(cols) - 1)

    col_range = max(cols) - min(cols)
    spread_ratio = col_range / num_cols if num_cols > 0 else 0

    return monotone_ratio >= 0.65 and spread_ratio >= 0.3


def _boundary_stats(boundary_cols, num_cols):
    """Return (monotonicity_ratio, spread_ratio) for the pass boundary."""
    valid = [c for c in boundary_cols if c is not None]
    if len(valid) < 2 or num_cols <= 0:
        return 0.0, 0.0
    monotone_count = 0
    for i in range(len(valid) - 1):
        if valid[i] >= valid[i + 1]:
            monotone_count += 1
    monotone_ratio = monotone_count / (len(valid) - 1)
    spread_ratio = (max(valid) - min(valid)) / num_cols
    return monotone_ratio, spread_ratio


def compute_features(matrix: List[List[int]]) -> Optional[Dict[str, Any]]:
    """Compute spatial features from a binary fail matrix (1=fail, 0=pass)."""
    if not matrix or not matrix[0]:
        return None

    num_rows = len(matrix)
    num_cols = len(matrix[0])
    total_cells = num_rows * num_cols

    if total_cells == 0:
        return None

    total_fails = sum(sum(row) for row in matrix)
    total_fail_ratio = total_fails / total_cells

    mid_row = num_rows // 2
    mid_col = num_cols // 2

    # Top half (high Y); rows[-1] is highest Y.
    top_cells = sum(len(row) for row in matrix[mid_row:])
    top_fails = sum(sum(row) for row in matrix[mid_row:])
    top_fail_ratio = top_fails / top_cells if top_cells > 0 else 0

    bot_cells = sum(len(row) for row in matrix[:mid_row])
    bot_fails = sum(sum(row) for row in matrix[:mid_row])
    bot_fail_ratio = bot_fails / bot_cells if bot_cells > 0 else 0

    left_fails = sum(sum(row[:mid_col]) for row in matrix)
    left_cells = mid_col * num_rows
    left_fail_ratio = left_fails / left_cells if left_cells > 0 else 0

    right_fails = sum(sum(row[mid_col:]) for row in matrix)
    right_cells = (num_cols - mid_col) * num_rows
    right_fail_ratio = right_fails / right_cells if right_cells > 0 else 0

    r_start = num_rows // 4
    r_end = num_rows - num_rows // 4
    c_start = num_cols // 4
    c_end = num_cols - num_cols // 4
    center_fails = sum(
        sum(matrix[r][c_start:c_end]) for r in range(r_start, r_end)
    )
    center_cells = (r_end - r_start) * (c_end - c_start)
    center_fail_ratio = center_fails / center_cells if center_cells > 0 else 0

    edge_fails = total_fails - center_fails
    edge_cells = total_cells - center_cells
    edge_fail_ratio = edge_fails / edge_cells if edge_cells > 0 else 0

    third_col = max(1, num_cols // 3)
    left_end = third_col
    right_start = num_cols - third_col

    left_edge_fails = sum(sum(row[:left_end]) for row in matrix)
    left_edge_cells = left_end * num_rows
    left_edge_fail_ratio = left_edge_fails / left_edge_cells if left_edge_cells > 0 else 0

    right_edge_fails = sum(sum(row[right_start:]) for row in matrix)
    right_edge_cells = (num_cols - right_start) * num_rows
    right_edge_fail_ratio = right_edge_fails / right_edge_cells if right_edge_cells > 0 else 0

    center_band_fails = sum(sum(row[left_end:right_start]) for row in matrix)
    center_band_cells = max(0, (right_start - left_end) * num_rows)
    center_band_fail_ratio = (
        center_band_fails / center_band_cells if center_band_cells > 0 else 0
    )

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

    # Per-row fail ratio + transitions (diagonal / speckled detection)
    per_row_fail_ratio = []
    row_transitions = []
    for row in matrix:
        row_total = len(row)
        row_fails = sum(row)
        per_row_fail_ratio.append(row_fails / row_total if row_total > 0 else 0)
        transitions = 0
        for i in range(len(row) - 1):
            if row[i] != row[i + 1]:
                transitions += 1
        row_transitions.append(transitions)

    # Boundary: first passing column per row.
    boundary_cols = []
    for row in matrix:
        first_pass = None
        for c, val in enumerate(row):
            if val == 0:
                first_pass = c
                break
        boundary_cols.append(first_pass)

    is_diagonal = _check_diagonal(boundary_cols, num_cols)
    boundary_monotonicity, boundary_spread = _boundary_stats(boundary_cols, num_cols)

    # Speckled helpers: isolated fail ratio and largest fail cluster ratio
    isolated_fails = 0
    for r in range(num_rows):
        for c in range(num_cols):
            if matrix[r][c] != 1:
                continue
            neighbor_fails = 0
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    rr = r + dr
                    cc = c + dc
                    if 0 <= rr < num_rows and 0 <= cc < num_cols and matrix[rr][cc] == 1:
                        neighbor_fails += 1
            if neighbor_fails <= 1:
                isolated_fails += 1

    isolated_fail_ratio = isolated_fails / total_fails if total_fails > 0 else 0

    visited = [[False for _ in range(num_cols)] for _ in range(num_rows)]
    largest_cluster = 0

    for r in range(num_rows):
        for c in range(num_cols):
            if matrix[r][c] != 1 or visited[r][c]:
                continue
            stack = [(r, c)]
            visited[r][c] = True
            cluster_size = 0
            while stack:
                cr, cc = stack.pop()
                cluster_size += 1
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr = cr + dr
                        nc = cc + dc
                        if (
                            0 <= nr < num_rows
                            and 0 <= nc < num_cols
                            and not visited[nr][nc]
                            and matrix[nr][nc] == 1
                        ):
                            visited[nr][nc] = True
                            stack.append((nr, nc))
            if cluster_size > largest_cluster:
                largest_cluster = cluster_size

    largest_cluster_ratio = largest_cluster / total_fails if total_fails > 0 else 0
    avg_row_transitions = (
        sum(row_transitions) / len(row_transitions) if row_transitions else 0
    )
    max_row_transitions = max(row_transitions) if row_transitions else 0

    # Extended ML features.
    vertical_symmetry = _vertical_symmetry(matrix, num_rows, num_cols, total_cells)
    horizontal_symmetry = _horizontal_symmetry(matrix, num_rows, num_cols, total_cells)
    vertical_gradient = top_fail_ratio - bot_fail_ratio
    horizontal_gradient = right_fail_ratio - left_fail_ratio

    fail_rows = sum(1 for ratio in per_row_fail_ratio if ratio > 0)
    fail_row_fraction = fail_rows / num_rows if num_rows > 0 else 0
    col_has_fail = [0] * num_cols
    for row in matrix:
        for c, val in enumerate(row):
            if val == 1:
                col_has_fail[c] = 1
    fail_col_fraction = sum(col_has_fail) / num_cols if num_cols > 0 else 0
    aspect_ratio = num_cols / num_rows if num_rows > 0 else 0

    return {
        "total_fail_ratio": round(total_fail_ratio, 4),
        "top_fail_ratio": round(top_fail_ratio, 4),
        "bot_fail_ratio": round(bot_fail_ratio, 4),
        "left_fail_ratio": round(left_fail_ratio, 4),
        "right_fail_ratio": round(right_fail_ratio, 4),
        "center_fail_ratio": round(center_fail_ratio, 4),
        "edge_fail_ratio": round(edge_fail_ratio, 4),
        "left_edge_fail_ratio": round(left_edge_fail_ratio, 4),
        "right_edge_fail_ratio": round(right_edge_fail_ratio, 4),
        "center_band_fail_ratio": round(center_band_fail_ratio, 4),
        "q_tl_ratio": round(q_tl_ratio, 4),
        "q_tr_ratio": round(q_tr_ratio, 4),
        "q_bl_ratio": round(q_bl_ratio, 4),
        "q_br_ratio": round(q_br_ratio, 4),
        "is_diagonal": is_diagonal,
        "isolated_fail_ratio": round(isolated_fail_ratio, 4),
        "largest_cluster_ratio": round(largest_cluster_ratio, 4),
        "avg_row_transitions": round(avg_row_transitions, 4),
        "max_row_transitions": int(max_row_transitions),
        "num_rows": num_rows,
        "num_cols": num_cols,
        "vertical_symmetry": round(vertical_symmetry, 4),
        "horizontal_symmetry": round(horizontal_symmetry, 4),
        "vertical_gradient": round(vertical_gradient, 4),
        "horizontal_gradient": round(horizontal_gradient, 4),
        "boundary_monotonicity": round(boundary_monotonicity, 4),
        "boundary_spread": round(boundary_spread, 4),
        "aspect_ratio": round(aspect_ratio, 4),
        "fail_row_fraction": round(fail_row_fraction, 4),
        "fail_col_fraction": round(fail_col_fraction, 4),
    }


def _vertical_symmetry(matrix, num_rows, num_cols, total_cells):
    """Fraction of cells that match their top-bottom mirror (1.0 = symmetric)."""
    if total_cells == 0:
        return 0.0
    matches = 0
    for r in range(num_rows):
        mr = num_rows - 1 - r
        for c in range(num_cols):
            if matrix[r][c] == matrix[mr][c]:
                matches += 1
    return matches / total_cells


def _horizontal_symmetry(matrix, num_rows, num_cols, total_cells):
    """Fraction of cells that match their left-right mirror (1.0 = symmetric)."""
    if total_cells == 0:
        return 0.0
    matches = 0
    for r in range(num_rows):
        row = matrix[r]
        for c in range(num_cols):
            mc = num_cols - 1 - c
            if row[c] == row[mc]:
                matches += 1
    return matches / total_cells


def features_from_rows(rows: List[str]) -> Optional[Dict[str, Any]]:
    """Convenience: rows -> feature dict (None if rows are empty)."""
    if not rows:
        return None
    return compute_features(rows_to_matrix(rows))


def features_to_vector(features: Optional[Dict[str, Any]]) -> List[float]:
    """Convert a feature dict into an ordered float vector following FEATURE_NAMES.

    Missing keys (e.g. features produced by an older version) default to 0.0 so
    vectors always have a consistent length.
    """
    vector: List[float] = []
    for name in FEATURE_NAMES:
        value = (features or {}).get(name, 0.0)
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        try:
            vector.append(float(value))
        except (TypeError, ValueError):
            vector.append(0.0)
    return vector
