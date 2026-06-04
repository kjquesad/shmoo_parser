---
name: shmoo-parser
description: "Parse post silicon shmoo console/log data from a file or folder and enrich with classification and vmin tags. Runs shmoo_parser.py, shmoo_classifier.py, and vmin_detector.py. Final output is shmoo_parsed.json."
argument-hint: "Provide input path to file/folder containing shmoo logs"
user-invocable: true
---

# Shmoo Parser Skill

Use this skill to parse shmoo data and produce enriched `shmoo_parsed.json`.

## When to Use
- User asks to parse shmoo data from a file/folder.
- User asks to extract shmoos from logs/console output.
- User asks for shmoo summary stats from a path.

## Workflow
1. Resolve user input path.
2. Resolve optional team filter from user request:
   - Examples: `SCN`, `SCN CBB`, `SCN IMH`.
   - If provided, pass it through `--team-filter` so output JSON contains only matching entries.
3. Resolve output folder from input path.
4. Resolve expected-vmin database path:
   - Prefer `.github/skills/vmin_detector/vmin_expected.json`.
   - If user provides a different path, use user-provided path.
   - If the default file is missing, ask user for expected-vmin JSON path before continuing.
5. Run parser:
   - `python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_path>" -o "<output_folder>/shmoo_parsed.json" [--team-filter "<filter_text>"]`
6. Run classifier and overwrite the same parse file:
   - `python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_parsed.json"`
7. Run vmin detector and overwrite the same parse file:
   - `python .github/skills/vmin_detector/scripts/vmin_detector.py "<output_folder>/shmoo_parsed.json" "<expected_vmin_json>" -o "<output_folder>/shmoo_parsed.json"`
8. Read the generated JSON and summarize:
   - files scanned
   - files with shmoo
   - total shmoos
   - visual IDs found
   - shmoos per visual ID
   - classification distribution
   - vmin high/ok/missing/no-match counts

## Parsed Output Notes
- Each shmoo entry includes `vmin_found` after `plist`.
- `vmin_found` is computed by checking the center column of `failing_data.rows` from low Y to high Y and taking the first passing point (`*`).
- If no passing point is found in the center column, `vmin_found` is `null`.
- Classifier injects `classification` into each entry.
- Vmin detector injects `vmin_status`, `vmin_expected_mv`, `vmin_found_mv`, and `vmin_delta_mv`.
- Final enriched data is saved as `shmoo_parsed.json`.

## Command Pattern
```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_path>" -o "<output_folder>\shmoo_parsed.json"
python .github/skills/shmoo-classifier/scripts/shmoo_classifier.py "<output_folder>\shmoo_parsed.json" -o "<output_folder>\shmoo_parsed.json"
python .github/skills/vmin_detector/scripts/vmin_detector.py "<output_folder>\shmoo_parsed.json" ".github/skills/vmin_detector/vmin_expected.json" -o "<output_folder>\shmoo_parsed.json"
```

Filter example:

```powershell
python .github/skills/shmoo-parser/scripts/shmoo_parser.py "<input_path>" -o "<output_folder>\shmoo_parsed.json" --team-filter "SCN IMH"
```

## Analysis Requirements
After parsing, always report:
- Files scanned count
- Files with shmoo count
- Total shmoo count
- Unique visual IDs
- Per-unit shmoo counts
- Classification summary
- Vmin status summary (`high`, `ok`, `missing_found`, `no_expected_match`)
