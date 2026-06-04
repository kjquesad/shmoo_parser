#!/usr/bin/env python3
"""Compare shmoo vmin_found against expected Vmin database and tag high values."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def normalize_rail_key(value: str) -> str:
    text = normalize_text(value)
    if text.startswith("voltage"):
        text = text[len("voltage") :]
    if text.startswith("vcc"):
        text = text[len("vcc") :]
    return text


def parse_mv(value: Any) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        num = float(value)
        return num * 1000.0 if num <= 5 else num

    text = str(value).strip().lower().replace(" ", "")
    if not text:
        return None

    match = re.search(r"(-?\d+(?:\.\d+)?)", text)
    if not match:
        return None

    num = float(match.group(1))

    if "mv" in text:
        return num
    if text.endswith("v") or "volt" in text:
        return num * 1000.0

    return num * 1000.0 if num <= 5 else num


def format_v(value_mv: Optional[float]) -> str:
    if value_mv is None:
        return "N/A"
    return f"{value_mv / 1000.0:.3f}V"


def extract_frequency_tokens(*values: Optional[str]) -> List[str]:
    found: List[str] = []
    for value in values:
        if not value:
            continue
        for token in re.findall(r"(?<![A-Za-z0-9])F\d+(?![A-Za-z0-9])", value, flags=re.IGNORECASE):
            up = token.upper()
            if up not in found:
                found.append(up)
    return found


def split_y_label_tokens(ylabel: str) -> List[str]:
    text = str(ylabel or "")
    if ":" in text:
        text = text.split(":", 1)[1]
    return [tok.strip() for tok in text.split(",") if tok.strip()]


def flatten_expected_db(payload: Any) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Return expected DB indexed as product -> normalized_rail -> frequency -> expected_mv.

    Supports nested shapes where first level are product buckets and second level are rails.
    """
    db: Dict[str, Dict[str, Dict[str, float]]] = {}

    if not isinstance(payload, dict):
        return db

    for product, product_value in payload.items():
        if not isinstance(product_value, dict):
            continue

        product_key = str(product).strip().upper()
        rails: Dict[str, Dict[str, float]] = {}

        for rail_name, rail_value in product_value.items():
            if not isinstance(rail_value, dict):
                continue

            rail_key = normalize_rail_key(str(rail_name))
            if not rail_key:
                continue

            freq_map: Dict[str, float] = {}
            for freq_key, expected_value in rail_value.items():
                freq = str(freq_key).strip().upper()
                if not re.fullmatch(r"F\d+", freq):
                    continue
                expected_mv = parse_mv(expected_value)
                if expected_mv is None:
                    continue
                freq_map[freq] = expected_mv

            if freq_map:
                rails[rail_key] = freq_map

        if rails:
            db[product_key] = rails

    return db


def infer_product_bucket(entry: Dict[str, Any], available_products: Iterable[str]) -> Optional[str]:
    plist = str(entry.get("plist") or "").upper()
    instance = str(entry.get("instance") or "").upper()
    team = str(entry.get("team") or "").upper()

    for product in available_products:
        if product in plist or product in instance or product in team:
            return product

    return next(iter(available_products), None)


def best_rail_match(ylabel: str, rail_map: Dict[str, Dict[str, float]]) -> Optional[str]:
    if not rail_map:
        return None

    y_tokens = split_y_label_tokens(ylabel)
    y_norm_text = normalize_text(ylabel)

    candidates: List[Tuple[int, str]] = []
    for rail_key in rail_map.keys():
        score = 0

        if rail_key and rail_key in y_norm_text:
            score += 3

        for token in y_tokens:
            token_norm = normalize_rail_key(token)
            if not token_norm:
                continue
            if rail_key in token_norm or token_norm in rail_key:
                score += 2

            token_alpha = re.sub(r"\d+", "", token_norm)
            rail_alpha = re.sub(r"\d+", "", rail_key)
            if token_alpha and rail_alpha and (rail_alpha in token_alpha or token_alpha in rail_alpha):
                score += 1

        if score > 0:
            candidates.append((score, rail_key))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def pick_default_frequency(freq_map: Dict[str, float]) -> Tuple[Optional[str], Optional[float], bool]:
    """Pick a default expected frequency when none is found in the shmoo context."""
    if not freq_map:
        return None, None, False

    if "F1" in freq_map:
        return "F1", freq_map["F1"], True

    sortable: List[Tuple[int, str]] = []
    for freq in freq_map.keys():
        match = re.fullmatch(r"F(\d+)", freq)
        if not match:
            continue
        sortable.append((int(match.group(1)), freq))

    if sortable:
        sortable.sort(key=lambda item: item[0])
        selected = sortable[0][1]
        return selected, freq_map[selected], True

    selected_any = next(iter(freq_map.keys()))
    return selected_any, freq_map[selected_any], True


def iter_entries(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    shmoos = payload.get("shmoos")
    if not isinstance(shmoos, dict):
        return

    for _, value in shmoos.items():
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    yield entry
            continue

        if isinstance(value, dict):
            for _, entries in value.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict):
                        yield entry


def parse_filter_set(raw: str) -> Set[str]:
    if not raw:
        return set()
    return {token.strip() for token in raw.split(",") if token.strip()}


def should_process(entry: Dict[str, Any], plist_filters: Set[str], visual_filters: Set[str]) -> bool:
    if plist_filters:
        plist = str(entry.get("plist") or "")
        if not any(pf.lower() in plist.lower() for pf in plist_filters):
            return False

    if visual_filters:
        visual_id = str(entry.get("visual_id") or "")
        if visual_id not in visual_filters:
            return False

    return True


