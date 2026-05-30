"""Generate a team-filtered plain-text email report from shmoo_parsed.json."""

import argparse
import html
import json
import platform
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def load_shmoo_data(json_path: Path) -> Dict[str, Any]:
    """Load and return parsed shmoo JSON."""
    return json.loads(json_path.read_text(encoding="utf-8"))


def flatten_entries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize both supported shmoo JSON shapes into a flat list."""
    shmoos = payload.get("shmoos", {})
    result: List[Dict[str, Any]] = []

    if not isinstance(shmoos, dict):
        return result

    for key, value in shmoos.items():
        # Shape A: visual_id -> [entries]
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                normalized = dict(entry)
                normalized.setdefault("visual_id", key)
                normalized.setdefault("source_file", "")
                result.append(normalized)
            continue

        # Shape B: source -> visual_id -> [entries]
        if isinstance(value, dict):
            source_file = key
            for visual_id, entries in value.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    normalized = dict(entry)
                    normalized.setdefault("visual_id", visual_id)
                    normalized.setdefault("source_file", source_file)
                    result.append(normalized)

    return result


def infer_team(instance: str) -> str:
    """Fallback inference if team is missing in JSON."""
    if not instance:
        return "UNKNOWN"
    if "_COMP::" in instance:
        return instance.split("_COMP::", 1)[0]
    if "::" in instance:
        return instance.split("::", 1)[0]
    prefixes = ["SCN_SCAN", "SIO_BSCAN", "TATPG", "RESET_COMP", "DV", "PCS"]
    for prefix in prefixes:
        if instance.startswith(prefix):
            return prefix
    return "UNKNOWN"


def normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return only fields needed by the email report."""
    failing_data = entry.get("failing_data") if isinstance(entry.get("failing_data"), dict) else {}
    instance = entry.get("instance") or ""
    team = entry.get("team") or infer_team(instance)

    return {
        "visual_id": entry.get("visual_id") or "NO_VISUAL_ID",
        "team": str(team),
        "plist": entry.get("plist") or "UNKNOWN_PLIST",
        "die_id": entry.get("die_id") or "N/A",
        "rows": failing_data.get("rows") if isinstance(failing_data.get("rows"), list) else [],
        "legends": entry.get("legends") if isinstance(entry.get("legends"), dict) else {},
    }


def filter_by_team(entries: List[Dict[str, Any]], team: str) -> List[Dict[str, Any]]:
    """Filter shmoo entries by team name (case-insensitive)."""
    wanted = team.strip().lower()
    if not wanted:
        return []
    return [e for e in entries if str(e.get("team", "")).strip().lower() == wanted]


def format_rows(rows: List[Any]) -> List[str]:
    """Return shmoo row lines."""
    if not rows:
        return ["    (no shmoo rows available)"]
    return [f"    {str(row)}" for row in rows]


def format_legends(legends: Dict[str, Any]) -> List[str]:
    """Return legend lines with stable ordering."""
    if not legends:
        return ["    (no legends available)"]

    lines: List[str] = []
    for key in sorted(legends.keys(), key=lambda k: str(k)):
        value = str(legends[key])
        value_lines = value.splitlines() or [value]
        if len(value_lines) == 1:
            lines.append(f"    {key}: {value_lines[0]}")
            continue
        lines.append(f"    {key}:")
        for vline in value_lines:
            lines.append(f"      {vline}")
    return lines


def build_email_body(team: str, entries: List[Dict[str, Any]]) -> str:
    """Build the plain-text email body grouped by unit."""
    units: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        units[str(entry.get("visual_id") or "NO_VISUAL_ID")].append(entry)

    lines: List[str] = []
    lines.append(f"Hello,\nBelow is the shmoo report for team {team}.\n")

    if not units:
        lines.append("No shmoos matched the requested team filter.")
        lines.append("")
        lines.append("Regards,")
        lines.append("Shmoo Analyzer")
        return "\n".join(lines)

    for unit in sorted(units.keys()):
        lines.append(f"Unit: {unit}")
        for idx, shmoo in enumerate(units[unit], start=1):
            lines.append(f"- Shmoo {idx}")
            lines.append(f"  PList: {shmoo.get('plist', 'UNKNOWN_PLIST')}")
            lines.append(f"  Die: {shmoo.get('die_id', 'N/A')}")
            lines.append("  Shmoo Data:")
            lines.extend(format_rows(shmoo.get("rows", [])))
            lines.append("  Legends:")
            lines.extend(format_legends(shmoo.get("legends", {})))
        lines.append("")

    lines.append("Regards,")
    lines.append("Shmoo Analyzer")
    return "\n".join(lines)


