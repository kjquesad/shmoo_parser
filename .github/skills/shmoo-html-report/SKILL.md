---
name: shmoo-html-report
description: "Create shmoo visualization HTML report from shmoo_parsed.json using html_report.py. Use when user asks to visualize shmoos, show shmoos, show me x shmoos, or generate/create an HTML report."
argument-hint: "Provide path to shmoo_parsed.json"
user-invocable: true
---

# Shmoo HTML Report Skill

Use this skill whenever user asks to visualize shmoo data.

## When to Use
- "show me the shmoos"
- "show me 3 shmoos"
- "display 3 shmoos"
- "i want to visualiz 3 smoos"
- "create html report"
- "visualize shmoo"
- "generate report from shmoo_parsed.json"
- Combined prompts such as: "Do a full analisys for this data ... Show me the units with high vmin"

## Natural Language Mapping
- Treat these as equivalent display intent: `show`, `display`, `visualize`, `visualiz`.
- Treat these as equivalent target terms: `shmoo`, `shmoos`, `smoo`, `smoos`.
- Extract first integer in user phrase as `N` and map to `--limit N`.
- If display intent is present but `N` is missing, default to `--limit 5`.
- For display intents, output must always be graph-style (shmoo grid/table in HTML), not metadata-only text.
- Examples:
   - "show me 7 shmoos" -> `--limit 7`
   - "display 10 smoos" -> `--limit 10`
   - "i want to visualiz shmoos" -> `--limit 5`

## Workflow
1. Resolve JSON input path.
2. If JSON path is missing, first run the `shmoo-parser` skill.
   - If prompt includes full analysis intent, run parser workflow even when prior JSON exists so results are fresh for that input path.
3. Infer subset filters from user wording when present.
   - Number in phrase (example: "show me 5 shmoos") -> `--limit 5`
   - Team qualifier (example: "SCN only") -> `--team "SCN"`
   - Vmin qualifier (example: "high vmin") -> `--vmin-status high`
   - Additional text qualifier -> `--search "<text>"`
4. Run the report generator:
   - `python html_report.py <input_json> -o <output_html> [filters]`
5. The generated report always auto-opens in the default browser.
6. Return summary with:
   - input JSON path
   - output HTML path
   - total shmoos
   - visual ID count
   - applied filter summary
   - high-vmin unit list when `--vmin-status high` is used

## Command Pattern
```powershell
python html_report.py "<input_json>" -o "<output_html>" --limit 5 --team "SCN" --search "group8" --vmin-status high
```

Combined intent example:

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_path>" -o "<output_folder>/shmoo_parsed.json"
python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_parsed.json"
python .github/skills/vmin_detector/scripts/vmin_detector.py "<output_folder>/shmoo_parsed.json" ".github/skills/vmin_detector/vmin_expected.json" -o "<output_folder>/shmoo_parsed.json"
python .github/skills/shmoo-html-report/scripts/html_report.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_report_high_vmin.html" --vmin-status high
```

## Supported Subset Filters
- `--limit <N>`: include only first N filtered shmoos
- `--visual-id <VID>`: keep one visual ID
- `--team <TEAM>`: exact team filter
- `--plist <TEXT>`: substring match on plist
- `--search <TEXT>`: free-text match across key fields
- `--vmin-status <STATUS>`: one of `high`, `ok`, `missing_found`, `no_expected_match`, `unknown`

## Browser Behavior
- Reports always attempt to open in the default browser after generation.

## Default Output Naming
- If input is `<folder>\shmoo_parsed.json`, output should be `<folder>\shmoo_report.html` unless user specifies otherwise.
