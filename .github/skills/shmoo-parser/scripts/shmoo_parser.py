import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def extract_shmoohub_sections(lines: List[str]) -> List[List[str]]:
    """Split file content into shmoo-centered sections keyed by ShmooHub."""
    sections: List[List[str]] = []
    current_section: List[str] = []
    in_shmoo = False

    pending_title: Optional[str] = None
    pending_plist: Optional[str] = None
    pending_dieid: Optional[str] = None
    pending_tname: Optional[str] = None
    current_visualid_line: Optional[str] = None

    for line in lines:
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

        if "shmoohub" in line.lower():
            if in_shmoo and current_section:
                sections.append(current_section)

            current_section = []
            in_shmoo = True

            if current_visualid_line:
                current_section.append(current_visualid_line)
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


def extract_ecads_sections(lines: List[str]) -> List[List[str]]:
    """Split file content into ECADS Plot3 sections."""
    sections: List[List[str]] = []
    current_section: List[str] = []
    in_ecads = False

    pending_plist: Optional[str] = None
    pending_dieid: Optional[str] = None
    pending_tname: Optional[str] = None
    current_visualid_line: Optional[str] = None

    for line in lines:
        plist_match = re.search(r"Plist\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if plist_match:
            pending_plist = plist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", line, re.IGNORECASE)
        if dieid_match:
            pending_dieid = dieid_match.group(1).strip()

        if "visualid" in line.lower() and "strgval_miss" not in line.lower():
            current_visualid_line = line.strip()

        normalized = line.strip().lstrip("\ufeff")
        if re.match(r"\d+_tname_", normalized):
            pending_tname = normalized

        if "_comnt_plot3start_" in line.lower():
            if in_ecads and current_section:
                sections.append(current_section)

            current_section = []
            in_ecads = True

            if current_visualid_line:
                current_section.append(current_visualid_line)
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
    token = payload.strip()
    match = re.search(
        r"(?:\d+_)?strgval_([A-Za-z0-9_]+?)(?=\s*[:\s]|$)", token, re.IGNORECASE
    )
    if match:
        return match.group(1).strip()

    if token.lower().startswith("strgval_"):
        token = token[len("strgval_") :]

    if ":" in token:
        candidate = token.split(":", 1)[0].strip()
        if candidate:
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


def build_failing_data(
    data_string: str,
    axis: Dict[str, float],
    legends: Dict[str, str],
) -> Dict[str, Any]:
    """Convert raw shmoo result string into structured failing point data."""
    rows = parse_data_rows(data_string)

    x_values = build_axis_values(axis["xstart"], axis["xstop"], axis["xstep"])
    y_values = build_axis_values(axis["ystart"], axis["ystop"], axis["ystep"])

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

            failures.append(failure_entry)

    return {
        "raw": data_string,
        "rows": rows,
        "pass_count": pass_count,
        "fail_count": len(failures),
        "failures": failures,
    }


def _extract_team_from_tname(tname: str) -> Optional[str]:
    """Extract team from tname like SCN_SCAN_COMP::TATPG_... -> SCN_SCAN."""
    if not tname:
        return None
    # Strip leading digit_tname_ prefix
    match = re.match(r"\d+_tname_(.+)", tname)
    content = match.group(1) if match else tname
    if "_COMP::" in content:
        return content.split("_COMP::")[0]
    if "::" in content:
        return content.split("::")[0]
    return None


def parse_shmoo_section(section: List[str], source_file: str, section_index: int) -> Optional[Dict[str, Any]]:
    """Parse one shmoo section into a JSON-serializable object."""
    visual_id: Optional[str] = None
    die_id: Optional[str] = None
    plist_name: Optional[str] = None
    plist_from_patterns: Optional[str] = None
    shmoo_title: Optional[str] = None
    team: Optional[str] = None

    legends: Dict[str, str] = {}
    axis: Optional[Dict[str, float]] = None

    shmoo_results_data: Optional[str] = None
    capture_next_as_results = False

    for i, line in enumerate(section):
        stripped = line.strip()

        if capture_next_as_results:
            shmoo_results_data = stripped
            inferred = infer_plist_from_strgval_payload(stripped)
            if inferred:
                plist_from_patterns = inferred
                if not plist_name or plist_name.upper() == "PATMOD":
                    plist_name = inferred
            capture_next_as_results = False
            continue

        maybe_visualid = parse_visualid_from_line(stripped)
        if maybe_visualid:
            visual_id = maybe_visualid

        if "strgval_" in stripped.lower():
            inferred = infer_plist_from_strgval_payload(stripped)
            if inferred:
                plist_from_patterns = inferred
            if not plist_name:
                plist_name = inferred

        tname_match = re.match(r"\d+_tname_(.+)", stripped)
        if tname_match and not team:
            team = _extract_team_from_tname(stripped)

        if "ShmooParams" in stripped:
            shmoo_title = stripped
            if "::" in shmoo_title:
                shmoo_title = shmoo_title.split("::")[-1].replace("_ShmooParams", "")

        plist_match = re.search(r"Plist\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if plist_match:
            plist_name = plist_match.group(1).strip()

        parent_plist_match = re.search(r"parentPlist\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if parent_plist_match and not plist_name:
            plist_name = parent_plist_match.group(1).strip()

        patlist_match = re.search(r"Patlist\s*=\s*\"([^\"]+)\"", stripped, re.IGNORECASE)
        if patlist_match and not plist_name:
            plist_name = patlist_match.group(1).strip()

        dieid_match = re.search(r"DieId\s*=\s*\[([^\]]+)\]", stripped, re.IGNORECASE)
        if dieid_match:
            die_id = dieid_match.group(1).strip()

        if "shmoohub" in stripped.lower() and axis is None:
            axis = parse_shmoo_axis(stripped)

        if "shmooresults" in stripped.lower():
            capture_next_as_results = True

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
                    inferred = infer_plist_from_strgval_payload(failure_info)
                    if inferred:
                        plist_from_patterns = inferred
                    if not plist_name:
                        plist_name = inferred

        if "Legend :" in stripped and "Failure information:" in stripped:
            legend_match = re.search(r"Legend\s*:\s*\[([^\]]+)\]", stripped)
            failure_match = re.search(r"Failure information:\s*(.+)", stripped)
            if legend_match and failure_match:
                legends[legend_match.group(1).strip()] = failure_match.group(1).strip()
                if not plist_name:
                    plist_name = infer_plist_from_text(failure_match.group(1).strip())

    if not plist_name:
        for failure_text in legends.values():
            inferred = infer_plist_from_text(failure_text)
            if inferred:
                plist_name = inferred
                break

    if plist_name and plist_name.upper() == "PATMOD":
        for failure_text in legends.values():
            inferred = infer_plist_from_text(failure_text)
            if inferred and inferred.upper() != "PATMOD":
                plist_name = inferred
                break

    # Pattern-derived plist is more specific than generic Plist=[PATMOD].
    if plist_from_patterns and (not plist_name or plist_name.upper() == "PATMOD"):
        plist_name = plist_from_patterns

    if not plist_name and shmoo_title:
        plist_name = infer_plist_from_text(shmoo_title)

    if axis is None or shmoo_results_data is None:
        return None

    failing_data = build_failing_data(shmoo_results_data, axis, legends)

    return {
        "visual_id": visual_id,
        "instance": shmoo_title,
        "team": team,
        "plist": plist_name,
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
        if maybe_visualid:
            visual_id = maybe_visualid

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
        elif "_comnt_p3legen_" in lower:
            legend_match = re.search(r"_comnt_p3legen_(.+)$", stripped, re.IGNORECASE)
            payload = legend_match.group(1) if legend_match else ""
            if "_" in payload:
                legend_key, failure_info = payload.split("_", 1)
                legend_key = legend_key.strip()
                if legend_key:
                    legends[legend_key] = failure_info.strip()
                    if not plist_name:
                        plist_name = infer_plist_from_text(failure_info)

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

    ecads_team = _extract_team_from_tname(instance_name) if instance_name else None

    return {
        "visual_id": visual_id,
        "instance": instance_name,
        "team": ecads_team,
        "plist": plist_name,
        "axis": axis,
        "failing_data": failing_data,
        "legends": legends,
        "die_id": die_id,
    }


def parse_file(file_path: Path) -> List[Dict[str, Any]]:
    """Extract and parse shmoo sections from supported formats in one file."""
    lines = read_text_lines(file_path)
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

    shmoohub_sections = extract_shmoohub_sections(lines)
    for idx, section in enumerate(shmoohub_sections, start=1):
        result = parse_shmoo_section(section, str(file_path), idx)
        if result:
            append_unique(result)

    ecads_sections = extract_ecads_sections(lines)
    for idx, section in enumerate(ecads_sections, start=1):
        result = parse_ecads_section(section, str(file_path), idx)
        if result:
            append_unique(result)

    return parsed


def parse_inputs(input_path: Path, recursive: bool) -> Dict[str, Any]:
    """Parse all supported input files and return one JSON object."""
    files = find_input_files(input_path, recursive)

    grouped_shmoos: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    files_with_shmoo = 0
    total_shmoos = 0

    for file_path in files:
        parsed = parse_file(file_path)
        if parsed:
            files_with_shmoo += 1
            source_file = str(file_path)
            for entry in parsed:
                visual_id = entry.get("visual_id") or "NO_VISUAL_ID"
                entry_with_source = dict(entry)
                entry_with_source["source_file"] = source_file
                grouped_shmoos[visual_id].append(entry_with_source)
            total_shmoos += len(parsed)

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "path_folder": str(input_path),
        "recursive": recursive,
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

    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    payload = parse_inputs(input_path, args.recursive)
    write_json(output_path, payload)

    print(
        f"Done. Scanned {payload['files_scanned']} file(s), found {payload['total_shmoos']} shmoo section(s)."
    )
    print(f"JSON written to: {output_path}")


if __name__ == "__main__":
    main()
