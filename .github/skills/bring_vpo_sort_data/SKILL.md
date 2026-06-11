---
name: bring_vpo_sort_data
description: "Fetch SORT scan data from X:/datalogs/1276/eng, prefer wafer zip packages when present, otherwise copy/decompress .gz scans, and build parsing_runs/<MV>/<WAFER>/ outputs."
argument-hint: "Provide MV number (example: 43DDS0T00), location (example: 132322), and optional wafer (example: 668)"
user-invocable: true
---

# Bring VPO Sort Data Skill

Use this skill when the user wants SORT scan data from the 1276 ENG datalogs tree.

## When to Use
- User asks to bring/fetch/copy SORT data.
- User provides MV + location and wants wafer-organized local data.
- Source path is under `X:/datalogs/1276/eng`.

## Source Layout
- Root: `X:/datalogs/1276/eng`
- Folder pattern: `<MV>_<LOCATION>/Scan/<WAFER>/`
- Example:
  - `X:/datalogs/1276/eng/43DDS0T00_132322/Scan/668`

## Input Rules
- Required: MV (example `43DDS0T00`)
- Required: location (example `132322`)
- Optional: wafer (single wafer). If omitted, process all wafer folders under `Scan`.
- Optional: output dir override.

If default root or resolved source folder is not accessible/found:
1. Ask the user for an alternate input path that contains SORT scan data.
2. Use the user-provided path as source scan folder.
3. If wafer folders or expected zip/gz inputs are still missing, report that clearly and stop.

## ZIP-First Rule
For each wafer folder:
1. Check for zip file(s) matching `I<MV>__<LOCATION>.W<WAFER>R*.zip`.
2. If found, copy only the selected zip file to local wafer folder, extract it, and delete the copied zip.
  - Normalize extracted primary scan files to include `.itf` extension.
3. If not found, copy `.gz` files from wafer folder, merge decompressed content into one `.itf`, then delete copied `.gz` files.

## Default Destination
- `parsing_runs/<MV>/<WAFER>/`

## Workflow
1. Resolve source scan folder: `X:/datalogs/1276/eng/<MV>_<LOCATION>/Scan`.
2. Resolve wafer folders (one or all).
3. For each wafer, apply ZIP-first rule.
4. Keep output organized per wafer under `parsing_runs/<MV>/`.
5. Return summary:
   - source scan folder
   - destination root
   - wafers processed
   - mode per wafer (`zip` or `gz-merged`)
   - output files/folders

## Command Pattern
```powershell
python .github/skills/bring_vpo_sort_data/scripts/bring_vpo_sort_data.py --mv "43DDS0T00" --location "132322"
```

Single wafer:

```powershell
python .github/skills/bring_vpo_sort_data/scripts/bring_vpo_sort_data.py --mv "43DDS0T00" --location "132322" --wafer "668"
```

Custom destination:

```powershell
python .github/skills/bring_vpo_sort_data/scripts/bring_vpo_sort_data.py --mv "43DDS0T00" --location "132322" --output-dir "D:/temp/parsing_runs/43DDS0T00"
```
