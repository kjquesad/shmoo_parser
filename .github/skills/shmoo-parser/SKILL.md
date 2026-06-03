---
name: shmoo-parser
description: "Parse post silicon shmoo console/log data from a file or folder using shmoo_parser.py. Use when user asks to extract shmoos, parse a path, or build shmoo_parsed.json. Reuse existing shmoo_parsed.json if present."
argument-hint: "Provide input path to file/folder containing shmoo logs"
user-invocable: true
---

# Shmoo Parser Skill

Use this skill to parse shmoo data and create or reuse `shmoo_parsed.json`.

## When to Use
- User asks to parse shmoo data from a file/folder.
- User asks to extract shmoos from logs/console output.
- User asks for shmoo summary stats from a path.

## Workflow
1. Resolve user input path.
2. If input is a folder, check whether `shmoo_parsed.json` already exists in that folder.
3. If `shmoo_parsed.json` exists and user did not ask to re-parse, reuse it.
4. Otherwise run parser:
   - `python shmoo_parser.py <input_path> -o <output_json_path>`
5. Read the generated/reused JSON and summarize:
   - files scanned
   - files with shmoo
   - total shmoos
   - visual IDs found
   - shmoos per visual ID
   - vmin_found availability per shmoo entry

## Parsed Output Notes
- Each shmoo entry includes `vmin_found` after `plist`.
- `vmin_found` is computed by checking the center column of `failing_data.rows` from low Y to high Y and taking the first passing point (`*`).
- If no passing point is found in the center column, `vmin_found` is `null`.

## Command Pattern
```powershell
python shmoo_parser.py "<input_path>" -o "<output_folder>\shmoo_parsed.json"
```

## Analysis Requirements
After parsing, always report:
- Files scanned count
- Files with shmoo count
- Total shmoo count
- Unique visual IDs
- Per-unit shmoo counts
