---
name: shmoo-html-report
description: "Create shmoo visualization HTML report from shmoo_parsed.json using html_report.py. Use when user asks to visualize shmoos, show shmoos, or generate/create an HTML report."
argument-hint: "Provide path to shmoo_parsed.json"
user-invocable: true
---

# Shmoo HTML Report Skill

Use this skill whenever user asks to visualize shmoo data.

## When to Use
- "show me the shmoos"
- "create html report"
- "visualize shmoo"
- "generate report from shmoo_parsed.json"

## Workflow
1. Resolve JSON input path.
2. If JSON path is missing, first run the `shmoo-parser` skill.
3. Run the report generator:
   - `python html_report.py <input_json> -o <output_html>`
4. Return summary with:
   - input JSON path
   - output HTML path
   - total shmoos
   - visual ID count

## Command Pattern
```powershell
python html_report.py "<input_json>" -o "<output_html>"
```

## Default Output Naming
- If input is `<folder>\shmoo_parsed.json`, output should be `<folder>\shmoo_report.html` unless user specifies otherwise.
