# Shmoo Parser and Report Generator

Parse post-silicon shmoo data from console/log files, generate an interactive HTML visualization report, and build team-filtered email report text.

## Quick Start for Common Paths

Use these commands as-is for the two datasets commonly used in this repo.

### Dataset A: ituff_CORE_MV

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "I:/engineering/dev/dcd/scan/jgsalaza/ituff_CORE_MV" -o "I:/engineering/dev/dcd/scan/jgsalaza/ituff_CORE_MV/shmoo_parsed.json"
python .github/skills/shmoo-html-report/scripts/html_report.py "I:/engineering/dev/dcd/scan/jgsalaza/ituff_CORE_MV/shmoo_parsed.json" -o "I:/engineering/dev/dcd/scan/jgsalaza/ituff_CORE_MV/shmoo_report.html"
```

### Dataset B: test_small

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "I:/engineering/dev/dcd/scan/kjquesad/tools/shmoo_parser/test_small" -o "I:/engineering/dev/dcd/scan/kjquesad/tools/shmoo_parser/test_small/shmoo_parsed.json"
python .github/skills/shmoo-html-report/scripts/html_report.py "I:/engineering/dev/dcd/scan/kjquesad/tools/shmoo_parser/test_small/shmoo_parsed.json" -o "I:/engineering/dev/dcd/scan/kjquesad/tools/shmoo_parser/test_small/shmoo_report.html"
```

Open the generated `shmoo_report.html` file in your browser.

## What This Repository Does

This repo provides a complete workflow for shmoo analysis:

1. Parse raw logs into structured JSON (`shmoo_parsed.json`).
2. Build an interactive HTML report (`shmoo_report.html`) from that JSON.
3. Build filtered subset HTML reports for requests like "show me 5 shmoos".
4. Classify shmoo shapes (`shmoo_classified.json`) from parsed JSON.
5. Compare `vmin_found` against expected Vmin database and tag high Vmin entries.
6. Build a team-filtered email report text (`shmoo_email_report.txt`) from that JSON.
7. Support both direct script usage and guided usage via the `@shmoo-analyzer` agent mode.

## Repository Structure

- `.github/skills/shmoo-parser/scripts/shmoo_parser.py`
- `.github/skills/shmoo-classifier/scripts/shmoo_classifier.py`
- `.github/skills/vmin_detector/scripts/vmin_detector.py`
- `.github/skills/shmoo-html-report/scripts/html_report.py`
- `.github/skills/shmoo-email-report/scripts/email_report.py`
- `.github/skills/shmoo-parser/SKILL.md`
- `.github/skills/shmoo-html-report/SKILL.md`
- `.github/skills/shmoo-email-report/SKILL.md`
- `.github/skills/bring_vpo_class_data/SKILL.md`
- `.github/skills/bring_vpo_sort_data/SKILL.md`
- `.github/agents/shmoo-analyzer.agent.md`
- `Shmoo_Overview.pdf`

## Capabilities

- Parse supported file types: `.txt`, `.log`, `.itf`, `.ittuf`, `.ituff`
- Parse shmoo sections from:
- ShmooHub-style tokens
- ECADS Plot3 sections
- Extract and normalize key fields:
- Visual ID
- Die ID
- Instance name
- Team
- PList
- Axis ranges and step sizes
- Axis labels (`xlabel`, `ylabel`)
- Failure legends and row data
- Generate HTML report with:
- Team/unit filtering
- Search
- Per-shmoo metadata panel
- Grid visualization of pass/fail symbols
- Legend table
- Inverted Y-axis rendering (low at bottom, high at top)
- Long Y-label summarization for multi-variable lists in display only (JSON remains full-fidelity)
- Generate email report text grouped by unit with:
- Team filtering
- PList and Die per shmoo
- Shmoo data rows
- Legends

## Show Me X Shmoos (HTML Subset)

Use `html_report.py` filters to generate a report for only the requested shmoo subset.

Command examples:

```powershell
python .github/skills/shmoo-html-report/scripts/html_report.py "<input_json>" -o "<output_html>" --limit 5
python .github/skills/shmoo-html-report/scripts/html_report.py "<input_json>" -o "<output_html>" --limit 10 --team "SCN"
python .github/skills/shmoo-html-report/scripts/html_report.py "<input_json>" -o "<output_html>" --vmin-status high --limit 20
```

## Vmin Detector

Use `vmin_detector.py` to compare shmoo `vmin_found` values against an expected Vmin JSON database and rewrite `vmin_found` as tagged text:

- `Vmin Found: <value>`
- `Vmin Found (High): <value>` when found Vmin is higher than expected.