def annotate_vmin(
    payload: Dict[str, Any],
    expected_db: Dict[str, Dict[str, Dict[str, float]]],
    plist_filters: Set[str],
    visual_filters: Set[str],
) -> Dict[str, int]:
    stats = {
        "total_entries": 0,
        "processed_entries": 0,
        "matched_expected": 0,
        "high_count": 0,
        "ok_count": 0,
        "missing_found": 0,
        "no_expected_match": 0,
    }

    for entry in iter_entries(payload):
        stats["total_entries"] += 1

        if not should_process(entry, plist_filters, visual_filters):
            continue

        stats["processed_entries"] += 1

        products = list(expected_db.keys())
        product = infer_product_bucket(entry, products)
        rail_map = expected_db.get(product or "", {})

        ylabel = str((entry.get("axis") or {}).get("ylabel") or "")
        rail_key = best_rail_match(ylabel, rail_map)

        freq_tokens = extract_frequency_tokens(
            str(entry.get("plist") or ""),
            str(entry.get("instance") or ""),
            str((entry.get("axis") or {}).get("xlabel") or ""),
        )

        expected_mv = None
        expected_freq = None
        expected_freq_inferred = False
        freq_map = rail_map.get(rail_key, {}) if rail_key else {}
        if rail_key and freq_tokens:
            for freq in freq_tokens:
                if freq in freq_map:
                    expected_mv = freq_map[freq]
                    expected_freq = freq
                    break

        if expected_mv is None and rail_key and not freq_tokens and freq_map:
            expected_freq, expected_mv, expected_freq_inferred = pick_default_frequency(freq_map)

        original_vmin = entry.get("vmin_found")
        found_mv = parse_mv(original_vmin)

        entry["vmin_found_raw"] = original_vmin

        if expected_mv is None:
            entry["vmin_status"] = "no_expected_match"
            entry["vmin_expected_mv"] = None
            entry["vmin_found_mv"] = found_mv
            entry["vmin_delta_mv"] = None
            entry["vmin_expected_freq"] = expected_freq
            entry["vmin_expected_freq_inferred"] = expected_freq_inferred
            entry["vmin_expected_product"] = product
            entry["vmin_expected_rail"] = rail_key
            entry["vmin_found"] = f"Vmin Found: {format_v(found_mv)}"
            stats["no_expected_match"] += 1
            continue

        stats["matched_expected"] += 1
        entry["vmin_expected_mv"] = round(expected_mv, 3)
        entry["vmin_found_mv"] = round(found_mv, 3) if found_mv is not None else None
        entry["vmin_expected_freq"] = expected_freq
        entry["vmin_expected_freq_inferred"] = expected_freq_inferred
        entry["vmin_expected_product"] = product
        entry["vmin_expected_rail"] = rail_key

        if found_mv is None:
            entry["vmin_status"] = "missing_found"
            entry["vmin_delta_mv"] = None
            entry["vmin_found"] = "Vmin Found: N/A"
            stats["missing_found"] += 1
            continue

        delta_mv = found_mv - expected_mv
        entry["vmin_delta_mv"] = round(delta_mv, 3)

        if delta_mv > 0:
            entry["vmin_status"] = "high"
            entry["vmin_found"] = f"Vmin Found (High): {format_v(found_mv)}"
            stats["high_count"] += 1
        else:
            entry["vmin_status"] = "ok"
            entry["vmin_found"] = f"Vmin Found: {format_v(found_mv)}"
            stats["ok_count"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare shmoo vmin_found values to expected database and tag high Vmin entries."
    )
    parser.add_argument("input_json", help="Path to shmoo_parsed.json or shmoo_classified.json")
    parser.add_argument("expected_json", help="Path to expected Vmin JSON database")
    parser.add_argument("-o", "--output", default="", help="Output JSON path (default: <input>_vmin_tagged.json)")
    parser.add_argument("--plist", default="", help="Optional plist filter (comma-separated substrings)")
    parser.add_argument("--visual-id", default="", help="Optional visual ID filter (comma-separated exact IDs)")
    args = parser.parse_args()

    input_path = Path(args.input_json)
    expected_path = Path(args.expected_json)

    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")
    if not expected_path.exists():
        raise FileNotFoundError(f"Expected Vmin JSON not found: {expected_path}")

    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_vmin_tagged.json")

    payload = load_json(input_path)
    expected_payload = load_json(expected_path)
    expected_db = flatten_expected_db(expected_payload)

    if not expected_db:
        raise ValueError("Expected Vmin JSON has no valid product/rail/frequency entries.")

    plist_filters = parse_filter_set(args.plist)
    visual_filters = parse_filter_set(args.visual_id)

    stats = annotate_vmin(payload, expected_db, plist_filters, visual_filters)
    save_json(output_path, payload)

    print(f"Vmin detector done. Output: {output_path}")
    print(f"Total entries: {stats['total_entries']}")
    print(f"Processed entries: {stats['processed_entries']}")
    print(f"Matched expected: {stats['matched_expected']}")
    print(f"High Vmin: {stats['high_count']}")
    print(f"OK Vmin: {stats['ok_count']}")
    print(f"Missing found Vmin: {stats['missing_found']}")
    print(f"No expected match: {stats['no_expected_match']}")


if __name__ == "__main__":
    main()
