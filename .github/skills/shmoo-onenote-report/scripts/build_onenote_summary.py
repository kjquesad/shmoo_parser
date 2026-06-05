"""Build a OneNote-ready summary payload from enriched shmoo JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_stats(payload: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, int], int, int]:
    shmoos = payload.get("shmoos", {})
    per_unit: Dict[str, int] = {}
    vmin_status: Dict[str, int] = {}
    total = 0

    if isinstance(shmoos, dict):
        for visual_id, entries in shmoos.items():
            if not isinstance(entries, list):
                continue
            per_unit.setdefault(str(visual_id), 0)
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                total += 1
                per_unit[str(visual_id)] += 1
                status = str(entry.get("vmin_status") or "unknown").lower()
                vmin_status[status] = vmin_status.get(status, 0) + 1

    visual_count = len(per_unit)
    return per_unit, vmin_status, total, visual_count


def collect_high_units(payload: Dict[str, Any]) -> Dict[str, int]:
    shmoos = payload.get("shmoos", {})
    by_unit: Dict[str, int] = {}

    if not isinstance(shmoos, dict):
        return by_unit

    for visual_id, entries in shmoos.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("vmin_status") or "").lower() == "high":
                key = str(visual_id)
                by_unit[key] = by_unit.get(key, 0) + 1

    return by_unit


def to_html_list(items: List[str]) -> str:
    if not items:
        return "<p>None</p>"
    li = "".join(f"<li>{item}</li>" for item in items)
    return f"<ul>{li}</ul>"


def build_html_summary(
    title: str,
    notebook_name: str,
    parsed_json: Path,
    html_report: Path,
    files_scanned: Any,
    files_with_shmoo: Any,
    total_shmoos: int,
    visual_count: int,
    high_units: Dict[str, int],
    vmin_status: Dict[str, int],
) -> str:
    high_lines = [f"{unit}: {count}" for unit, count in sorted(high_units.items())]
    status_lines = [f"{k}: {v}" for k, v in sorted(vmin_status.items())]

    return (
        "<html><body>"
        f"<h1>{title}</h1>"
        f"<p><b>Notebook:</b> {notebook_name}</p>"
        "<h2>Input and Output</h2>"
        f"<p><b>Parsed JSON:</b> {parsed_json}</p>"
        f"<p><b>High Vmin HTML Report:</b> {html_report}</p>"
        "<h2>Analysis Summary</h2>"
        f"<p><b>Files scanned:</b> {files_scanned}</p>"
        f"<p><b>Files with shmoo:</b> {files_with_shmoo}</p>"
        f"<p><b>Total shmoos:</b> {total_shmoos}</p>"
        f"<p><b>Visual IDs:</b> {visual_count}</p>"
        "<h2>High Vmin Units</h2>"
        f"{to_html_list(high_lines)}"
        "<h2>Vmin Status Distribution</h2>"
        f"{to_html_list(status_lines)}"
        "</body></html>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build OneNote summary payload from shmoo analysis output.")
    parser.add_argument("input_json", help="Path to enriched shmoo_parsed.json")
    parser.add_argument("--html-report", required=True, help="Path to generated high-vmin HTML report")
    parser.add_argument("--notebook", required=True, help="Target OneNote notebook display name")
    parser.add_argument("--title", default="", help="Optional explicit OneNote page title")
    parser.add_argument("-o", "--output", default="onenote_report_payload.json", help="Output payload JSON path")
    args = parser.parse_args()

    input_json = Path(args.input_json)
    html_report = Path(args.html_report)
    output = Path(args.output)

    if not input_json.exists():
        raise FileNotFoundError(f"Not found: {input_json}")

    payload = load_json(input_json)
    per_unit, vmin_status, total_shmoos, visual_count = collect_stats(payload)
    high_units = collect_high_units(payload)

    date_title = dt.date.today().isoformat()
    title = args.title.strip() or f"{date_title} - High Vmin Summary"

    html_body = build_html_summary(
        title=title,
        notebook_name=args.notebook,
        parsed_json=input_json,
        html_report=html_report,
        files_scanned=payload.get("files_scanned"),
        files_with_shmoo=payload.get("files_with_shmoo"),
        total_shmoos=total_shmoos,
        visual_count=visual_count,
        high_units=high_units,
        vmin_status=vmin_status,
    )

    result = {
        "title": title,
        "notebook": args.notebook,
        "source_json": str(input_json),
        "html_report": str(html_report),
        "counts": {
            "files_scanned": payload.get("files_scanned"),
            "files_with_shmoo": payload.get("files_with_shmoo"),
            "total_shmoos": total_shmoos,
            "visual_ids": visual_count,
            "high_vmin_entries": sum(high_units.values()),
        },
        "high_vmin_units": [
            {"visual_id": unit, "high_count": count}
            for unit, count in sorted(high_units.items())
        ],
        "vmin_status": dict(sorted(vmin_status.items())),
        "per_visual_id": dict(sorted(per_unit.items())),
        "onenote": {
            "title": title,
            "content_type": "text/html",
            "html": html_body,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Payload written: {output}")
    print(f"Title: {title}")
    print(f"High-vmin units: {len(high_units)}")
    print(f"High-vmin entries: {sum(high_units.values())}")


if __name__ == "__main__":
    main()