def symbol_color(symbol: str) -> str:
    """Return a deterministic color for each failing symbol."""
    if symbol == "*":
        return "#c8f7c5"

    palette = [
        "#e63946",
        "#ff7f11",
        "#ffbe0b",
        "#06d6a0",
        "#118ab2",
        "#3a86ff",
        "#8338ec",
        "#ef476f",
        "#2a9d8f",
        "#f4a261",
        "#457b9d",
        "#bc6c25",
    ]
    idx = ord(symbol[0]) % len(palette)
    return palette[idx]


def rows_to_html_grid(rows: List[Any]) -> str:
    """Render shmoo rows as an HTML table grid."""
    if not rows:
        return '<div class="empty">No shmoo rows available.</div>'

    row_strings = [str(row) for row in rows]
    max_cols = max(len(r) for r in row_strings)

    out: List[str] = []
    out.append('<table class="grid">')
    for row in row_strings:
        out.append("<tr>")
        for col in range(max_cols):
            symbol = row[col] if col < len(row) else " "
            if symbol == " ":
                out.append('<td class="empty-cell"></td>')
                continue

            color = symbol_color(symbol)
            text_color = "#111111" if symbol == "*" else "#ffffff"
            out.append(
                f'<td style="background:{color};color:{text_color}">{html.escape(symbol)}</td>'
            )
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def legends_to_html_table(legends: Dict[str, Any]) -> str:
    """Render legends as an HTML table."""
    if not legends:
        return '<div class="empty">No legends available.</div>'

    out: List[str] = []
    out.append('<table class="legend">')
    out.append("<tr><th>Symbol</th><th>Details</th></tr>")
    for key in sorted(legends.keys(), key=lambda k: str(k)):
        value = html.escape(str(legends[key])).replace("\n", "<br>")
        out.append(
            "<tr>"
            f'<td class="sym" style="background:{symbol_color(str(key))};">{html.escape(str(key))}</td>'
            f"<td>{value}</td>"
            "</tr>"
        )
    out.append("</table>")
    return "".join(out)


def build_email_html(team: str, entries: List[Dict[str, Any]]) -> str:
    """Build an HTML email body with visual shmoo sections."""
    units: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        units[str(entry.get("visual_id") or "NO_VISUAL_ID")].append(entry)

    parts: List[str] = []
    parts.append(
        """
<!DOCTYPE html>
<html>
<head>
<meta charset=\"utf-8\" />
<style>
body{font-family:Segoe UI,Arial,sans-serif;color:#1f2937;background:#f5f7fb;margin:0;padding:0}
.wrap{padding:16px}
.title{font-size:20px;font-weight:700;margin-bottom:6px}
.sub{color:#4b5563;margin-bottom:14px}
.unit{background:#ffffff;border:1px solid #dbe3ee;border-radius:10px;margin-bottom:14px;padding:12px}
.unit h2{font-size:16px;margin:0 0 8px 0}
.shmoo{border:1px solid #e5ebf3;border-radius:8px;padding:10px;margin-bottom:10px;background:#fbfdff}
.meta{font-size:13px;color:#374151;margin-bottom:8px}
.meta div{margin:2px 0}
.grid{border-collapse:collapse;margin-bottom:10px}
.grid td{width:16px;height:16px;border:1px solid #d1d9e6;text-align:center;font-family:Consolas,monospace;font-size:11px;padding:0}
.grid td.empty-cell{background:#ffffff;border:none}
.legend{border-collapse:collapse;width:100%;table-layout:fixed}
.legend th,.legend td{border:1px solid #d1d9e6;padding:6px 8px;font-size:12px;vertical-align:top;word-break:break-word}
.legend th{background:#eef3fb;text-align:left}
.legend .sym{text-align:center;color:#ffffff;font-weight:700;width:56px}
.empty{color:#6b7280;font-size:12px;font-style:italic;margin-bottom:8px}
</style>
</head>
<body>
<div class=\"wrap\">"""
    )

    parts.append(f'<div class="title">Shmoo Report - Team {html.escape(team)}</div>')
    parts.append(f'<div class="sub">Matching shmoos: {len(entries)}</div>')

    if not units:
        parts.append('<div class="unit"><div class="empty">No shmoos matched the requested team filter.</div></div>')
    else:
        for unit in sorted(units.keys()):
            parts.append(f'<div class="unit"><h2>Unit: {html.escape(unit)}</h2>')
            for idx, shmoo in enumerate(units[unit], start=1):
                parts.append('<div class="shmoo">')
                parts.append(
                    '<div class="meta">'
                    f"<div><strong>Shmoo:</strong> {idx}</div>"
                    f"<div><strong>PList:</strong> {html.escape(str(shmoo.get('plist', 'UNKNOWN_PLIST')))}</div>"
                    f"<div><strong>Die:</strong> {html.escape(str(shmoo.get('die_id', 'N/A')))}</div>"
                    "</div>"
                )
                parts.append(rows_to_html_grid(shmoo.get("rows", [])))
                parts.append(legends_to_html_table(shmoo.get("legends", {})))
                parts.append("</div>")
            parts.append("</div>")

    parts.append("</div></body></html>")
    return "".join(parts)


