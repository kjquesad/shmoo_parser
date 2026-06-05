---
name: shmoo-onenote-report
description: "Run full shmoo analysis, extract high-vmin units, and publish a OneNote summary for a target notebook with today's date title."
argument-hint: "Provide input data path and target OneNote notebook name"
user-invocable: true
---

# Shmoo OneNote Report Skill

Use this skill when the user asks for full shmoo analysis plus publishing a summary into OneNote.

## When to Use
- "make a full analysis over <path> and create a one note report in my DMR notebook"
- "run full analysis and push high-vmin summary to OneNote"
- "analyze this data and create OneNote report with today's date"

## Workflow
1. Resolve input path and notebook name from user prompt.
2. Resolve output folder from input path.
3. Run full enrichment pipeline:
   - parser -> classifier -> vmin detector
   - keep final output as `<output_folder>/shmoo_parsed.json`.
4. Generate high-vmin HTML report:
   - `python .github/skills/shmoo-html-report/scripts/html_report.py "<output_folder>/shmoo_parsed.json" -o "<output_folder>/shmoo_report_high_vmin.html" --vmin-status high`
5. Build OneNote summary payload:
   - `python .github/skills/shmoo-onenote-report/scripts/build_onenote_summary.py "<output_folder>/shmoo_parsed.json" --html-report "<output_folder>/shmoo_report_high_vmin.html" --notebook "<NOTEBOOK_NAME>" -o "<output_folder>/onenote_report_payload.json"`
6. Publish to OneNote:
   - Preferred: use M365 MCP tools to publish page content to the target notebook/section.
   - Expected tool sequence:
     1) `onenote_list_notebooks` to resolve notebook by display name.
     2) `onenote_list_sections` for notebook sections.
     3) `onenote_create_page` (if available) with title from payload and HTML body from payload.
   - Title must use today's date by default: `YYYY-MM-DD - High Vmin Summary`.
7. Return summary with:
   - analysis counts
   - high-vmin unit list
   - HTML report path
   - OneNote notebook + page title
   - publish status

## Notes
- If the OneNote MCP endpoint does not expose a page-create tool yet, still generate `onenote_report_payload.json` so the content is ready to publish once `onenote_create_page` is available.
- Notebook matching is case-insensitive by display name.
