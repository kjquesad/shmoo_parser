#!/usr/bin/env python3
"""
Clean the pasted Shmooify docs dump (shmoos_descriptions.txt) into a single
structured Markdown file: one section per shmoo class, with the repeated
navigation sidebar and footer boilerplate removed.

Usage:
  python clean_descriptions.py INPUT.txt -o OUTPUT.md
"""

import argparse
import re
from pathlib import Path

SOURCE_RE = re.compile(r"^Source:\s*static/training_data/.*/SKILL_(?P<cls>.+?)\.md\s*$")
FOOTER = "Other apps from our team that you might like"

FAMILY_ORDER = ["crack", "marginal", "near-solid", "passing", "speckles"]

# Sub-section titles that appear as plain lines and should become '###' headings.
SECTION_TITLES = {
    "Class Description",
    "Visual Structure",
    "Reference Example",
    "Reference Examples",
    "Per-Row Generation Rules",
    "Key Constraints",
    "Dominant Segment Patterns per Row",
    "Transition Row Patterns",
    "Transition Row Patterns (cols 1\u201310)",
    "Algorithm to Generate a New Shmoo Chars",
    "Validation Checklist",
    "Distinguishing Features",
    "Visual Examples",
}

# A grid line is made only of these chars (+ optional trailing annotation).
GRID_CHARS = set("A*.#\u2190 ")


def is_grid_line(ln):
    """True if the line is (or starts with) a shmoo grid row."""
    s = ln.rstrip()
    if not s:
        return False
    if re.match(r"^Row\s*\d+\s*:", s):
        return True
    # A run of A/* or ./# possibly followed by an annotation after 2+ spaces.
    core = s
    ann = re.search(r"\s{2,}\S", s)
    if ann:
        core = s[: ann.start()]
    core = core.strip()
    if len(core) < 3:
        return False
    return all(c in "A*.#" for c in core)


def fence_grids(lines):
    """Wrap consecutive grid-row runs in ``` fenced code blocks."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        if is_grid_line(lines[i]):
            j = i
            while j < n and is_grid_line(lines[j]):
                j += 1
            out.append("```text")
            out.extend(lines[i:j])
            out.append("```")
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def tab_tables(lines):
    """Convert runs of tab-separated lines into Markdown pipe tables."""
    out = []
    i = 0
    n = len(lines)
    while i < n:
        if "\t" in lines[i]:
            j = i
            while j < n and "\t" in lines[j]:
                j += 1
            rows = [ln.split("\t") for ln in lines[i:j]]
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            header = rows[0]
            out.append("| " + " | ".join(c.strip() for c in header) + " |")
            out.append("| " + " | ".join(["---"] * width) + " |")
            for r in rows[1:]:
                out.append("| " + " | ".join(c.strip() for c in r) + " |")
            out.append("")
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def promote_headings(lines):
    out = []
    for ln in lines:
        stripped = ln.strip()
        if stripped in SECTION_TITLES or stripped.startswith("Reference Example"):
            out.append("")
            out.append(f"### {stripped}")
            out.append("")
        elif stripped.startswith("SKILL: Generate"):
            continue  # redundant echo of the class id
        else:
            out.append(ln)
    return out


def format_body(lines):
    lines = promote_headings(lines)
    lines = fence_grids(lines)
    lines = tab_tables(lines)
    return collapse_blank(lines)


def split_family(class_id):
    """crack_curve_BL-to-UR -> ('crack', 'curve_BL-to-UR')."""
    fam, _, rest = class_id.partition("_")
    return fam, rest


def collapse_blank(lines):
    out = []
    blanks = 0
    for ln in lines:
        if ln.strip() == "":
            blanks += 1
            if blanks <= 1:
                out.append("")
        else:
            blanks = 0
            out.append(ln.rstrip())
    # trim leading/trailing blanks
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return out


def extract_blocks(lines):
    """Return list of (class_id, title, content_lines)."""
    blocks = []
    n = len(lines)
    src_idx = [i for i, ln in enumerate(lines) if SOURCE_RE.match(ln)]
    for i in src_idx:
        m = SOURCE_RE.match(lines[i])
        cls = m.group("cls")
        # Title = non-empty line directly above the Source line.
        title = ""
        j = i - 1
        while j >= 0 and lines[j].strip() == "":
            j -= 1
        if j >= 0:
            title = lines[j].strip()
        # Content = from Source line to the next footer marker.
        end = n
        for k in range(i + 1, n):
            if lines[k].strip() == FOOTER:
                end = k
                break
        content = collapse_blank(lines[i:end])
        blocks.append((cls, title, content))
    return blocks


def build_markdown(blocks):
    md = []
    md.append("# Shmoo Category Reference")
    md.append("")
    md.append(
        "Cleaned reference of shmoo pattern classes, extracted from the "
        "Shmooify \u201cTraining Data \u2014 Per-Class Notes\u201d docs. "
        "Reference examples are 11\u00d711 grids using `A` = pass and `*` = fail; "
        "the structural rules are described per-row so they can be generalized "
        "to any grid dimension."
    )
    md.append("")

    # Group by family.
    by_family = {}
    for cls, title, content in blocks:
        fam, _ = split_family(cls)
        by_family.setdefault(fam, []).append((cls, title, content))

    # Table of contents.
    md.append("## Contents")
    md.append("")
    families = [f for f in FAMILY_ORDER if f in by_family]
    families += [f for f in by_family if f not in FAMILY_ORDER]
    for fam in families:
        md.append(f"- **{fam}**")
        for cls, title, _ in by_family[fam]:
            anchor = cls.lower().replace("_", "-")
            md.append(f"  - [{title}](#{anchor})")
    md.append("")

    for fam in families:
        md.append(f"# Family: {fam}")
        md.append("")
        for cls, title, content in by_family[fam]:
            md.append(f"## {cls}")
            md.append("")
            md.append(f"**Display name:** {title}  ")
            md.append(f"**Family:** {fam}  ")
            md.append(f"**Class id:** `{cls}`")
            md.append("")
            # Drop the raw "Source:" line and the "SKILL: ..." echo; keep the body.
            body = []
            for ln in content:
                if ln.startswith("Source:"):
                    continue
                body.append(ln)
            body = format_body(body)
            md.extend(body)
            md.append("")
            md.append("---")
            md.append("")
    return "\n".join(md).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    blocks = extract_blocks(lines)
    print(f"[clean] extracted {len(blocks)} class block(s)")
    md = build_markdown(blocks)
    Path(args.output).write_text(md, encoding="utf-8")
    print(f"[clean] wrote {args.output} ({len(md)} chars)")


if __name__ == "__main__":
    main()