def build_report_text(email: str, subject: str, body: str) -> str:
    """Build the saved report text with message headers."""
    lines = [f"To: {email}", f"Subject: {subject}", "", body]
    return "\n".join(lines)


def build_report_html(email: str, subject: str, body_html: str) -> str:
    """Build an HTML report file wrapper with message headers."""
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\" /></head><body>"
        f"<div><strong>To:</strong> {html.escape(email)}</div>"
        f"<div><strong>Subject:</strong> {html.escape(subject)}</div>"
        "<hr />"
        f"{body_html}"
        "</body></html>"
    )


def send_via_outlook(
    email: str,
    subject: str,
    body_text: str,
    body_html: str,
    action: str,
    email_format: str,
) -> None:
    """Send or display an Outlook email using COM automation on Windows."""
    if action == "none":
        return

    if platform.system().lower() != "windows":
        raise RuntimeError("Outlook automation is only supported on Windows.")

    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "pywin32 is required for Outlook integration. Install with: pip install pywin32"
        ) from exc

    outlook = win32com.client.Dispatch("Outlook.Application")
    message = outlook.CreateItem(0)
    message.To = email
    message.Subject = subject
    if email_format == "html":
        message.HTMLBody = body_html
    else:
        message.Body = body_text

    if action == "display":
        message.Display()
        return

    message.Send()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a team-filtered email report from shmoo_parsed.json"
    )
    parser.add_argument("input_json", type=Path, help="Path to shmoo_parsed.json")
    parser.add_argument("--team", required=False, help="Team name for filtering")
    parser.add_argument("--email", required=False, help="Recipient email")
    parser.add_argument(
        "--subject",
        default=None,
        help="Optional email subject. Default: Shmoo Report - Team <TEAM>",
    )
    parser.add_argument(
        "--outlook-action",
        choices=["none", "display", "send"],
        default="none",
        help="none=generate text only, display=open Outlook draft, send=send email via Outlook",
    )
    parser.add_argument(
        "--email-format",
        choices=["text", "html"],
        default="html",
        help="Email body format for report output and Outlook message",
    )
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output .txt path")
    return parser.parse_args()


def prompt_if_missing(value: str, prompt_text: str) -> str:
    """Prompt user for required value if CLI argument is missing."""
    if value and value.strip():
        return value.strip()
    while True:
        entered = input(prompt_text).strip()
        if entered:
            return entered


def main() -> None:
    args = parse_args()

    if not args.input_json.exists():
        raise FileNotFoundError(f"Input JSON not found: {args.input_json}")

    team = prompt_if_missing(args.team or "", "Enter team for shmoo filter: ")
    email = prompt_if_missing(args.email or "", "Enter recipient email: ")
    subject = args.subject or f"Shmoo Report - Team {team}"

    payload = load_shmoo_data(args.input_json)
    entries = [normalize_entry(e) for e in flatten_entries(payload)]
    filtered_entries = filter_by_team(entries, team)

    body_text = build_email_body(team=team, entries=filtered_entries)
    body_html = build_email_html(team=team, entries=filtered_entries)
    report_text = build_report_text(email=email, subject=subject, body=body_text)
    report_html = build_report_html(email=email, subject=subject, body_html=body_html)

    output_path = args.output
    if output_path is None:
        ext = "html" if args.email_format == "html" else "txt"
        output_path = args.input_json.parent / f"shmoo_email_report.{ext}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.email_format == "html":
        output_path.write_text(report_html, encoding="utf-8")
    else:
        output_path.write_text(report_text, encoding="utf-8")

    send_via_outlook(
        email=email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        action=args.outlook_action,
        email_format=args.email_format,
    )

    print(f"Generated email report: {output_path}")
    print(f"Team filter: {team}")
    print(f"Recipient: {email}")
    print(f"Matching shmoos: {len(filtered_entries)}")
    print(f"Email format: {args.email_format}")
    print(f"Outlook action: {args.outlook_action}")


if __name__ == "__main__":
    main()