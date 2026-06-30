# Shmoo Parser and Report Generator

Parse post-silicon shmoo data from console/log files, classify shmoo patterns, detect high Vmin entries, generate an interactive HTML visualization report with hover pattern tooltips, and build team-filtered email report text.

## Quick Start

### Complete Analysis Workflow (Parse → Classify → Vmin Detect → Visualize)

```powershell
# 1. Parse shmoo data from logs/ITF files
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_folder>" -o "<output>/shmoo_parsed.json"

# 2. Classify shmoo patterns (red, clean, ceiling, floor, diagonal, etc.)
python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "<output>/shmoo_parsed.json" -o "<output>/shmoo_parsed.json"

# 3. Detect high Vmin and compare against expected database
python .github/skills/vmin_detector/scripts/vmin_detector.py "<output>/shmoo_parsed.json" ".github/skills/vmin_detector/vmin_expected.json" -o "<output>/shmoo_parsed.json"

# 4. Generate interactive HTML report
python .github/skills/shmoo-html-report/scripts/html_report.py "<output>/shmoo_parsed.json" -o "<output>/shmoo_report.html"
```

Open `shmoo_report.html` in your browser to explore the shmoos interactively.

### Example: test_small Dataset

```powershell
cd C:\Scripts\shmoo_parser
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "test_data\test_small" -o "test_data\test_small\shmoo_parsed.json"
python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "test_data\test_small\shmoo_parsed.json" -o "test_data\test_small\shmoo_parsed.json"
python .github/skills/vmin_detector/scripts/vmin_detector.py "test_data\test_small\shmoo_parsed.json" ".github/skills/vmin_detector/vmin_expected.json" -o "test_data\test_small\shmoo_parsed.json"
python .github/skills/shmoo-html-report/scripts/html_report.py "test_data\test_small\shmoo_parsed.json" -o "test_data\test_small\shmoo_report.html"
```
## What This Repository Does

This repo provides a complete workflow for shmoo analysis:

1. Parse raw logs into structured JSON (`shmoo_parsed.json`).
2. Classify shmoo patterns into categories (left_wall, red, clean, ceiling, floor, diagonal, etc.).
3. Compare `vmin_found` against expected Vmin database and tag high Vmin entries.
4. Build an interactive HTML report (`shmoo_report.html`) with hover tooltips, filtering, and search.
5. Build filtered subset HTML reports for specific shmoo selections.
6. Build a team-filtered email report text (`shmoo_email_report.txt`) from that JSON.
7. Support both direct script usage and guided usage via the `@shmoo-analyzer` agent mode.

## Shmoo Classification Categories

The classifier categorizes each shmoo based on its failure pattern shape:

| Category | Description | Example Pattern |
|----------|-------------|-----------------|
| **left_wall** | Failures concentrated on the left side (low voltage/timing boundary) | Most common; indicates voltage/timing margin issues |
| **right_wall** | Failures concentrated on the right side (high voltage/timing boundary) | Indicates upper bound issues |
| **floor** | Failures concentrated at the bottom (low voltage/frequency region) | Systematic low-voltage failures |
| **ceiling** | Failures concentrated at the top (high voltage/frequency region) | Indicates stress at high operating points |
| **diagonal** | Failures along a diagonal line | Suggests coupled voltage-timing dependency |
| **clean** | Very few failures or nearly perfect shmoo | Rare; indicates robust design point |
| **red** | Many scattered failures across multiple regions | Severe or multiple failure modes |
| **mixed** | Multiple distinct failure regions | Complex failure signature with multiple independent modes |
| **corner_top_left** / **corner_top_right** / **corner_bottom_left** / **corner_bottom_right** | Failures concentrated in specific corners | Indicates corner-dependent behavior (PVT corners) |
| **speckled** | Small isolated failure islands scattered throughout | Rare defects or intermittent issues |
| **crack** | Diagonal or jagged failure region | Dynamic behavior; may indicate interaction between axes |
| **island** | Isolated failure region surrounded by passes | Localized weak point |
| **slow_limit** | Failures at low frequency/voltage extremes | Timing closure issues at slow corners |
| **speed_limit** | Failures at high frequency/voltage extremes | Speed/timing issues at fast corners |

