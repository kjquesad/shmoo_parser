import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _progress(msg: str) -> None:
    print(msg, flush=True)


def find_input_files(input_path: Path, recursive: bool) -> List[Path]:
    """Collect candidate console/log files that may contain Shmoo data."""
    supported = {".txt", ".log", ".itf", ".ittuf", ".ituff"}

    if input_path.is_file():
        return [input_path]

    if not input_path.is_dir():
        return []

    if recursive:
        return sorted(
            p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in supported
        )

    return sorted(
        p for p in input_path.iterdir() if p.is_file() and p.suffix.lower() in supported
    )


def read_text_lines(file_path: Path) -> List[str]:
    """Read a text file with a forgiving fallback for mixed encodings."""
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []


def parse_visualid_from_line(line: str) -> Optional[str]:
    """Extract VisualID using the same token styles observed in existing logs."""
    if line.lstrip().upper().startswith("SORT_VISUALID"):
        # Synthetic sort marker; handled by parse_sort_visualid_from_line.
        return None
    if "visualid" not in line.lower() or "strgval_miss" in line.lower():
        return None

    parts = line.split("_")
    for i, part in enumerate(parts):
        if part.lower() == "visualid" and i + 1 < len(parts):
            candidate = parts[i + 1].strip()
            if candidate:
                return candidate

    match = re.search(r"visualid[_\s]*([A-Za-z0-9]+)", line, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    if "visualid_" in line.lower():
        trailing = line.lower().split("visualid_", 1)[1]
        candidate = trailing.split("_")[0].split()[0].strip()
        if candidate:
            return candidate

    lower_line = line.lower()
    pos = lower_line.find("visualid")
    if pos != -1:
        after = line[pos + 8 :].strip()
        match = re.search(r"[_\s]*([A-Za-z0-9]+)", after)
        if match:
            return match.group(1)

    return None


# Sort/wafer ITTUFs do not carry a packaged VisualID. Instead they identify each
# die by wafer id + wafer X/Y coordinates (e.g. "4_wafid_251", "3_wafxloc_-1",
# "3_wafyloc_-2"). We synthesize a VisualID as "<wafid>_<x>_<y>" (WAF_X_Y).
_WAFID_RE = re.compile(r"^\d+_wafid_(\S+)", re.IGNORECASE)
_WAFXLOC_RE = re.compile(r"^\d+_wafxloc_(-?\d+)", re.IGNORECASE)
_WAFYLOC_RE = re.compile(r"^\d+_wafyloc_(-?\d+)", re.IGNORECASE)
_SORT_VISUALID_RE = re.compile(r"SORT_VISUALID=\[([^\]]+)\]")


def build_sort_visualid(
    wafid: Optional[str], wafxloc: Optional[str], wafyloc: Optional[str]
) -> Optional[str]:
    """Construct a sort VisualID as '<wafid>_<x>_<y>' when all parts are present."""
    if wafid and wafxloc is not None and wafyloc is not None:
        return f"{wafid}_{wafxloc}_{wafyloc}"
    return None


def parse_sort_visualid_from_line(line: str) -> Optional[str]:
    """Extract a synthesized sort VisualID from a SORT_VISUALID=[...] marker line."""
    match = _SORT_VISUALID_RE.search(line)
    if match:
        return match.group(1).strip() or None
    return None


def extract_shmoohub_sections(
    lines: List[str], progress_label: str = "", heartbeat_every_lines: int = 250000
) -> List[List[str]]:
    """Split file content into shmoo-centered sections keyed by ShmooHub."""
    sections: List[List[str]] = []
    current_section: List[str] = []
    in_shmoo = False

    pending_title: Optional[str] = None
    pending_plist: Optional[str] = None
    pending_dieid: Optional[str] = None
    pending_tname: Optional[str] = None
    current_visualid_line: Optional[str] = None
    pending_wafid: Optional[str] = None
    pending_wafxloc: Optional[str] = None
    pending_wafyloc: Optional[str] = None

    for line_index, line in enumerate(lines, start=1):
        if heartbeat_every_lines > 0 and line_index % heartbeat_every_lines == 0:
            _progress(
                f"[heartbeat] {progress_label} ShmooHub scan line {line_index}/{len(lines)}"
            )

        plist_match = re.search(r"Plist\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if plist_match:
            pending_plist = plist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if dieid_match:
            pending_dieid = dieid_match.group(1).strip()

        if "_ShmooParams" in line:
            pending_title = line.strip()

        normalized_line = line.strip().lstrip("\ufeff")
        if re.match(r"\d+_tname_", normalized_line):
            pending_tname = normalized_line

        if "visualid" in line.lower() and "strgval_miss" not in line.lower():
            current_visualid_line = line.strip()

        waf_stripped = line.strip().lstrip("\ufeff")
        waf_match = _WAFID_RE.match(waf_stripped)
        if waf_match:
            pending_wafid = waf_match.group(1).strip()
        waf_match = _WAFXLOC_RE.match(waf_stripped)
        if waf_match:
            pending_wafxloc = waf_match.group(1).strip()
        waf_match = _WAFYLOC_RE.match(waf_stripped)
        if waf_match:
            pending_wafyloc = waf_match.group(1).strip()

        if "shmoohub" in line.lower():
            if in_shmoo and current_section:
                sections.append(current_section)

            current_section = []
            in_shmoo = True

            if current_visualid_line:
                current_section.append(current_visualid_line)
            sort_vid = build_sort_visualid(pending_wafid, pending_wafxloc, pending_wafyloc)
            if sort_vid:
                current_section.append(f"SORT_VISUALID=[{sort_vid}]")
            if pending_plist:
                current_section.append(f"Plist=[{pending_plist}]")
            if pending_dieid:
                current_section.append(f"DieId=[{pending_dieid}]")
            if pending_title:
                current_section.append(pending_title)
            if pending_tname:
                current_section.append(pending_tname)

            current_section.append(line)
            continue

        if in_shmoo:
            current_section.append(line)

    if in_shmoo and current_section:
        sections.append(current_section)

    return sections


def extract_ecads_sections(
    lines: List[str], progress_label: str = "", heartbeat_every_lines: int = 250000
) -> List[List[str]]:
    """Split file content into ECADS Plot3 sections."""
    sections: List[List[str]] = []
    current_section: List[str] = []
    in_ecads = False

    pending_plist: Optional[str] = None
    pending_dieid: Optional[str] = None
    pending_tname: Optional[str] = None
    current_visualid_line: Optional[str] = None
    pending_wafid: Optional[str] = None
    pending_wafxloc: Optional[str] = None
    pending_wafyloc: Optional[str] = None

    for line_index, line in enumerate(lines, start=1):
        if heartbeat_every_lines > 0 and line_index % heartbeat_every_lines == 0:
            _progress(
                f"[heartbeat] {progress_label} ECADS scan line {line_index}/{len(lines)}"
            )

        plist_match = re.search(r"Plist\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if plist_match:
            pending_plist = plist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if dieid_match:
            pending_dieid = dieid_match.group(1).strip()

        if "visualid" in line.lower() and "strgval_miss" not in line.lower():
            current_visualid_line = line.strip()

        normalized = line.strip().lstrip("\ufeff")
        waf_match = _WAFID_RE.match(normalized)
        if waf_match:
            pending_wafid = waf_match.group(1).strip()
        waf_match = _WAFXLOC_RE.match(normalized)
        if waf_match:
            pending_wafxloc = waf_match.group(1).strip()
        waf_match = _WAFYLOC_RE.match(normalized)
        if waf_match:
            pending_wafyloc = waf_match.group(1).strip()
        if re.match(r"\d+_tname_", normalized):
            pending_tname = normalized

        if "_comnt_plot3start_" in line.lower():
            if in_ecads and current_section:
                sections.append(current_section)

            current_section = []
            in_ecads = True

            if current_visualid_line:
                current_section.append(current_visualid_line)
            sort_vid = build_sort_visualid(pending_wafid, pending_wafxloc, pending_wafyloc)
            if sort_vid:
                current_section.append(f"SORT_VISUALID=[{sort_vid}]")
            if pending_plist:
                current_section.append(f"Plist=[{pending_plist}]")
            if pending_dieid:
                current_section.append(f"DieId=[{pending_dieid}]")
            if pending_tname:
                current_section.append(pending_tname)

            current_section.append(line)
            continue

        if in_ecads:
            current_section.append(line)
            if "_comnt_plt3end_" in line.lower():
                sections.append(current_section)
                current_section = []
                in_ecads = False

    if in_ecads and current_section:
        sections.append(current_section)

    return sections


def extract_sections_single_pass(
    lines: List[str], progress_label: str = "", heartbeat_every_lines: int = 250000
) -> tuple[List[List[str]], List[List[str]]]:
    """Extract ShmooHub and ECADS sections in a single scan over file lines."""
    shmoohub_sections: List[List[str]] = []
    ecads_sections: List[List[str]] = []

    shmoohub_current: List[str] = []
    ecads_current: List[str] = []
    in_shmoohub = False
    in_ecads = False

    pending_title: Optional[str] = None
    pending_plist: Optional[str] = None
    pending_dieid: Optional[str] = None
    pending_tname: Optional[str] = None
    current_visualid_line: Optional[str] = None
    pending_wafid: Optional[str] = None
    pending_wafxloc: Optional[str] = None
    pending_wafyloc: Optional[str] = None

    for line_index, line in enumerate(lines, start=1):
        if heartbeat_every_lines > 0 and line_index % heartbeat_every_lines == 0:
            _progress(
                f"[heartbeat] {progress_label} single-pass scan line {line_index}/{len(lines)}"
            )

        lower_line = line.lower()

        plist_match = re.search(r"Plist\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if plist_match:
            pending_plist = plist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if dieid_match:
            pending_dieid = dieid_match.group(1).strip()

        if "_ShmooParams" in line:
            pending_title = line.strip()

        normalized_line = line.strip().lstrip("\ufeff")
        if re.match(r"\d+_tname_", normalized_line):
            pending_tname = normalized_line

        if "visualid" in lower_line and "strgval_miss" not in lower_line:
            current_visualid_line = line.strip()

        waf_match = _WAFID_RE.match(normalized_line)
        if waf_match:
            pending_wafid = waf_match.group(1).strip()
        waf_match = _WAFXLOC_RE.match(normalized_line)
        if waf_match:
            pending_wafxloc = waf_match.group(1).strip()
        waf_match = _WAFYLOC_RE.match(normalized_line)
        if waf_match:
            pending_wafyloc = waf_match.group(1).strip()

        if "shmoohub" in lower_line:
            if in_shmoohub and shmoohub_current:
                shmoohub_sections.append(shmoohub_current)

            shmoohub_current = []
            in_shmoohub = True

            if current_visualid_line:
                shmoohub_current.append(current_visualid_line)
            sort_vid = build_sort_visualid(pending_wafid, pending_wafxloc, pending_wafyloc)
            if sort_vid:
                shmoohub_current.append(f"SORT_VISUALID=[{sort_vid}]")
            if pending_plist:
                shmoohub_current.append(f"Plist=[{pending_plist}]")
            if pending_dieid:
                shmoohub_current.append(f"DieId=[{pending_dieid}]")
            if pending_title:
                shmoohub_current.append(pending_title)
            if pending_tname:
                shmoohub_current.append(pending_tname)

            shmoohub_current.append(line)
            continue

        if "_comnt_plot3start_" in lower_line:
            if in_ecads and ecads_current:
                ecads_sections.append(ecads_current)

            ecads_current = []
            in_ecads = True

            if current_visualid_line:
                ecads_current.append(current_visualid_line)
            sort_vid = build_sort_visualid(pending_wafid, pending_wafxloc, pending_wafyloc)
            if sort_vid:
                ecads_current.append(f"SORT_VISUALID=[{sort_vid}]")
            if pending_plist:
                ecads_current.append(f"Plist=[{pending_plist}]")
            if pending_dieid:
                ecads_current.append(f"DieId=[{pending_dieid}]")
            if pending_tname:
                ecads_current.append(pending_tname)

            ecads_current.append(line)
            continue

        if in_shmoohub:
            shmoohub_current.append(line)

        if in_ecads:
            ecads_current.append(line)
            if "_comnt_plt3end_" in lower_line:
                ecads_sections.append(ecads_current)
                ecads_current = []
                in_ecads = False

    if in_shmoohub and shmoohub_current:
        shmoohub_sections.append(shmoohub_current)

    if in_ecads and ecads_current:
        ecads_sections.append(ecads_current)

    return shmoohub_sections, ecads_sections


def parse_shmoo_axis(line: str) -> Optional[Dict[str, float]]:
    """Parse ShmooHub axis tokens from a line."""
    segments = line.split("^")
    if len(segments) < 8:
        return None

    try:
        xstart = float(segments[1])
        xstop = float(segments[2])
        xstep = float(segments[3])
        ystart = float(segments[5])
        ystop = float(segments[6])
        ystep = float(segments[7].split("_")[0])
    except (ValueError, IndexError):
        return None

    unit = " "
    if 1e-12 <= abs(xstart) <= 1e-3:
        xstart *= 1e9
        xstop *= 1e9
        xstep *= 1e9
        unit = "ns"

    # Extract axis labels from ShmooHub token.
    # segments[0] example: "0_strgval_TIMING:bck_param" -> xlabel = "TIMING:bck_param"
    # segments[4] example: "VOLTAGE:VCCINF"             -> ylabel
    xlabel = ""
    ylabel = ""
    s0 = segments[0]
    lower_s0 = s0.lower()
    if "_strgval_" in lower_s0:
        idx = lower_s0.index("_strgval_") + len("_strgval_")
        xlabel = s0[idx:]
    if len(segments) > 4:
        ylabel = segments[4].strip()

    return {
        "xstart": xstart,
        "xstop": xstop,
        "xstep": xstep,
        "ystart": ystart,
        "ystop": ystop,
        "ystep": ystep,
        "unit": unit,
        "xlabel": xlabel,
        "ylabel": ylabel,
    }


def parse_ecads_float(value: str) -> Optional[float]:
    """Parse float token from ECADS key/value lines."""
    try:
        return float(value.strip())
    except ValueError:
        return None


def infer_plist_from_text(text: str) -> Optional[str]:
    """Best-effort plist extraction from freeform failure text."""
    strgval_match = re.search(
        r"(?:\d+_)?strgval_([A-Za-z0-9_]+?)(?=\s*[:\s]|$)", text, re.IGNORECASE
    )
    if strgval_match:
        return strgval_match.group(1).strip()

    bracketed = re.search(r"parentPlist\s*=\s*\[([^\]]+)\]", text, re.IGNORECASE)
    if bracketed:
        return bracketed.group(1).strip()

    bracketed = re.search(r"Plist\s*=\s*\[([^\]]+)\]", text, re.IGNORECASE)
    if bracketed:
        return bracketed.group(1).strip()

    explicit = re.search(r"\b([A-Za-z0-9_]*plist)\b", text, re.IGNORECASE)
    if explicit:
        return explicit.group(1)

    list_like = re.search(r"\b([A-Za-z0-9_]*_list)\b", text, re.IGNORECASE)
    if list_like:
        return list_like.group(1)

    return None


def infer_plist_from_strgval_payload(payload: str) -> Optional[str]:
    """Extract plist from payloads shaped like strgval_<plist>:pattern..."""
    # Known axis label prefixes that are NOT plists
    _AXIS_KEYWORDS = {"TIMING", "VOLTAGE", "FREQUENCY", "CURRENT", "TEMP", "TEMPERATURE"}

    def _is_shmoo_grid_data(candidate: str) -> bool:
        """Return True if the candidate looks like shmoo grid data (e.g., AAAAAAA, ****BBB)."""
        if not candidate:
            return True
        # Shmoo grid rows are underscore-separated tokens of equal length containing only
        # pass/fail symbols (*, A-Z, a-z, 0-9). Real plist names have meaningful word
        # structure with varying token lengths.
        parts = candidate.split("_")
        if len(parts) >= 3:
            # Check if all parts are same length (grid rows are uniform width)
            lengths = set(len(p) for p in parts if p)
            if len(lengths) == 1:
                # All tokens same width — likely grid data
                sample = "".join(parts)
                # Grid data is only pass/fail symbols with no lowercase multi-char words
                if all(c in "*ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" for c in sample):
                    return True
        # Single token: if it's all the same character repeated, it's grid data
        stripped = candidate.replace("_", "")
        if stripped and len(set(stripped)) <= 3 and len(stripped) > 4:
            return True
        return False

    token = payload.strip()
    match = re.search(
        r"(?:\d+_)?strgval_([A-Za-z0-9_]+?)(?=\s*[:\s]|$)", token, re.IGNORECASE
    )
    if match:
        candidate = match.group(1).strip()
        if candidate.upper() not in _AXIS_KEYWORDS and not _is_shmoo_grid_data(candidate):
            return candidate

    if token.lower().startswith("strgval_"):
        token = token[len("strgval_") :]

    if ":" in token:
        candidate = token.split(":", 1)[0].strip()
        if candidate and candidate.upper() not in _AXIS_KEYWORDS and not _is_shmoo_grid_data(candidate):
            return candidate

    return None


def parse_data_rows(data_string: str) -> List[str]:
    """Split encoded shmoo data rows."""
    parts = data_string.split("_")

    if parts and parts[0].isdigit():
        parts = parts[1:]

    if parts and parts[0].isalpha():
        parts = parts[1:]

    return parts


def build_axis_values(start: float, stop: float, step: float) -> List[float]:
    """Create a deterministic axis list from start/stop/step."""
    if step == 0:
        return [start]

    count = int(round((stop - start) / step)) + 1
    if count <= 1:
        return [start]

    return [start + i * step for i in range(count)]


# Conversion from axis time units to seconds (repetition legend keys encode
# timing in SI seconds, e.g. "9E-09" == 9 ns).
_UNIT_TO_SECONDS_FACTOR = {
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "µs": 1e-6,
    "ns": 1e-9,
    "ps": 1e-12,
}


def _build_coord_legend_map(
    legends: Dict[str, str],
    axis: Dict[str, float],
    x_values: List[float],
    y_values: List[float],
) -> Dict[str, List[str]]:
    """Map grid index "x_idx|y_idx" -> failure infos for coordinate-keyed legends.

    Repetition shmoos use legend keys like "[9E-09^0.55^0]" encoding
    (timing_in_seconds ^ voltage ^ repetition_index). The grid symbol in these
    shmoos is a digit (how many repetitions failed at that point), so the failure
    info cannot be looked up by symbol. Instead, each failing point's (x, y)
    coordinate is matched against these legend keys.
    """
    coord_map: Dict[str, List[str]] = {}
    if not legends:
        return coord_map

    unit = str(axis.get("unit", "")).strip().lower()
    factor = _UNIT_TO_SECONDS_FACTOR.get(unit)  # seconds per axis time-unit
    xstep = float(axis.get("xstep") or 0) or 1.0
    ystep = float(axis.get("ystep") or 0) or 1.0
    xtol = abs(xstep) * 0.5 or 0.5
    ytol = abs(ystep) * 0.5 or 0.5

    def nearest_idx(value: float, values: List[float], tol: float) -> int:
        best_i, best_d = -1, None
        for i, v in enumerate(values):
            d = abs(v - value)
            if best_d is None or d < best_d:
                best_d, best_i = d, i
        if best_i != -1 and best_d is not None and best_d <= tol:
            return best_i
        return -1

    for key, info in legends.items():
        k = key.strip()
        if not k.startswith("[") or "^" not in k:
            continue
        body = k[1:]
        if body.endswith("]"):
            body = body[:-1]
        parts = body.split("^")
        if len(parts) < 2:
            continue
        try:
            xval = float(parts[0])
            yval = float(parts[1])
        except ValueError:
            continue
        # Legend timing is in seconds; convert to axis units when the unit is known.
        xval_axis = xval / factor if factor else xval
        x_idx = nearest_idx(xval_axis, x_values, xtol)
        y_idx = nearest_idx(yval, y_values, ytol)
        if x_idx == -1 or y_idx == -1:
            continue
        bucket = coord_map.setdefault(f"{x_idx}|{y_idx}", [])
        if info not in bucket:
            bucket.append(info)

    return coord_map


def build_failing_data(
    data_string: str,
    axis: Dict[str, float],
    legends: Dict[str, str],
) -> Dict[str, Any]:
    """Convert raw shmoo result string into structured failing point data."""
    rows = parse_data_rows(data_string)

    x_values = build_axis_values(axis["xstart"], axis["xstop"], axis["xstep"])
    y_values = build_axis_values(axis["ystart"], axis["ystop"], axis["ystep"])

    coord_legends = _build_coord_legend_map(legends, axis, x_values, y_values)

    failures: List[Dict[str, Any]] = []
    pass_count = 0

    for y_idx, row in enumerate(rows):
        if y_idx >= len(y_values):
            break

        for x_idx, symbol in enumerate(row):
            if x_idx >= len(x_values):
                break

            if symbol == "*":
                pass_count += 1
                continue

            failure_entry: Dict[str, Any] = {
                "x": x_values[x_idx],
                "y": y_values[y_idx],
                "symbol": symbol,
            }

            if symbol in legends:
                failure_entry["legend_info"] = legends[symbol]
            else:
                coord_info = coord_legends.get(f"{x_idx}|{y_idx}")
                if coord_info:
                    failure_entry["legend_info"] = " ; ".join(coord_info)

            failures.append(failure_entry)

    return {
        "raw": data_string,
        "rows": rows,
        "pass_count": pass_count,
        "fail_count": len(failures),
        "failures": failures,
    }


def find_vmin_from_center(axis: Dict[str, float], rows: List[str]) -> Optional[float]:
    """Find vmin by scanning the center column from low Y to high Y for first pass ('*').

    If no passing point is found in the center column (fully failing shmoo), return
    the highest Y value on the axis — the device was still failing at max tested voltage.
    """
    if not rows:
        return None

    # Use the widest row to define the center probing column.
    max_cols = max((len(row) for row in rows), default=0)
    if max_cols == 0:
        return None

    center_col = max_cols // 2
    y_values = build_axis_values(axis["ystart"], axis["ystop"], axis["ystep"])

    row_count = min(len(rows), len(y_values))
    for y_idx in range(row_count):
        row = rows[y_idx]
        if center_col >= len(row):
            continue
        if row[center_col] == "*":
            return round(y_values[y_idx], 6)

    # No pass found anywhere in center column — fully failing shmoo.
    # Return the highest Y tested so downstream vmin comparisons see the worst case.
    if y_values:
        return round(y_values[-1], 6)

    return None


def _extract_team_from_tname(tname: str) -> Optional[str]:
    """Extract team from tname.

    Formats:
      - SCN_SCAN_COMP::TATPG_...          -> SCN_SCAN
      - IP_IMH::SCN_A_IMH::STUCK_...      -> SCN_A_IMH  (die::team::testname)
    """
    if not tname:
        return None
    # Strip leading digit_tname_ prefix
    match = re.match(r"\d+_tname_(.+)", tname)
    content = match.group(1) if match else tname
    if "_COMP::" in content:
        return content.split("_COMP::")[0]
    parts = content.split("::")
    if len(parts) >= 3:
        # die::team::testname — return team (second segment)
        return parts[1]
    if len(parts) == 2:
        return parts[0]
    return None


def _extract_instance_from_tname(tname: str) -> Optional[str]:
    """Extract instance/testname portion from tname line."""
    if not tname:
        return None

    match = re.match(r"\d+_tname_(.+)", tname)
    content = match.group(1).strip() if match else tname.strip()
    if not content:
        return None

    if content.lower().startswith("testtime_"):
        content = content[len("testtime_") :]

    parts = content.split("::")
    candidate = parts[-1].strip() if parts else content
    if not candidate:
        return None

    candidate = re.sub(r"_(ShmooParams|ShmooResults|SSTP)$", "", candidate)
    return candidate or None


def parse_shmoo_section(section: List[str], source_file: str, section_index: int) -> Optional[Dict[str, Any]]:
    """Parse one shmoo section into a JSON-serializable object."""
    visual_id: Optional[str] = None
    die_id: Optional[str] = None
    shmoo_title: Optional[str] = None
    team: Optional[str] = None

    legends: Dict[str, str] = {}
    axis: Optional[Dict[str, float]] = None

    shmoo_results_data: Optional[str] = None
    capture_next_as_results = False
    tname_instances: List[str] = []
    shmoo_instance: Optional[str] = None

    # Plist candidates collected during parsing (resolved by priority after loop)
    plist_from_strgval: Optional[str] = None       # Priority 1: ^LEGEND^ + next strgval_ line
    plist_from_failure_info: Optional[str] = None  # Priority 2: Failure information: pattern|num:plist:port
    plist_from_bracket: Optional[str] = None       # Priority 3: Plist=[...] or Plist name=[...]

    def _extract_plist_from_payload(text: str) -> Optional[str]:
        """Extract plist from strgval/failure-info payload.

        Handles formats:
          - <plist>:<pattern>                        (plist first, no pipe)
          - <pattern>:<plist>:<testport>             (pattern first, no pipe, 3+ segments)
          - <pattern>|<num>:<instance>::<plist>:...  (pipe format with :: separator)
          - <pattern>|<num>:<plist>:<testport>       (pipe format without ::)
        """
        if ":" not in text:
            return None
        first_seg = text.split(":", 1)[0].strip()
        if "|" in first_seg:
            # Has pipe: pattern|num:<...>
            if "::" in text:
                after_dcolon = text.split("::", 1)[1]
                return after_dcolon.split(":", 1)[0].strip() or None
            else:
                parts = text.split(":")
                return parts[1].strip() if len(parts) >= 2 else None
        else:
            # No pipe — check segment count and whether first_seg is a pattern hash
            parts = text.split(":")
            is_hash = bool(re.match(r"^[a-zA-Z]\d{5,}", first_seg))
            if is_hash and len(parts) >= 2:
                # pattern:plist:testport — plist is parts[1]
                return parts[1].strip() or None
            else:
                # plist:pattern
                return first_seg or None

    for i, line in enumerate(section):
        stripped = line.strip()

        if capture_next_as_results:
            shmoo_results_data = stripped
            capture_next_as_results = False
            continue

        maybe_visualid = parse_visualid_from_line(stripped)
        if maybe_visualid and not visual_id:
            # Keep the first visual ID observed for this section to avoid
            # cross-unit overwrite when later lines from subsequent context appear.
            visual_id = maybe_visualid

        maybe_sort_visualid = parse_sort_visualid_from_line(stripped)
        if maybe_sort_visualid and not visual_id:
            # Sort/wafer ITTUFs have no packaged VisualID; use synthesized WAF_X_Y.
            visual_id = maybe_sort_visualid

        tname_match = re.match(r"\d+_tname_(.+)", stripped)
        if tname_match:
            if not team:
                team = _extract_team_from_tname(stripped)
            instance_candidate = _extract_instance_from_tname(stripped)
            if instance_candidate:
                tname_instances.append(instance_candidate)
                # The tname carrying _ShmooResults is the definitive instance for
                # strgval-format shmoos. Later tname lines in the same section can
                # belong to unrelated tests (e.g. absorbed VMIN scalars) and must
                # not override this.
                if "shmooresults" in stripped.lower() and shmoo_instance is None:
                    shmoo_instance = instance_candidate

        if "ShmooParams" in stripped:
            shmoo_title = stripped
            if "::" in shmoo_title:
                shmoo_title = shmoo_title.split("::")[-1].replace("_ShmooParams", "")

        # Priority 3: Plist=[...] or Plist name=[...]
        plist_match = re.search(r"Plist\s*(?:name)?\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if plist_match and not plist_from_bracket:
            plist_from_bracket = plist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if dieid_match:
            die_id = dieid_match.group(1).strip()

        if "shmoohub" in stripped.lower() and axis is None:
            axis = parse_shmoo_axis(stripped)

        if "shmooresults" in stripped.lower():
            capture_next_as_results = True

        # ^LEGEND^ handling: collect legend text + Priority 1 plist from strgval
        if "^LEGEND^" in stripped:
            parts = stripped.split("^")
            try:
                legend_idx = parts.index("LEGEND")
            except ValueError:
                legend_idx = -1

            if legend_idx != -1 and legend_idx + 1 < len(parts):
                legend_char = parts[legend_idx + 1].strip()

                if legend_char.startswith("["):
                    bracket_content = legend_char
                    part_idx = legend_idx + 2
                    while not bracket_content.endswith("]") and part_idx < len(parts):
                        bracket_content += "^" + parts[part_idx]
                        part_idx += 1
                    legend_char = bracket_content

                if i + 1 < len(section) and "strgval_" in section[i + 1]:
                    failure_info = section[i + 1].split("strgval_", 1)[1].strip()
                    legends[legend_char] = failure_info
                    # Priority 1: extract plist from strgval payload
                    if not plist_from_strgval:
                        candidate = _extract_plist_from_payload(failure_info)
                        if candidate:
                            plist_from_strgval = candidate

        # "Legend : [X] ... Failure information: ..." handling
        if "Legend :" in stripped and "Failure information:" in stripped:
            legend_match = re.search(r"Legend\s*:\s*\[([^\]]+)\]", stripped)
            failure_match = re.search(r"Failure information:\s*(.+)", stripped)
            if legend_match and failure_match:
                legends[legend_match.group(1).strip()] = failure_match.group(1).strip()
                # Priority 2: extract plist from failure info payload
                if not plist_from_failure_info:
                    candidate = _extract_plist_from_payload(failure_match.group(1).strip())
                    if candidate:
                        plist_from_failure_info = candidate

        # P3Legend format (ECADS-style legends in ituff)
        if "2_comnt_P3Legend_" in stripped:
            p3_match = re.search(r"2_comnt_P3Legend_([A-Z])_[^|]*\|(\d+):(.+)$", stripped)
            if p3_match:
                legend_char = p3_match.group(1).strip()
                legend_description = p3_match.group(3).strip()
                legends[legend_char] = legend_description
                # P3Legend format: char_pattern|num:plist_name — description IS the plist
                if not plist_from_failure_info:
                    plist_from_failure_info = legend_description

    # Resolve plist by priority: strgval > failure_info > bracket
    plist_name = plist_from_strgval or plist_from_failure_info or plist_from_bracket or None

    if axis is None or shmoo_results_data is None:
        return None

    instance_name: Optional[str] = None

    # A tname explicitly tagged with _ShmooResults is the true owner of this grid.
    if shmoo_instance:
        instance_name = shmoo_instance

    # Prefer instance candidates parsed from tname lines over generic ShmooParams wrappers.
    if instance_name is None:
        for candidate in tname_instances:
            upper = candidate.upper()
            if "VMIN" in upper and not upper.startswith("RESET_"):
                instance_name = candidate
                break

    if instance_name is None:
        for candidate in tname_instances:
            if not candidate.upper().startswith("RESET_"):
                instance_name = candidate
                break

    if instance_name is None:
        instance_name = shmoo_title

    # Some chain-group plists can be wrapped by RESET_* shmoo labels.
    # When that happens, promote to the chain-group instance form.
    if instance_name and instance_name.upper().startswith("RESET_") and plist_name:
        plist_lower = plist_name.lower()
        chain_group_match = re.search(r"group(\d+)_x_atpg_chain", plist_lower)
        if chain_group_match and "bgnimh_ssn_edt" in plist_lower:
            group_num = chain_group_match.group(1)
            instance_name = f"CHAIN_GROUP{group_num}_VMIN_K_BGNIMH_SSN_X_VMIN_X_X"

    failing_data = build_failing_data(shmoo_results_data, axis, legends)
    vmin_found = find_vmin_from_center(axis, failing_data.get("rows", []))

    return {
        "visual_id": visual_id,
        "instance": instance_name,
        "team": team,
        "plist": plist_name,
        "vmin_found": vmin_found,
        "axis": axis,
        "failing_data": failing_data,
        "legends": legends,
        "die_id": die_id,
    }


def parse_ecads_section(section: List[str], source_file: str, section_index: int) -> Optional[Dict[str, Any]]:
    """Parse one ECADS Plot3 section into a JSON-serializable object."""
    del source_file, section_index

    visual_id: Optional[str] = None
    die_id: Optional[str] = None
    plist_name: Optional[str] = None
    instance_name: Optional[str] = None

    x_start: Optional[float] = None
    x_stop: Optional[float] = None
    y_start: Optional[float] = None
    y_stop: Optional[float] = None
    x_steps_count: Optional[float] = None
    y_steps_count: Optional[float] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None

    data_rows: List[str] = []
    legends: Dict[str, str] = {}

    for line in section:
        stripped = line.strip().lstrip("\ufeff")
        lower = stripped.lower()

        maybe_visualid = parse_visualid_from_line(stripped)
        if maybe_visualid and not visual_id:
            # Keep first visual ID in section; later visualid tokens can belong
            # to neighboring units in mixed logs.
            visual_id = maybe_visualid

        maybe_sort_visualid = parse_sort_visualid_from_line(stripped)
        if maybe_sort_visualid and not visual_id:
            # Sort/wafer ITTUFs have no packaged VisualID; use synthesized WAF_X_Y.
            visual_id = maybe_sort_visualid

        plist_match = re.search(r"Plist\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if plist_match:
            plist_name = plist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if dieid_match:
            die_id = dieid_match.group(1).strip()

        tname_match = re.match(r"\d+_tname_(.+)", stripped)
        if tname_match:
            instance_name = tname_match.group(1).strip()

        if "_comnt_plot_pxstart," in lower:
            x_start = parse_ecads_float(stripped.split(",", 1)[1])
        elif "_comnt_plot_pystart," in lower:
            y_start = parse_ecads_float(stripped.split(",", 1)[1])
        elif "_comnt_plot_pxstop," in lower:
            x_stop = parse_ecads_float(stripped.split(",", 1)[1])
        elif "_comnt_plot_pystop," in lower:
            y_stop = parse_ecads_float(stripped.split(",", 1)[1])
        elif "_comnt_plot_pxstep," in lower:
            x_steps_count = parse_ecads_float(stripped.split(",", 1)[1])
        elif "_comnt_plot_pystep," in lower:
            y_steps_count = parse_ecads_float(stripped.split(",", 1)[1])
        elif "_comnt_plot_pxname," in lower:
            x_label = stripped.split(",", 1)[1].strip()
        elif "_comnt_plot_pyname," in lower:
            y_label = stripped.split(",", 1)[1].strip()
        elif "_comnt_p3data_" in lower:
            data_match = re.search(r"_comnt_p3data_(.+)$", stripped, re.IGNORECASE)
            payload = data_match.group(1) if data_match else ""
            if payload and payload[0].isalpha() and len(payload) > 1:
                data_rows.append(payload[1:])
            elif payload:
                data_rows.append(payload)
        elif "_comnt_p3legend_" in lower:
            p3_match = re.search(r"_comnt_p3legend_([A-Z])_[^|]*\|(\d+):(.+)$", stripped, re.IGNORECASE)
            if p3_match:
                legend_char = p3_match.group(1).strip()
                legend_description = p3_match.group(3).strip()
                legends[legend_char] = legend_description
                if not plist_name:
                    plist_name = infer_plist_from_text(legend_description)

    required = [x_start, x_stop, y_start, y_stop, x_steps_count, y_steps_count]
    if any(value is None for value in required) or not data_rows:
        return None

    # ECADS step fields are documented as number of steps, excluding first point.
    x_step = 0.0 if x_steps_count == 0 else (x_stop - x_start) / x_steps_count
    y_step = 0.0 if y_steps_count == 0 else (y_stop - y_start) / y_steps_count

    axis = {
        "xstart": x_start,
        "xstop": x_stop,
        "xstep": x_step,
        "ystart": y_start,
        "ystop": y_stop,
        "ystep": y_step,
        "unit": " ",
        "xlabel": x_label or "",
        "ylabel": y_label or "",
    }

    ecads_data_string = "_".join(data_rows)
    failing_data = build_failing_data(ecads_data_string, axis, legends)
    vmin_found = find_vmin_from_center(axis, failing_data.get("rows", []))

    ecads_team = _extract_team_from_tname(instance_name) if instance_name else None

    return {
        "visual_id": visual_id,
        "instance": instance_name,
        "team": ecads_team,
        "plist": plist_name,
        "vmin_found": vmin_found,
        "axis": axis,
        "failing_data": failing_data,
        "legends": legends,
        "die_id": die_id,
    }


def parse_file(file_path: Path) -> List[Dict[str, Any]]:
    """Extract and parse shmoo sections from supported formats in one file."""
    _progress(f"[parser] Reading {file_path}")
    lines = read_text_lines(file_path)
    _progress(f"[parser] Loaded {len(lines)} line(s) from {file_path.name}")
    parsed: List[Dict[str, Any]] = []
    seen_fingerprints = set()

    def append_unique(entry: Dict[str, Any]) -> None:
        axis = entry.get("axis", {})
        failing = entry.get("failing_data", {})
        fingerprint = (
            entry.get("visual_id"),
            entry.get("instance"),
            entry.get("plist"),
            axis.get("xstart"),
            axis.get("xstop"),
            axis.get("xstep"),
            axis.get("ystart"),
            axis.get("ystop"),
            axis.get("ystep"),
            failing.get("raw"),
        )
        if fingerprint not in seen_fingerprints:
            seen_fingerprints.add(fingerprint)
            parsed.append(entry)

    shmoohub_sections, ecads_sections = extract_sections_single_pass(
        lines, progress_label=file_path.name
    )
    _progress(f"[parser] {file_path.name}: found {len(shmoohub_sections)} ShmooHub section(s)")
    for idx, section in enumerate(shmoohub_sections, start=1):
        result = parse_shmoo_section(section, str(file_path), idx)
        if result:
            append_unique(result)
        if idx % 200 == 0:
            _progress(
                f"[heartbeat] {file_path.name} parsed {idx}/{len(shmoohub_sections)} ShmooHub section(s)"
            )

    _progress(f"[parser] {file_path.name}: found {len(ecads_sections)} ECADS section(s)")
    for idx, section in enumerate(ecads_sections, start=1):
        result = parse_ecads_section(section, str(file_path), idx)
        if result:
            append_unique(result)
        if idx % 200 == 0:
            _progress(
                f"[heartbeat] {file_path.name} parsed {idx}/{len(ecads_sections)} ECADS section(s)"
            )

    _progress(f"[parser] Completed {file_path.name}: {len(parsed)} parsed shmoo(s)")

    return parsed


def _parse_filter_tokens(team_filter: str) -> List[str]:
    """Split free-form team filter text into normalized tokens."""
    if not team_filter:
        return []
    tokens = re.split(r"[\s,;|]+", team_filter.strip())
    return [token.upper() for token in tokens if token.strip()]


def _entry_matches_team_filter(entry: Dict[str, Any], team_filter: str) -> bool:
    """Return True when all team-filter tokens are present in team/instance/plist context."""
    tokens = _parse_filter_tokens(team_filter)
    if not tokens:
        return True

    context = " ".join(
        [
            str(entry.get("team") or ""),
            str(entry.get("instance") or ""),
            str(entry.get("plist") or ""),
        ]
    ).upper()

    return all(token in context for token in tokens)


KNOWN_LOCATIONS = [
    "CLASSHOT",
    "CLASSCOLD",
    "CLASSROOM",
    "CLASS",
    "PHMHOT",
    "PHMCOLD",
    "PHM",
    "QAHOT",
    "QACOLD",
    "CSM",
    "HOT",
    "COLD",
]


def _extract_location_from_filename(file_path: Path) -> Optional[str]:
    """Derive a test location (e.g. CLASSHOT, CSM, PHMHOT) from the file name."""
    name = file_path.stem.upper()
    for location in KNOWN_LOCATIONS:
        if location in name:
            return location
    return None


def parse_inputs(input_path: Path, recursive: bool, team_filter: str = "") -> Dict[str, Any]:
    """Parse all supported input files and return one JSON object."""
    files = find_input_files(input_path, recursive)

    grouped_shmoos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    files_with_shmoo = 0
    total_shmoos = 0

    if files:
        _progress(f"[parser] Files queued: {len(files)}")

    for file_index, file_path in enumerate(files, start=1):
        _progress(f"[parser] Processing file {file_index}/{len(files)}: {file_path.name}")
        parsed = parse_file(file_path)
        if team_filter:
            parsed = [entry for entry in parsed if _entry_matches_team_filter(entry, team_filter)]
        if parsed:
            files_with_shmoo += 1
            source_file = str(file_path)
            location = _extract_location_from_filename(file_path)
            for entry in parsed:
                visual_id = entry.get("visual_id") or "NO_VISUAL_ID"
                entry_with_source = dict(entry)
                entry_with_source["source_file"] = source_file
                entry_with_source["location"] = location
                grouped_shmoos[visual_id].append(entry_with_source)
            total_shmoos += len(parsed)

        _progress(
            f"[parser] File {file_index}/{len(files)} done: {len(parsed)} shmoo(s) kept"
        )

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path_folder": str(input_path),
        "recursive": recursive,
        "team_filter": team_filter or None,
        "files_scanned": len(files),
        "files_with_shmoo": files_with_shmoo,
        "total_shmoos": total_shmoos,
        "shmoos": dict(grouped_shmoos),
    }


def write_json(output_path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON output with stable formatting for future tooling."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse ITTUF/ITUFF/log shmoo outputs into structured JSON."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=".",
        help="Input file or directory to scan (default: current directory).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="shmoo_parsed.json",
        help="Output JSON file path (default: shmoo_parsed.json).",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan subfolders when input is a directory.",
    )
    parser.add_argument(
        "--team-filter",
        default="",
        help=(
            "Optional team filter text. Entries are kept only when all tokens are present in "
            "team/instance/plist (examples: 'SCN', 'SCN CBB', 'SCN IMH')."
        ),
    )

    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    payload = parse_inputs(input_path, args.recursive, args.team_filter)
    write_json(output_path, payload)

    _progress(
        f"Done. Scanned {payload['files_scanned']} file(s), found {payload['total_shmoos']} shmoo section(s)."
    )
    if args.team_filter:
        _progress(f"Applied team filter: {args.team_filter}")
    _progress(f"JSON written to: {output_path}")


if __name__ == "__main__":
    main()
