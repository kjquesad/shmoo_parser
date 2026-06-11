---
name: bring_vpo_class_data
description: "Fetch VPO production .gz files from I:/hdmxdata/prod, copy them locally, group by step suffix, merge each step into one .itf, and clean up .gz files."
argument-hint: "Provide VPO number (example: J623173MV), optional location (example: 6248), and optional destination folder"
user-invocable: true
---

# Bring VPO Class Data Skill

Use this skill when the user provides a VPO number and wants raw production data staged locally as merged `.itf` files.

## When to Use
- User gives a VPO id like `J623173MV`.
- User asks to bring/copy/fetch/collect production data for a VPO.
- User wants `.gz` files from `I:/hdmxdata/prod` merged by step (for example `CLASSHOT`, `CSM`).

## Input Rules
- Required: VPO number.
- Optional: location code (for example `6248`).
- Optional: destination folder.

If location is missing:
1. Search `I:/hdmxdata/prod` for folders that match `<VPO>_*`.
2. If exactly one folder exists, use it.
3. If multiple folders exist, ask the user which location to use.

If default root or resolved source folder is not accessible/found:
1. Ask the user for an alternate input path that contains the VPO data.
2. Use the user-provided path as source for `.gz` discovery and merge.
3. If still no `.gz` files are found, report that clearly and stop.

## Source Folder Convention
- Source folder format: `<VPO>_<LOCATION>`
- Example: `J623173MV_6248`
- Example path: `I:/hdmxdata/prod/J623173MV_6248`

## Default Destination
- If user does not provide output path, write to:
  - `parsing_runs/<VPO>/`

## Workflow
1. Resolve source folder from VPO + location.
2. Find all `.gz` files in that source folder.
3. Copy all `.gz` files to local destination folder.
4. Group copied files by step token (last underscore-delimited token before extension):
   - Examples:
     - `..._CLASSHOT.itf.gz` -> step `CLASSHOT`
     - `..._CSM.itf.gz` -> step `CSM`
5. For each step group:
   - Decompress every `.gz` file in sorted order.
   - Concatenate contents into one merged output file.
   - Output naming: `<VPO>_<LOCATION>_<STEP>.itf`
6. Delete copied `.gz` files from destination after merge to save disk space.
7. Return summary:
   - source folder used
   - destination folder
   - copied file count
   - number of step groups
   - output `.itf` files created

## Command Pattern
```powershell
python .github/skills/bring_vpo_class_data/scripts/bring_vpo_class_data.py --vpo "J623173MV" --location "6248"
```

With custom destination:

```powershell
python .github/skills/bring_vpo_class_data/scripts/bring_vpo_class_data.py --vpo "J623173MV" --location "6248" --output-dir "D:/temp/itf_runs/J623173MV"
```

Auto-discover location when unique:

```powershell
python .github/skills/bring_vpo_class_data/scripts/bring_vpo_class_data.py --vpo "J623173MV"
```

## Notes
- Merge is done as plain text concatenation of decompressed payloads.
- This skill only removes local copied `.gz` files in the destination folder.
- Source `.gz` files in `I:/hdmxdata/prod` are never deleted.