It also adds trace fields such as `vmin_status`, `vmin_expected_mv`, `vmin_found_mv`, and `vmin_delta_mv`.

Command example:

```powershell
python .github/skills/vmin_detector/scripts/vmin_detector.py "<input_shmoo_json>" "<expected_vmin_json>" -o "<output_json>" --plist "<optional_plist_filter>" --visual-id "<optional_visual_id_filter>"
```

## Axis Label Behavior

Axis labels are extracted during parsing.

ShmooHub example:

`0_strgval_TIMING:bck_param^9E-09^1.1E-08^0.1E-9^VOLTAGE:VCCINF^0.5^0.94^0.02_ShmooHub`

- X label -> `TIMING:bck_param`
- Y label -> `VOLTAGE:VCCINF`

ECADS example:

- `0_comnt_PLOT_PXName,Rcomp` -> X label `Rcomp`
- `0_comnt_PLOT_PYName,y` -> Y label `y`

If a Y label contains a very long comma-separated variable list (for example many `VCORE_Ux_CyRz_*` tokens), the HTML report displays a summarized grouped label (for readability), while the JSON keeps the full original string.

## Requirements

- Python 3.9+ (standard library only)
- Windows PowerShell examples are provided below, but scripts are plain Python and work cross-platform.

## Quick Start

### 1) Parse shmoo data into JSON

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_file_or_folder>" -o "<output_folder>/shmoo_parsed.json"
```

Optional recursive scan:

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_folder>" -o "<output_folder>/shmoo_parsed.json" -r
```

### 2) Generate HTML report from JSON

```powershell
python .github/skills/shmoo-html-report/scripts/html_report.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_report.html"
```

Optional filter to one visual ID:

```powershell
python .github/skills/shmoo-html-report/scripts/html_report.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_report.html" --visual-id "<VISUAL_ID>"
```

Optional subset filters:

```powershell
python .github/skills/shmoo-html-report/scripts/html_report.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_report_subset.html" --limit 5 --team "SCN" --search "group8" --vmin-status high
```

### 3) Open the report

Open `shmoo_report.html` in your browser.

### 4) Generate team email report text

```powershell
python .github/skills/shmoo-email-report/scripts/email_report.py "<output_folder>/shmoo_parsed.json" --team "<TEAM>" --email "<recipient@company.com>" -o "<output_folder>/shmoo_email_report.txt"
```

If `--team` or `--email` is omitted, the script prompts for the missing value(s) and does not proceed until both are provided.

## Typical Output Files

- `shmoo_parsed.json`
- `shmoo_report.html`
- `shmoo_email_report.txt`

## JSON Output Shape (High Level)

Top-level metadata:

- `generated_utc`
- `path_folder`
- `recursive`
- `files_scanned`
- `files_with_shmoo`
- `total_shmoos`
- `shmoos`

Each shmoo entry includes fields such as:

- `visual_id`
- `instance`
- `team`
- `plist`
- `die_id`
- `axis`
- `axis.xstart`, `axis.xstop`, `axis.xstep`
- `axis.ystart`, `axis.ystop`, `axis.ystep`
- `axis.xlabel`, `axis.ylabel`
- `legends`
- `failing_data` (including row data and fail points)

## Agent Workflow (`@shmoo-analyzer`)

The agent is configured to:

1. Read parser/report/email skills at start.
2. Reuse `shmoo_parsed.json` when present (unless explicitly asked to re-parse).
3. Parse first when JSON is missing.
4. Generate HTML report when visualization is requested.
5. Generate email report text when email output is requested.
6. Ask for `email` and `team` if missing before generating email report.
7. Return required summary metrics:
- files scanned
- files with shmoo
- total shmoos
- visual IDs
- shmoo count per visual ID
- input/output report paths

## Common Commands

Parse folder and generate report in place:

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "I:/path/to/data" -o "I:/path/to/data/shmoo_parsed.json"
python .github/skills/shmoo-html-report/scripts/html_report.py "I:/path/to/data/shmoo_parsed.json" -o "I:/path/to/data/shmoo_report.html"
python .github/skills/shmoo-email-report/scripts/email_report.py "I:/path/to/data/shmoo_parsed.json" --team "SCN_SCAN" --email "recipient@company.com" -o "I:/path/to/data/shmoo_email_report.txt"
```

## Troubleshooting

- If parsing appears slow, check file sizes and network-drive latency.
- If report generation succeeds but content is outdated, re-run parser and then regenerate HTML.
- If no shmoos are found, verify that input files actually contain ShmooHub or ECADS Plot3 sections.

## Notes

- JSON is intentionally full-fidelity for downstream analysis.
- Some display logic in HTML is intentionally summarized for readability (for example long Y-axis label lists).