Each classification includes a **confidence score** (0-1) indicating classifier certainty.

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
- **Interactive hover tooltips** showing pattern names when hovering over any failing data point in the grid
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

## HTML Report Features

The interactive HTML report provides a comprehensive shmoo visualization experience:

### Pattern Name Tooltips
- **Hover over any failing point** in the shmoo grid to instantly see the **pattern name** in a tooltip
- Pattern name is extracted from the failure legend information
- Tooltip appears above the data point with clear visibility

### Interactive Sidebar
- Browse all shmoos organized by Visual ID
- Quick-click navigation between different units
- Color-coded tags for:
	- Team (background color)
	- Classification category (classification type: red, clean, ceiling, floor, diagonal, etc.)
	- Vmin status (high, ok, missing_found, no_expected_match)

### Filtering and Search
- Filter by team across all loaded shmoos
- Filter by classification category (red, clean, ceiling, floor, etc.)
- Filter by Vmin status (high, ok, unknown, etc.)
- Free-text search across instance names, plists, teams, classifications, and more

### Detailed Metadata Panel
- Visual ID, Die ID, Instance name
- Team and classification with confidence score
- Vmin status and comparison data (expected vs. found)
- Axis ranges and labels for both X and Y dimensions
- Source file reference

### Grid Visualization
- Color-coded pass/fail symbols
- Axis labels and calibrated ranges
- Click on any failing point to see detailed coordinates and failure info
- Pass regions marked with green (`*`)

### Legend Display
- Full failure legend table
- Maps each symbol to its pattern name and description

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

### Vmin Status Values

After running vmin_detector, each shmoo entry includes a `vmin_status` field with one of these values:

| Status | Meaning | Action |
|--------|---------|--------|
| **high** | Found Vmin is **higher** than expected nominal value | ⚠️ Investigate - may indicate marginal design or test conditions |
| **ok** | Found Vmin matches or is **lower** than expected nominal value | ✓ Acceptable - meets margin requirements |
| **missing_found** | Vmin could not be calculated from shmoo data | Review shmoo grid for data quality |
| **no_expected_match** | No expected Vmin database entry for this product/rail/frequency combo | Check database completeness |

### Example Expected Vmin Database Format

The expected Vmin JSON file maps product/rail/frequency combinations to nominal voltages:

```json
{
	"nominal": "10ns",
	"CWF": {
		"VCCFIXDIGMIO": {
			"F1": "520mV",
			"F2": "560mV",
			"F3": "600mV"
		},
		"VCORE": {
			"F1": "480mV",
			"F2": "510mV",
			"F3": "560mV"
		}
	},
	"DMR": {
		"VCCFIXDIGMIO": {
			"F1": "510mV",
			"F2": "520mV",
			"F3": "610mV"
		}
	}
}
```

### Vmin Fields Added to JSON

After vmin detection, each shmoo entry includes:

- `vmin_found`: Updated to include status tag (e.g., "Vmin Found: 0.620V" or "Vmin Found (High): 0.650V")
- `vmin_status`: One of the values above
- `vmin_expected_mv`: Expected nominal in millivolts (e.g., 620)
- `vmin_found_mv`: Measured Vmin in millivolts (e.g., 650)
- `vmin_delta_mv`: Delta (found - expected) in millivolts (e.g., +30 for high Vmin)
- `vmin_expected_rail`: Rail name (e.g., "VCCFIXDIGMIO")
- `vmin_expected_freq`: Frequency tag (e.g., "F1")

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

## Common Use Cases with Examples

### 1. Parse a Folder of Shmoo Files

```powershell
# Parse all ITF files in a folder
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "C:\data\shmoos" -o "C:\data\shmoos\shmoo_parsed.json"
```

Output: `shmoo_parsed.json` containing all extracted shmoos with raw data and metadata

### 2. Classify Shmoo Patterns

