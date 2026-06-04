---
name: vmin_detector
description: "Compare shmoo vmin_found values against a user-provided expected-vmin JSON database and tag high Vmin results in output JSON. Supports optional filtering by plist and visual ID."
argument-hint: "Provide path to shmoo JSON and expected-vmin JSON"
user-invocable: true
---

# Vmin Detector Skill

Use this skill to compare shmoo Vmin results against an expected Vmin database and tag high Vmin entries.

## When to Use
- User asks to check shmoo Vmin against a nominal/expected table.
- User asks to flag high Vmin shmoos.
- User asks to compare by rail and frequency.
- User asks to process only specific `plist` or `visual_id` values.

## Input Requirements
1. Shmoo JSON path.
- Can be `shmoo_parsed.json` or `shmoo_classified.json`.
2. Expected Vmin JSON path.
- Default shared path in this repo: `.github/skills/vmin_detector/vmin_expected.json`.
- Nested product/rail/frequency maps are supported.
- Example shape:

```json
{
  "nominal": "10ns",
  "CWF": {
    "VCCFIXDIGMIO": {
      "F1": "520mV",
      "F2": "560mV",
      "F3": "600mV"
    }
  },
  "DMR": {
    "VCCFIXDIGMIO": {
      "F1": "510mV",
      "F2": "520mV",
      "F3": "610mV",
      "F4": "640mV"
    }
  }
}
```

## Workflow
1. Load shmoo JSON.
2. Load expected Vmin JSON and flatten it into product/rail/frequency records.
3. For each shmoo (or filtered subset):
- Find rail match from `axis.ylabel`.
- Find frequency from `plist` or `instance` tokens (for example `F1`, `F2`, ...).
- Resolve expected Vmin for matched rail/frequency.
- Compare found vs expected Vmin.
- Update JSON with tagged display text:
  - `Vmin Found: <value>`
  - `Vmin Found (High): <value>` when found > expected.
4. Save output JSON.
5. Print summary counts (checked, matched, high).

## Command Pattern
```powershell
python vmin_detector.py "<shmoo_json>" "<expected_vmin_json>" -o "<output_json>"
```

Optional filters:
```powershell
python vmin_detector.py "<shmoo_json>" "<expected_vmin_json>" --plist "main_list" --visual-id "D6B54E4000062"
```

## Output Fields Added/Updated Per Matched Entry
- `vmin_found_raw`: original numeric/string value (preserved)
- `vmin_found`: tagged display value (`Vmin Found...`)
- `vmin_expected_mv`: expected Vmin in mV
- `vmin_found_mv`: found Vmin in mV (if parseable)
- `vmin_delta_mv`: found minus expected
- `vmin_status`: `high`, `ok`, `missing_found`, or `no_expected_match`
