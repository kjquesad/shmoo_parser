---
name: shmoo-email-report
description: "Generate a team-filtered shmoo email report from shmoo_parsed.json. Use when user asks for an email report or wants shmoo summary email text."
argument-hint: "Provide json path. If missing team or email, ask for both before running."
user-invocable: true
---

# Shmoo Email Report Skill

Use this skill when the user asks for an email report.

## When to Use
- "create an email report"
- "send shmoo summary email"
- "generate report for team by email"

## Required Inputs
- `email` (recipient email)
- `team` (team name used to filter shmoos)

Do not run the report script until both values are provided.

## Mandatory Interaction Rule
1. If `email` is missing, ask for it.
2. If `team` is missing, ask for it.
3. If both are missing, ask for both.
4. Do not proceed with parsing/generation until both answers are received.

## Workflow
1. Resolve input JSON path.
2. If JSON path is missing, first run the `shmoo-parser` skill.
3. Collect and confirm `email` and `team`.
4. Generate the email report (HTML visual style by default) and optionally send with Outlook:
   - `python email_report.py <input_json> --team <team> --email <email> --email-format <html|text> -o <output_file> --outlook-action <none|display|send>`
5. Return summary with:
   - input JSON path
   - output report path
   - team filter used
   - recipient email
   - matching units and shmoo count

## Output Content Requirements
The generated email body must be grouped by unit and include:
- Unit header
- For each shmoo:
  - PList name
  - Die ID (if available)
   - Shmoo data grid (HTML mode) or shmoo data rows (text mode)
  - Legend entries

## Command Pattern
```powershell
python .github/skills/shmoo-email-report/scripts/email_report.py "<input_json>" --team "<team>" --email "<email>" --email-format html -o "<output_folder>/shmoo_email_report.html" --outlook-action send
```

## Format Options
- `--email-format html`: visual email body with styled shmoo grids and legend tables (default)
- `--email-format text`: plain text report body

## Outlook Integration
- `--outlook-action none`: generate report only (default)
- `--outlook-action display`: open prefilled Outlook draft window
- `--outlook-action send`: send directly through Outlook
- Requires Windows + Outlook + `pywin32` (`pip install pywin32`)

## Default Output Naming
- If input is `<folder>\shmoo_parsed.json`:
   - HTML mode -> `<folder>\shmoo_email_report.html`
   - Text mode -> `<folder>\shmoo_email_report.txt`