```powershell
# Classify parsed shmoos into categories
python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_parsed.json"
```

Output: Classification summary showing distribution across categories (left_wall: 68.6%, mixed: 12.7%, floor: 12.7%, etc.)

### 3. Detect High Vmin Entries

```powershell
# Compare against expected Vmin database
python .github/skills/vmin_detector/scripts/vmin_detector.py "C:\data\shmoos\shmoo_parsed.json" ".github/skills/vmin_detector/vmin_expected.json" -o "C:\data\shmoos\shmoo_parsed.json"
```

Output: JSON updated with vmin_status tags (high, ok, missing_found, no_expected_match)

### 4. Generate Full HTML Report

```powershell
# Generate interactive HTML visualization of all shmoos
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report.html"
```

Opens automatically in your browser. Features:
- Hover over grid points to see pattern names
- Filter by team, classification, vmin status
- Search for specific instances/plists
- Click grid points to see detailed coordinates

### 5. Show Me Specific Shmoos (Limited Subset)

```powershell
# Show only the first 5 shmoos
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report_5.html" --limit 5

# Show only SCN team shmoos
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report_scn.html" --team "SCN"

# Show only high Vmin units
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report_high_vmin.html" --vmin-status high

# Combine filters: show 10 high-vmin SCN shmoos
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report_filtered.html" --vmin-status high --team "SCN" --limit 10
```

### 6. Filter by PList or Search Terms

```powershell
# Show only shmoos from a specific plist
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report_plist.html" --plist "reset_Mscn"

# Search for shmoos matching pattern names or instance strings
python .github/skills/shmoo-html-report/scripts/html_report.py "C:\data\shmoos\shmoo_parsed.json" -o "C:\data\shmoos\shmoo_report_search.html" --search "IO_NORTH"
```

### 7. Generate Email Report for a Team

```powershell
# Build email-ready report text for SCN team
python .github/skills/shmoo-email-report/scripts/email_report.py "C:\data\shmoos\shmoo_parsed.json" --team "SCN" --email "team@company.com" -o "C:\data\shmoos\shmoo_email_report.txt"
```

Output: Formatted email text with unit summaries, vmin data, and classification

### 8. Full Workflow in One Script

```powershell
# Complete analysis from raw files to HTML report
$INPUT = "C:\raw_shmoo_data"
$OUTPUT = "C:\analysis_output"

# Parse
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "$INPUT" -o "$OUTPUT\shmoo_parsed.json"

# Classify
python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "$OUTPUT\shmoo_parsed.json" -o "$OUTPUT\shmoo_parsed.json"

# Detect high Vmin
python .github/skills/vmin_detector/scripts/vmin_detector.py "$OUTPUT\shmoo_parsed.json" ".github/skills/vmin_detector/vmin_expected.json" -o "$OUTPUT\shmoo_parsed.json"

# Generate reports
python .github/skills/shmoo-html-report/scripts/html_report.py "$OUTPUT\shmoo_parsed.json" -o "$OUTPUT\shmoo_report_full.html"
python .github/skills/shmoo-html-report/scripts/html_report.py "$OUTPUT\shmoo_parsed.json" -o "$OUTPUT\shmoo_report_high_vmin.html" --vmin-status high
python .github/skills/shmoo-email-report/scripts/email_report.py "$OUTPUT\shmoo_parsed.json" --team "SCN" --email "team@company.com" -o "$OUTPUT\shmoo_email_report.txt"
```

## Troubleshooting

- If parsing appears slow, check file sizes and network-drive latency.
- If report generation succeeds but content is outdated, re-run parser and then regenerate HTML.
- If no shmoos are found, verify that input files actually contain ShmooHub or ECADS Plot3 sections.
- If hover tooltips are not showing, ensure your browser supports CSS pseudo-elements (modern browsers do).
- If pattern names in tooltips appear truncated or strange, check the legend section to see the full failure info for each symbol.

## Notes

- JSON is intentionally full-fidelity for downstream analysis.
- Some display logic in HTML is intentionally summarized for readability (for example long Y-axis label lists).
