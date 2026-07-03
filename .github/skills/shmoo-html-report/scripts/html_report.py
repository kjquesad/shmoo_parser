"""Generate an interactive HTML report from shmoo_parsed.json."""

import argparse
import json
import webbrowser
from pathlib import Path
from typing import Any, Dict, List


def load_shmoo_data(json_path: Path) -> Dict[str, Any]:
    """Load and return parsed shmoo JSON."""
    return json.loads(json_path.read_text(encoding="utf-8"))


def flatten_entries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize both supported shmoo JSON shapes into a flat list."""
    shmoos = payload.get("shmoos", {})
    result: List[Dict[str, Any]] = []

    if not isinstance(shmoos, dict):
        return result

    for key, value in shmoos.items():
        # Shape A: visual_id -> [entries]
        if isinstance(value, list):
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                normalized = dict(entry)
                normalized.setdefault("visual_id", key)
                normalized.setdefault("source_file", "")
                result.append(normalized)
            continue

        # Shape B: source -> visual_id -> [entries]
        if isinstance(value, dict):
            source_file = key
            for visual_id, entries in value.items():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    normalized = dict(entry)
                    normalized.setdefault("visual_id", visual_id)
                    normalized.setdefault("source_file", source_file)
                    result.append(normalized)

    return result


def infer_team(instance: str) -> str:
    """Fallback inference if team is missing in JSON."""
    if not instance:
        return "UNKNOWN"
    if "_COMP::" in instance:
        return instance.split("_COMP::", 1)[0]
    if "::" in instance:
        return instance.split("::", 1)[0]
    prefixes = ["SCN_SCAN", "SIO_BSCAN", "TATPG", "RESET_COMP", "DV", "PCS"]
    for prefix in prefixes:
        if instance.startswith(prefix):
            return prefix
    return "UNKNOWN"


def normalize_classification(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize classification into a stable shape."""
    raw = entry.get("classification")
    if isinstance(raw, dict):
        category = str(raw.get("category") or "").strip()
        confidence = raw.get("confidence")
        out: Dict[str, Any] = {
            "category": category or "unclassified",
            "confidence": confidence if isinstance(confidence, (int, float)) else None,
        }
        if isinstance(raw.get("features"), dict):
            out["features"] = raw.get("features")
        return out

    if isinstance(raw, str) and raw.strip():
        return {"category": raw.strip(), "confidence": None}

    # Fallback support for alternate keys.
    alt = str(entry.get("classification_category") or entry.get("class") or "").strip()
    if alt:
        conf = entry.get("classification_confidence")
        return {
            "category": alt,
            "confidence": conf if isinstance(conf, (int, float)) else None,
        }

    return {"category": "unclassified", "confidence": None}


def slim_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only fields needed by the report."""
    failing_data = entry.get("failing_data") if isinstance(entry.get("failing_data"), dict) else {}
    instance = entry.get("instance") or ""
    team = entry.get("team") or infer_team(instance)
    classification = normalize_classification(entry)
    tags = entry.get("tags") if isinstance(entry.get("tags"), list) else []

    return {
        "visual_id": entry.get("visual_id"),
        "die_id": entry.get("die_id"),
        "instance": instance,
        "team": team,
        "location": entry.get("location"),
        "plist": entry.get("plist"),
        "vmin_found": entry.get("vmin_found"),
        "vmin_status": entry.get("vmin_status"),
        "vmin_expected_mv": entry.get("vmin_expected_mv"),
        "vmin_found_mv": entry.get("vmin_found_mv"),
        "vmin_delta_mv": entry.get("vmin_delta_mv"),
        "vmin_expected_rail": entry.get("vmin_expected_rail"),
        "vmin_expected_freq": entry.get("vmin_expected_freq"),
        "vmin_tag": entry.get("vmin_tag"),
        "high_vmin": entry.get("high_vmin"),
        "vmin_is_high": entry.get("vmin_is_high"),
        "source_file": entry.get("source_file"),
        "axis": entry.get("axis") if isinstance(entry.get("axis"), dict) else {},
        "legends": entry.get("legends") if isinstance(entry.get("legends"), dict) else {},
        "rows": failing_data.get("rows") if isinstance(failing_data.get("rows"), list) else [],
        "failures": failing_data.get("failures") if isinstance(failing_data.get("failures"), list) else [],
        "classification": classification,
        "classification_category": classification.get("category"),
        "classification_confidence": classification.get("confidence"),
        "tags": tags,
    }


def normalize_vmin_status(entry: Dict[str, Any]) -> str:
    """Normalize vmin status from explicit field or tagged text."""
    status = str(entry.get("vmin_status") or "").strip().lower()
    if status:
        return status

    vmin_tag = str(entry.get("vmin_tag") or "").strip().lower()
    if vmin_tag in {"high", "ok", "missing_found", "no_expected_match", "unknown"}:
        return vmin_tag

    found = str(entry.get("vmin_found") or "").lower()
    if bool(entry.get("high_vmin")) or bool(entry.get("vmin_is_high")):
        return "high"

    tags = entry.get("tags")
    if isinstance(tags, list):
        tag_set = {str(t).strip().lower() for t in tags}
        if any(t in tag_set for t in {"high_vmin", "vmin_high", "high"}):
            return "high"

    if "(high)" in found:
        return "high"
    if "vmin found" in found:
        return "ok"
    return "unknown"


def apply_entry_filters(
    entries: List[Dict[str, Any]],
    team: str,
    plist_contains: str,
    search_text: str,
    vmin_status: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Apply optional CLI filters before generating the report."""
    team_norm = team.strip().lower()
    plist_norm = plist_contains.strip().lower()
    search_norm = search_text.strip().lower()
    vmin_norm = vmin_status.strip().lower()

    filtered: List[Dict[str, Any]] = []
    for entry in entries:
        if team_norm and str(entry.get("team") or infer_team(str(entry.get("instance") or ""))).lower() != team_norm:
            continue
        if plist_norm and plist_norm not in str(entry.get("plist") or "").lower():
            continue
        if vmin_norm and normalize_vmin_status(entry) != vmin_norm:
            continue
        if search_norm:
            haystack = " ".join(
                [
                    str(entry.get("visual_id") or ""),
                    str(entry.get("instance") or ""),
                    str(entry.get("plist") or ""),
                    str(entry.get("die_id") or ""),
                    str(entry.get("source_file") or ""),
                    str(entry.get("team") or ""),
                    str(entry.get("vmin_found") or ""),
                    str(entry.get("vmin_status") or ""),
                    str(entry.get("vmin_tag") or ""),
                    str(entry.get("vmin_expected_rail") or ""),
                    str(entry.get("vmin_expected_freq") or ""),
                    str(entry.get("classification_category") or ""),
                    " ".join(str(t) for t in (entry.get("tags") or [])),
                ]
            ).lower()
            if search_norm not in haystack:
                continue
        filtered.append(entry)

    if limit > 0:
        return filtered[:limit]
    return filtered


def build_html(entries: List[Dict[str, Any]], meta: Dict[str, Any]) -> str:
    """Build report HTML."""
    payload = json.dumps({"meta": meta, "entries": entries}, ensure_ascii=False, separators=(",", ":"))

    parts: List[str] = []
    parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Shmoo Report</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Segoe UI",sans-serif;background:#f4f6f5;color:#1a2b25}
header{padding:14px 20px;background:#fff;border-bottom:1px solid #d4ddd8;position:sticky;top:0;z-index:9}
header h1{font-size:1.1rem;font-weight:700}
header .info{font-size:.82rem;color:#5a6e66;margin-top:4px}
.filters{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.filters select,.filters input{padding:6px 10px;border:1px solid #c5d0cb;border-radius:6px;font-size:.84rem;background:#fff}
.filters select{min-width:160px}
.filters input{flex:1;min-width:180px}
.wrap{display:flex;height:calc(100vh - 150px)}
.sidebar{width:340px;border-right:1px solid #d4ddd8;background:#fff;overflow-y:auto;flex-shrink:0;padding:10px}
.unit-group{margin-bottom:12px}
.unit-header{font-weight:700;font-size:.84rem;padding:6px 8px;background:#edf8f4;border:1px solid #c5e8db;border-radius:6px;margin-bottom:4px}
.unit-header .count{font-weight:400;color:#5a6e66;font-size:.76rem}
.card{border:1px solid #d4ddd8;border-radius:6px;padding:6px 8px;margin-bottom:4px;margin-left:8px;cursor:pointer;transition:border-color .15s}
.card:hover{border-color:#7ab8a4}
.card.active{border-color:#0d7c66;background:#edf8f4}
.card .inst{font-size:.78rem;color:#2a4a40;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .team-tag{display:inline-block;font-size:.68rem;background:#e0ebe5;border-radius:3px;padding:1px 5px;color:#2a5e48;margin-top:2px}
.card .class-tag{display:inline-block;font-size:.68rem;border-radius:3px;padding:1px 5px;margin-top:2px;margin-left:4px;font-weight:600}
.card .vmin-tag{display:inline-block;font-size:.68rem;border-radius:3px;padding:1px 5px;margin-top:2px;margin-left:4px;font-weight:700}
.vmin-tag.high{background:#ffe5e5;color:#9f1239}
.vmin-tag.ok{background:#dcfce7;color:#166534}
.vmin-tag.missing_found,.vmin-tag.no_expected_match,.vmin-tag.unknown{background:#f3f4f6;color:#374151}
.class-tag.red{background:#fde2e2;color:#b91c1c}.class-tag.clean{background:#d1fae5;color:#065f46}
.class-tag.ceiling{background:#fef3c7;color:#92400e}.class-tag.floor{background:#e0e7ff;color:#3730a3}
.class-tag.diagonal{background:#ede9fe;color:#5b21b6}.class-tag.speed_limit{background:#fee2e2;color:#991b1b}
.class-tag.slow_limit{background:#dbeafe;color:#1e40af}.class-tag.crack{background:#fce7f3;color:#9d174d}
.class-tag.island{background:#ccfbf1;color:#134e4a}.class-tag.mixed{background:#f3f4f6;color:#374151}
.class-tag.corner_top_left,.class-tag.corner_top_right,.class-tag.corner_bottom_left,.class-tag.corner_bottom_right{background:#fff7ed;color:#9a3412}
.class-tag.left_wall,.class-tag.right_wall{background:#e2f4ff;color:#0b4f73}
.class-tag.speckled{background:#fef9c3;color:#854d0e}
.meta-item.classification .v{font-weight:600}
.main{flex:1;overflow-y:auto;padding:16px}
.panel{background:#fff;border:1px solid #d4ddd8;border-radius:10px;padding:14px;margin-bottom:12px}
.panel h2{font-size:.92rem;margin-bottom:10px;color:#1a3b2e}
.meta-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.meta-item{background:#f7faf8;border:1px solid #e0ebe5;border-radius:6px;padding:6px 8px}
.meta-item.wide{grid-column:span 2}
.meta-item .k{font-size:.7rem;text-transform:uppercase;color:#5a6e66;letter-spacing:.04em}
.meta-item .v{font-size:.84rem;margin-top:2px;white-space:normal;overflow-wrap:anywhere;word-break:break-word;font-family:Consolas,monospace}
#shmoo-grid{width:100%;overflow:auto;display:flex;justify-content:center;padding:10px 0}
#shmoo-grid table{border-collapse:collapse;margin:0 auto}
#shmoo-grid td{width:24px;height:24px;text-align:center;font-size:13px;font-family:Consolas,monospace;border:1px solid #e8ede9}
#shmoo-grid td.pass{background:#b7e4c7;color:#155d27}
#shmoo-grid td.fail{color:#fff;position:relative;cursor:pointer}
#point-selected{margin-top:8px;background:#f7faf8;border:1px solid #e0ebe5;border-radius:6px;padding:8px 10px;font-size:.82rem;color:#1f3a31}
#point-selected .title{font-weight:700;margin-bottom:4px;color:#1a3b2e}
#point-selected .empty{padding:0;text-align:left}
#point-selected>div:not(.title):not(.empty){white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.legend-tbl{width:100%;table-layout:fixed;border-collapse:collapse;font-size:.82rem;margin-top:6px}
.legend-tbl th,.legend-tbl td{border:1px solid #dde5dd;padding:5px 7px;text-align:left;overflow-wrap:anywhere;word-break:break-word}
.legend-tbl th:first-child,.legend-tbl td:first-child{width:70px}
.legend-tbl th{background:#f2f7f3}
.empty{padding:20px;text-align:center;color:#5a6e66}
.theme-toggle{position:absolute;top:14px;right:20px;padding:6px 12px;border:1px solid #c5d0cb;border-radius:6px;font-size:.8rem;background:#fff;color:#1a2b25;cursor:pointer}
.theme-toggle:hover{border-color:#7ab8a4}
/* Dark theme */
body.dark{background:#121212;color:#e6e6e6}
body.dark header{background:#1c1c1c;border-bottom-color:#333}
body.dark header .info{color:#a0a0a0}
body.dark .theme-toggle{background:#2a2a2a;color:#e6e6e6;border-color:#444}
body.dark .filters select,body.dark .filters input{background:#2a2a2a;color:#e6e6e6;border-color:#444}
body.dark .sidebar{background:#1c1c1c;border-right-color:#333}
body.dark .unit-header{background:#243029;border-color:#33463c;color:#e6e6e6}
body.dark .unit-header .count{color:#a0a0a0}
body.dark .card{border-color:#333;background:#222}
body.dark .card:hover{border-color:#4a8f78}
body.dark .card.active{border-color:#2a9d8f;background:#233}
body.dark .card .inst{color:#cfe8dd}
body.dark .card .team-tag{background:#2f3f37;color:#9fd6bf}
body.dark .main{color:#e6e6e6}
body.dark .panel{background:#1c1c1c;border-color:#333}
body.dark .panel h2{color:#cfe8dd}
body.dark .meta-item{background:#242424;border-color:#3a3a3a}
body.dark .meta-item .k{color:#9a9a9a}
body.dark .meta-item .v{color:#e6e6e6}
body.dark #shmoo-grid td{border-color:#333}
body.dark #shmoo-grid td.pass{background:#1f4d33;color:#a7e8c4}
body.dark #point-selected{background:#242424;border-color:#3a3a3a;color:#e6e6e6}
body.dark #point-selected .title{color:#cfe8dd}
body.dark .legend-tbl th,body.dark .legend-tbl td{border-color:#3a3a3a}
body.dark .legend-tbl th{background:#242424}
body.dark .empty{color:#9a9a9a}
.view{display:none}
.view.active{display:block}
.tabs{display:flex;gap:6px;margin-top:10px}
.tab-btn{padding:6px 14px;border:1px solid #c5d0cb;border-radius:6px 6px 0 0;background:#eef3f1;color:#1a2b25;cursor:pointer;font-size:.84rem;font-weight:600}
.tab-btn.active{background:#0d7c66;color:#fff;border-color:#0d7c66}
body.heatmaps-active .filters{display:none}
.hm-filters{display:none}
body.heatmaps-active .hm-filters{display:flex}
#hm-grid{width:100%;overflow:auto;display:flex;justify-content:center;padding:10px 0}
#hm-grid table{border-collapse:collapse;margin:0 auto}
#hm-grid td{width:28px;height:26px;text-align:center;font-size:12px;font-family:Consolas,monospace;border:1px solid #e8ede9}
#hm-grid td.pass{background:#f2f7f4;color:#9fb3aa}
#hm-grid td.fail{cursor:pointer;font-weight:700;color:#fff;text-shadow:0 0 2px rgba(0,0,0,.65)}
#hm-info{margin-bottom:8px;font-size:.82rem;color:#5a6e66}
#hm-point{margin-top:8px;background:#f7faf8;border:1px solid #e0ebe5;border-radius:6px;padding:8px 10px;font-size:.82rem;color:#1f3a31}
#hm-point .title{font-weight:700;margin-bottom:4px;color:#1a3b2e}
#hm-point>div:not(.title):not(.empty){margin-bottom:2px}
body.dark .tab-btn{background:#242424;color:#e6e6e6;border-color:#444}
body.dark .tab-btn.active{background:#2a9d8f;color:#08130f;border-color:#2a9d8f}
body.dark #hm-grid td{border-color:#333}
body.dark #hm-grid td.pass{background:#222;color:#555}
body.dark #hm-info{color:#a0a0a0}
body.dark #hm-point{background:#242424;border-color:#3a3a3a;color:#e6e6e6}
body.dark #hm-point .title{color:#cfe8dd}
@media (max-width: 980px){.wrap{display:block;height:auto}.sidebar{width:100%;border-right:none;border-bottom:1px solid #d4ddd8;max-height:42vh}}
</style>
</head>
<body>
<header>
  <h1 id="report-title">Shmoo HTML Report</h1>
  <button id="theme-toggle" class="theme-toggle" type="button">Dark mode</button>
  <div class="info" id="hdr-info"></div>
  <div class="tabs">
    <button class="tab-btn active" type="button" data-view="shmoos">Shmoos</button>
    <button class="tab-btn" type="button" data-view="heatmaps">HeatMaps</button>
  </div>
  <div class="filters">
    <select id="team-filter"><option value="">All Teams</option></select>
    <select id="location-filter"><option value="">All Locations</option></select>
    <select id="unit-filter"><option value="">All Units</option></select>
    <select id="class-filter"><option value="">All Classifications</option></select>
    <select id="vmin-filter"><option value="">All Vmin Status</option></select>
    <input id="search" placeholder="Search instance, plist..." />
  </div>
  <div class="filters hm-filters">
    <select id="hm-team-filter"><option value="">All Teams</option></select>
    <select id="hm-location-filter"><option value="">All Locations</option></select>
  </div>
</header>
<div id="view-shmoos" class="view active">
<div class="wrap">
  <aside class="sidebar">
    <div id="card-list"></div>
  </aside>
  <div class="main">
    <div class="panel"><h2>Metadata</h2><div class="meta-grid" id="meta-panel"></div></div>
    <div class="panel"><h2>Shmoo Visualization</h2><div id="shmoo-grid"></div><div id="point-selected"><div class="title">Point Selected</div><div class="empty">Click a failing point in the grid to inspect it.</div></div></div>
    <div class="panel"><h2>Legend</h2><div id="legend-panel"></div></div>
  </div>
</div>
</div>
<div id="view-heatmaps" class="view">
<div class="wrap">
  <aside class="sidebar">
    <div id="hm-list"></div>
  </aside>
  <div class="main">
    <div class="panel"><h2>Instance Heatmap</h2><div class="info" id="hm-info"></div><div id="hm-grid"><div class="empty">Select an instance to view its heatmap.</div></div><div id="hm-point"><div class="title">Cell Selected</div><div class="empty">Click a cell in the heatmap to see failing units.</div></div></div>
  </div>
</div>
</div>
<script id="report-data" type="application/json">""")

    parts.append(payload)

    parts.append("""</script>
<script>
(function(){
  var data = JSON.parse(document.getElementById("report-data").textContent);
  var entries = data.entries || [];
  var meta = data.meta || {};

  var themeToggle = document.getElementById("theme-toggle");
  function applyTheme(mode){
    var dark = mode === "dark";
    document.body.classList.toggle("dark", dark);
    themeToggle.textContent = dark ? "Light mode" : "Dark mode";
  }
  var savedTheme = null;
  try { savedTheme = localStorage.getItem("shmooReportTheme"); } catch (err) {}
  applyTheme(savedTheme === "dark" ? "dark" : "light");
  themeToggle.addEventListener("click", function(){
    var next = document.body.classList.contains("dark") ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("shmooReportTheme", next); } catch (err) {}
  });

  var hdrInfo = document.getElementById("hdr-info");
  var titleEl = document.getElementById("report-title");
  if (titleEl && meta.report_title) {
    titleEl.textContent = "Shmoo HTML Report: " + meta.report_title;
  }
  hdrInfo.textContent = "Total shmoos: " + entries.length +
    " | Visual IDs: " + (meta.visual_id_count || "-") +
    " | Files scanned: " + (meta.files_scanned || "-") +
    " | High Vmin: " + (meta.high_vmin_count || 0);

  var cardList = document.getElementById("card-list");
  var metaPanel = document.getElementById("meta-panel");
  var shmooGrid = document.getElementById("shmoo-grid");
  var pointSelected = document.getElementById("point-selected");
  var legendPanel = document.getElementById("legend-panel");
  var searchBox = document.getElementById("search");
  var teamFilter = document.getElementById("team-filter");
  var locationFilter = document.getElementById("location-filter");
  var unitFilter = document.getElementById("unit-filter");

  var classFilter = document.getElementById("class-filter");
  var vminFilter = document.getElementById("vmin-filter");

  var teamSet = {};
  var locationSet = {};
  var unitSet = {};
  var classSet = {};
  var vminSet = {};
  for (var i = 0; i < entries.length; i++) {
    teamSet[entries[i].team || "UNKNOWN"] = true;
    locationSet[entries[i].location || "UNKNOWN"] = true;
    unitSet[entries[i].visual_id || "NO_VISUAL_ID"] = true;
    var cl = entries[i].classification;
    var clCat = entries[i].classification_category || (cl && cl.category ? cl.category : "unclassified");
    classSet[clCat || "unclassified"] = true;
    vminSet[deriveVminStatus(entries[i])] = true;
  }

  Object.keys(teamSet).sort().forEach(function(team){
    var opt = document.createElement("option");
    opt.value = team;
    opt.textContent = team;
    teamFilter.appendChild(opt);
  });

  Object.keys(locationSet).sort().forEach(function(loc){
    var opt = document.createElement("option");
    opt.value = loc;
    opt.textContent = loc;
    locationFilter.appendChild(opt);
  });

  Object.keys(unitSet).sort().forEach(function(unit){
    var opt = document.createElement("option");
    opt.value = unit;
    opt.textContent = unit;
    unitFilter.appendChild(opt);
  });

  Object.keys(classSet).sort().forEach(function(cls){
    var opt = document.createElement("option");
    opt.value = cls;
    opt.textContent = cls;
    classFilter.appendChild(opt);
  });

  Object.keys(vminSet).sort().forEach(function(vs){
    var opt = document.createElement("option");
    opt.value = vs;
    opt.textContent = vminLabel(vs);
    vminFilter.appendChild(opt);
  });

  var filtered = entries.slice();
  var selectedIdx = 0;
  var COLORS = ["#e76f51","#f4a261","#e9c46a","#2a9d8f","#457b9d","#f72585","#4361ee","#7209b7","#ef476f","#06d6a0","#ff7f11","#1d3557","#8ecae6","#e63946","#fb8500"];

  function esc(v){ return (v === null || v === undefined || v === "") ? "-" : String(v); }
  function escAttr(v){
    return String(v === null || v === undefined ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/'/g, "&#39;");
  }
  function shortFile(v){ if(!v) return "-"; var p=v.replace(/\\\\/g,"/").split("/"); return p[p.length-1] || v; }
  function getColor(sym, idx){ return sym === "*" ? "#b7e4c7" : COLORS[idx % COLORS.length]; }
  function categoryClassName(cat){ return (cat || "").toLowerCase().replace(/\\s+/g, "_"); }
  function vminClassName(status){ return (status || "unknown").toLowerCase().replace(/\\s+/g, "_"); }
  function vminLabel(status){
    var s = (status === null || status === undefined) ? "" : String(status).toLowerCase();
    if (s === "ok") return "normal";
    if (s === "no_expected_match") return "no vmin expected";
    if (s === "missing_found") return "missing found";
    return s;
  }
  function fmtMv(v){
    if (v === null || v === undefined || v === "") return "-";
    var n = Number(v);
    if (!isFinite(n)) return String(v);
    return (n % 1 === 0 ? n.toFixed(0) : String(n)) + " mV";
  }
  function formatVminDisplay(vminFound, vminStatus){
    var raw = vminFound ? String(vminFound) : "";
    raw = raw.replace(/^Vmin Found(?: \\(High\\))?:\\s*/i, "");
    if (!raw) raw = "N/A";
    if (vminStatus === "high") return "High: " + raw;
    if (vminStatus === "ok") return "Normal: " + raw;
    return raw;
  }
  function deriveVminStatus(e){
    if (e.vmin_status) return String(e.vmin_status).toLowerCase();
    if (e.vmin_tag) {
      var t = String(e.vmin_tag).toLowerCase();
      if (t === "high" || t === "ok" || t === "missing_found" || t === "no_expected_match" || t === "unknown") return t;
    }
    if (e.high_vmin === true || e.vmin_is_high === true) return "high";
    if (Array.isArray(e.tags)) {
      for (var ti = 0; ti < e.tags.length; ti++) {
        var tg = String(e.tags[ti] || "").toLowerCase();
        if (tg === "high_vmin" || tg === "vmin_high" || tg === "high") return "high";
      }
    }
    var vf = e.vmin_found ? String(e.vmin_found).toLowerCase() : "";
    if (vf.indexOf("(high)") !== -1) return "high";
    if (vf.indexOf("vmin found") !== -1) return "ok";
    return "unknown";
  }

  function renderCards(){
    if (!filtered.length) {
      cardList.innerHTML = '<div class="empty">No shmoos match filters.</div>';
      renderDetail();
      return;
    }

    var groups = {};
    var order = [];
    for (var i = 0; i < filtered.length; i++) {
      var vid = filtered[i].visual_id || "NO_VISUAL_ID";
      if (!groups[vid]) { groups[vid] = []; order.push(vid); }
      groups[vid].push({entry: filtered[i], idx: i});
    }

    var html = "";
    for (var g = 0; g < order.length; g++) {
      var vid = order[g];
      var items = groups[vid];
      html += '<div class="unit-group">';
      html += '<div class="unit-header">' + esc(vid) + ' <span class="count">(' + items.length + ' shmoos)</span></div>';
      for (var j = 0; j < items.length; j++) {
        var e = items[j].entry;
        var idx = items[j].idx;
        var cls = idx === selectedIdx ? "card active" : "card";
        html += '<div class="' + cls + '" data-idx="' + idx + '">';
        var clCat = e.classification_category || ((e.classification && e.classification.category) ? e.classification.category : '');
        var clCatClass = categoryClassName(clCat);
        var confRaw = (e.classification_confidence !== null && e.classification_confidence !== undefined)
          ? e.classification_confidence
          : ((e.classification && e.classification.confidence !== undefined) ? e.classification.confidence : null);
        var clConf = (typeof confRaw === 'number') ? (confRaw * 100).toFixed(0) + '%' : '';
        var vmStat = deriveVminStatus(e);
        var vmClass = vminClassName(vmStat);
        html += '<div class="inst">' + esc(e.instance) + '</div>';
        html += '<span class="team-tag">' + esc(e.team) + '</span>';
        if (clCat) { html += '<span class="class-tag ' + clCatClass + '">' + clCat + (clConf ? ' ' + clConf : '') + '</span>'; }
        if (vmStat && vmStat !== 'unknown') { html += '<span class="vmin-tag ' + vmClass + '">Vmin: ' + esc(vminLabel(vmStat)) + '</span>'; }
        html += '</div>';
      }
      html += '</div>';
    }

    cardList.innerHTML = html;
    var cards = cardList.querySelectorAll('.card');
    for (var c = 0; c < cards.length; c++) {
      cards[c].addEventListener('click', function(){
        selectedIdx = parseInt(this.getAttribute('data-idx'));
        renderCards();
        renderDetail();
      });
    }
    renderDetail();
  }

  function renderMeta(e){
    var clInfo = e.classification;
    var clCat = e.classification_category || (clInfo && clInfo.category ? clInfo.category : 'unclassified');
    var confRaw = (e.classification_confidence !== null && e.classification_confidence !== undefined)
      ? e.classification_confidence
      : ((clInfo && clInfo.confidence !== undefined) ? clInfo.confidence : null);
    var clText = clCat;
    if (typeof confRaw === 'number') {
      clText += ' (' + (confRaw * 100).toFixed(0) + '% confidence)';
    }
    var vminStatus = deriveVminStatus(e);
    var xRange = esc(e.axis.xstart) + " to " + esc(e.axis.xstop) + " step " + esc(e.axis.xstep);
    var yRange = esc(e.axis.ystart) + " to " + esc(e.axis.ystop) + " step " + esc(e.axis.ystep);
    var items = [
      ["Visual ID", e.visual_id],
      ["Team", e.team],
      ["Location", e.location],
      ["Classification", clText],
      ["Vmin Status", vminLabel(vminStatus)],
      ["Die ID", e.die_id],
      ["Instance", e.instance],
      ["PList", e.plist],
      ["Vmin Found", fmtMv(e.vmin_found_mv)],
      ["Vmin Expected", fmtMv(e.vmin_expected_mv)],
      ["Vmin Delta", fmtMv(e.vmin_delta_mv)],
      ["Vmin Rail", e.vmin_expected_rail],
      ["Vmin Freq", e.vmin_expected_freq],
      ["Source", shortFile(e.source_file)],
      ["X", {label: e.axis.xlabel, range: xRange}],
      ["Y", {label: e.axis.ylabel, range: yRange}]
    ];

    var html = "";
    for (var i = 0; i < items.length; i++) {
      var key = items[i][0];
      var value = items[i][1];
      var cls = (key === "Instance" || key === "PList") ? "meta-item wide" : "meta-item";
      if (key === "Classification") cls = "meta-item classification";
      if ((key === "X" || key === "Y") && value && typeof value === "object") {
        html += '<div class="' + cls + '"><div class="k">' + key + '</div><div class="v">' + esc(value.label) + '<br>' + esc(value.range) + '</div></div>';
      } else {
        html += '<div class="' + cls + '"><div class="k">' + key + '</div><div class="v">' + esc(value) + '</div></div>';
      }
    }
    metaPanel.innerHTML = html;
  }

  function renderGrid(e){
    var rows = e.rows || [];
    if (!rows.length) {
      shmooGrid.innerHTML = '<div class="empty">No shmoo row data.</div>';
      pointSelected.innerHTML = '<div class="title">Point Selected</div><div class="empty">Click a failing point in the grid to inspect it.</div>';
      return;
    }

    var axis = e.axis || {};
    var xStart = Number(axis.xstart || 0);
    var xStep = Number(axis.xstep || 1);
    var yStart = Number(axis.ystart || 0);
    var yStep = Number(axis.ystep || 1);

    var maxCols = 0;
    for (var r = 0; r < rows.length; r++) { if (rows[r].length > maxCols) maxCols = rows[r].length; }

    var failures = Array.isArray(e.failures) ? e.failures : [];
    var failureMap = {};
    for (var fi = 0; fi < failures.length; fi++) {
      var f = failures[fi] || {};
      var fx = Number(f.x);
      var fy = Number(f.y);
      if (!isFinite(fx) || !isFinite(fy)) continue;
      var xIdx = Math.round((fx - xStart) / xStep);
      var yIdx = Math.round((fy - yStart) / yStep);
      if (!isFinite(xIdx) || !isFinite(yIdx) || xIdx < 0 || yIdx < 0) continue;
      var k = xIdx + "|" + yIdx;
      if (!failureMap[k]) failureMap[k] = [];
      var info = (f.legend_info !== undefined && f.legend_info !== null && String(f.legend_info).trim())
        ? String(f.legend_info).trim()
        : ((f.symbol && e.legends && e.legends[f.symbol]) ? String(e.legends[f.symbol]).trim() : "");
      if (!info) continue;
      if (failureMap[k].indexOf(info) === -1) failureMap[k].push(info);
    }

    var symbolSet = {};
    for (var rr = 0; rr < rows.length; rr++) {
      for (var cc = 0; cc < rows[rr].length; cc++) { symbolSet[rows[rr][cc]] = true; }
    }
    var symbols = Object.keys(symbolSet).sort();
    var symbolIdx = {};
    for (var si = 0; si < symbols.length; si++) { symbolIdx[symbols[si]] = si; }

    var html = '<table><tr><td></td>';
    for (var x = 0; x < maxCols; x++) {
      var xVal = (xStart + x * xStep).toFixed(3);
      html += "<td style='font-size:11px;writing-mode:vertical-rl;transform:rotate(180deg);height:72px;padding:4px 2px'>" + xVal + "</td>";
    }
    html += '</tr>';

    for (var y = 0; y < rows.length; y++) {
      var yVal = (yStart + y * yStep).toFixed(4);
      html += "<tr><td style='font-size:11px;white-space:nowrap;padding-right:8px'>" + yVal + "</td>";
      var row = rows[y];
      for (var x2 = 0; x2 < maxCols; x2++) {
        var ch = x2 < row.length ? row[x2] : " ";
        if (ch === "*") {
          html += '<td class="pass">*</td>';
        } else {
          var bg = getColor(ch, symbolIdx[ch] || 0);
          var xValCell = (xStart + x2 * xStep).toFixed(6);
          var yValCell = (yStart + y * yStep).toFixed(6);
          var key = x2 + "|" + y;
          var failInfoList = failureMap[key] || [];
          var failInfo = failInfoList.length ? failInfoList.join(" ; ") : ((e.legends && e.legends[ch]) ? e.legends[ch] : "");
          var failInfoText = escAttr(failInfo || "Unknown");
          html += '<td class="fail" data-xidx="' + x2 + '" data-yidx="' + y + '" data-x="' + xValCell + '" data-y="' + yValCell + '" data-symbol="' + ch + '" data-failure-info="' + failInfoText + '" title="' + failInfoText + '" style="background:' + bg + '">' + ch + '</td>';
        }
      }
      html += '</tr>';
    }
    html += '</table>';
    shmooGrid.innerHTML = html;

    pointSelected.innerHTML = '<div class="title">Point Selected</div><div class="empty">Click a failing point in the grid to inspect it.</div>';

    var failCells = shmooGrid.querySelectorAll('td.fail');
    for (var f = 0; f < failCells.length; f++) {
      failCells[f].addEventListener('click', function(){
        var xidx = this.getAttribute('data-xidx');
        var yidx = this.getAttribute('data-yidx');
        var xval = this.getAttribute('data-x');
        var yval = this.getAttribute('data-y');
        var symbol = this.getAttribute('data-symbol');
        var cellInfo = this.getAttribute('data-failure-info');
        var failInfo = cellInfo || ((e.legends && e.legends[symbol]) ? e.legends[symbol] : '-');

        pointSelected.innerHTML =
          '<div class="title">Point Selected</div>' +
          '<div><b>Symbol:</b> ' + esc(symbol) + '</div>' +
          '<div><b>Grid Index:</b> x=' + esc(xidx) + ', y=' + esc(yidx) + '</div>' +
          '<div><b>X Value:</b> ' + esc(xval) + '</div>' +
          '<div><b>Y Value:</b> ' + esc(yval) + '</div>' +
          '<div><b>Failure Info:</b> ' + esc(failInfo) + '</div>';
      });
    }
  }

  function renderLegend(e){
    var legends = e.legends || {};
    var keys = Object.keys(legends);
    if (!keys.length) {
      legendPanel.innerHTML = '<div class="empty">No legend data.</div>';
      return;
    }
    keys.sort();
    var html = '<table class="legend-tbl"><tr><th>Symbol</th><th>Failure Info</th></tr>';
    for (var i = 0; i < keys.length; i++) {
      html += '<tr><td>' + keys[i] + '</td><td>' + esc(legends[keys[i]]) + '</td></tr>';
    }
    html += '</table>';
    legendPanel.innerHTML = html;
  }

  function renderDetail(){
    if (!filtered.length) {
      metaPanel.innerHTML = '<div class="empty">No shmoo selected.</div>';
      shmooGrid.innerHTML = '';
      pointSelected.innerHTML = '<div class="title">Point Selected</div><div class="empty">No shmoo selected.</div>';
      legendPanel.innerHTML = '';
      return;
    }
    var e = filtered[selectedIdx] || filtered[0];
    renderMeta(e);
    renderGrid(e);
    renderLegend(e);
  }

  function applyFilter(){
    var teamVal = teamFilter.value;
    var locationVal = locationFilter.value;
    var unitVal = unitFilter.value;
    var classVal = classFilter.value;
    var vminVal = vminFilter.value;
    var q = searchBox.value.trim().toLowerCase();

    filtered = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (teamVal && (e.team || "UNKNOWN") !== teamVal) continue;
      if (locationVal && (e.location || "UNKNOWN") !== locationVal) continue;
      if (unitVal && (e.visual_id || "") !== unitVal) continue;
      if (classVal) {
        var eCat = e.classification_category || ((e.classification && e.classification.category) ? e.classification.category : "unclassified");
        if (eCat !== classVal) continue;
      }
      if (vminVal) {
        if (deriveVminStatus(e) !== vminVal) continue;
      }
      if (q) {
        var hay = [
          e.visual_id,
          e.instance,
          e.plist,
          e.die_id,
          e.location,
          e.source_file,
          e.team,
          e.vmin_found,
          e.vmin_status,
          e.vmin_tag,
          e.vmin_expected_rail,
          e.vmin_expected_freq,
          e.classification_category,
          Array.isArray(e.tags) ? e.tags.join(' ') : ''
        ].join(' ').toLowerCase();
        if (hay.indexOf(q) === -1) continue;
      }
      filtered.push(e);
    }

    selectedIdx = 0;
    renderCards();
  }

  // ===== HeatMaps =====
  var hmList = document.getElementById("hm-list");
  var hmGrid = document.getElementById("hm-grid");
  var hmPoint = document.getElementById("hm-point");
  var hmInfo = document.getElementById("hm-info");
  var hmTeamFilter = document.getElementById("hm-team-filter");
  var hmLocationFilter = document.getElementById("hm-location-filter");
  var hmGroups = {};
  var hmOrder = [];
  var hmSelectedInstance = null;

  Object.keys(teamSet).sort().forEach(function(team){
    var opt = document.createElement("option");
    opt.value = team;
    opt.textContent = team;
    hmTeamFilter.appendChild(opt);
  });
  Object.keys(locationSet).sort().forEach(function(loc){
    var opt = document.createElement("option");
    opt.value = loc;
    opt.textContent = loc;
    hmLocationFilter.appendChild(opt);
  });

  function heatColor(ratio){
    var a = 0.18 + 0.82 * Math.max(0, Math.min(1, ratio));
    return 'rgba(220,38,38,' + a.toFixed(3) + ')';
  }

  function failureInfoMap(e){
    var axis = e.axis || {};
    var xStart = Number(axis.xstart || 0), xStep = Number(axis.xstep || 1);
    var yStart = Number(axis.ystart || 0), yStep = Number(axis.ystep || 1);
    var failures = Array.isArray(e.failures) ? e.failures : [];
    var map = {};
    for (var fi = 0; fi < failures.length; fi++) {
      var f = failures[fi] || {};
      var fx = Number(f.x), fy = Number(f.y);
      if (!isFinite(fx) || !isFinite(fy)) continue;
      var xIdx = Math.round((fx - xStart) / xStep);
      var yIdx = Math.round((fy - yStart) / yStep);
      if (!isFinite(xIdx) || !isFinite(yIdx) || xIdx < 0 || yIdx < 0) continue;
      var k = xIdx + "|" + yIdx;
      var info = (f.legend_info !== undefined && f.legend_info !== null && String(f.legend_info).trim())
        ? String(f.legend_info).trim()
        : ((f.symbol && e.legends && e.legends[f.symbol]) ? String(e.legends[f.symbol]).trim() : "");
      if (!info) continue;
      if (!map[k]) map[k] = info;
    }
    return map;
  }

  function buildHeatGroups(){
    var teamVal = hmTeamFilter.value;
    var locationVal = hmLocationFilter.value;
    hmGroups = {}; hmOrder = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (teamVal && (e.team || "UNKNOWN") !== teamVal) continue;
      if (locationVal && (e.location || "UNKNOWN") !== locationVal) continue;
      var inst = e.instance || "(no instance)";
      if (!hmGroups[inst]) { hmGroups[inst] = []; hmOrder.push(inst); }
      hmGroups[inst].push(e);
    }
    hmOrder.sort();
    if (hmSelectedInstance && !hmGroups[hmSelectedInstance]) hmSelectedInstance = null;
  }

  function renderHmList(){
    if (!hmOrder.length) { hmList.innerHTML = '<div class="empty">No instances.</div>'; return; }
    var html = "";
    for (var g = 0; g < hmOrder.length; g++) {
      var inst = hmOrder[g];
      var items = hmGroups[inst];
      var units = {};
      for (var j = 0; j < items.length; j++) { units[items[j].visual_id || "?"] = true; }
      var cls = inst === hmSelectedInstance ? "card active" : "card";
      html += '<div class="' + cls + ' hm-card" data-inst="' + escAttr(inst) + '">';
      html += '<div class="inst">' + esc(inst) + '</div>';
      html += '<span class="team-tag">' + Object.keys(units).length + ' units &middot; ' + items.length + ' shmoos</span>';
      html += '</div>';
    }
    hmList.innerHTML = html;
    var cards = hmList.querySelectorAll('.hm-card');
    for (var c = 0; c < cards.length; c++) {
      cards[c].addEventListener('click', function(){
        hmSelectedInstance = this.getAttribute('data-inst');
        renderHmList();
        renderHeatmap();
      });
    }
  }

  function renderHeatmap(){
    if (!hmSelectedInstance || !hmGroups[hmSelectedInstance]) {
      hmGrid.innerHTML = '<div class="empty">Select an instance to view its heatmap.</div>';
      hmInfo.textContent = "";
      hmPoint.innerHTML = '<div class="title">Cell Selected</div><div class="empty">Click a cell in the heatmap to see failing units.</div>';
      return;
    }
    var items = hmGroups[hmSelectedInstance];
    var ref = items[0], bestArea = -1, maxCols = 0, maxRows = 0;
    for (var i = 0; i < items.length; i++) {
      var rws = items[i].rows || [];
      var cols = 0;
      for (var r = 0; r < rws.length; r++) { if (rws[r].length > cols) cols = rws[r].length; }
      if (rws.length > maxRows) maxRows = rws.length;
      if (cols > maxCols) maxCols = cols;
      var area = rws.length * cols;
      if (area > bestArea) { bestArea = area; ref = items[i]; }
    }
    var axis = ref.axis || {};
    var xStart = Number(axis.xstart || 0), xStep = Number(axis.xstep || 1);
    var yStart = Number(axis.ystart || 0), yStep = Number(axis.ystep || 1);

    var unitTotals = {};
    for (var u = 0; u < items.length; u++) { unitTotals[items[u].visual_id || "?"] = true; }
    var totalUnitCount = Object.keys(unitTotals).length;

    var cell = {};
    for (var i2 = 0; i2 < items.length; i2++) {
      var e2 = items[i2];
      var vid = e2.visual_id || "?";
      var rows2 = e2.rows || [];
      var fMap = failureInfoMap(e2);
      for (var y = 0; y < rows2.length; y++) {
        var row = rows2[y];
        for (var x = 0; x < row.length; x++) {
          var ch = row[x];
          if (ch === "*" || ch === " ") continue;
          var key = x + "|" + y;
          if (!cell[key]) cell[key] = { units: {}, infos: {} };
          cell[key].units[vid] = true;
          var info = fMap[key] || ((e2.legends && e2.legends[ch]) ? e2.legends[ch] : ch);
          if (!cell[key].infos[vid]) cell[key].infos[vid] = [];
          if (cell[key].infos[vid].indexOf(info) === -1) cell[key].infos[vid].push(info);
        }
      }
    }

    var html = '<table><tr><td></td>';
    for (var x1 = 0; x1 < maxCols; x1++) {
      var xVal = (xStart + x1 * xStep).toFixed(3);
      html += "<td style='font-size:11px;writing-mode:vertical-rl;transform:rotate(180deg);height:72px;padding:4px 2px'>" + xVal + "</td>";
    }
    html += '</tr>';
    for (var y2 = 0; y2 < maxRows; y2++) {
      var yVal = (yStart + y2 * yStep).toFixed(4);
      html += "<tr><td style='font-size:11px;white-space:nowrap;padding-right:8px'>" + yVal + "</td>";
      for (var x2 = 0; x2 < maxCols; x2++) {
        var key2 = x2 + "|" + y2;
        var c2 = cell[key2];
        var cnt = c2 ? Object.keys(c2.units).length : 0;
        if (cnt === 0) {
          html += '<td class="pass">&middot;</td>';
        } else {
          var ratio = totalUnitCount ? cnt / totalUnitCount : 0;
          html += '<td class="fail" data-key="' + key2 + '" data-xidx="' + x2 + '" data-yidx="' + y2 + '" title="' + cnt + ' / ' + totalUnitCount + ' units" style="background:' + heatColor(ratio) + '">' + cnt + '</td>';
        }
      }
      html += '</tr>';
    }
    html += '</table>';
    hmGrid.innerHTML = html;

    hmInfo.textContent = "Instance: " + hmSelectedInstance + "  |  " + totalUnitCount + " units overlaid  |  grid " + maxCols + " x " + maxRows;
    hmPoint.innerHTML = '<div class="title">Cell Selected</div><div class="empty">Click a cell in the heatmap to see failing units.</div>';

    var cells = hmGrid.querySelectorAll('td.fail');
    for (var q = 0; q < cells.length; q++) {
      cells[q].addEventListener('click', (function(cellRef, axisRef, total){
        return function(){
          var key = this.getAttribute('data-key');
          var xidx = this.getAttribute('data-xidx');
          var yidx = this.getAttribute('data-yidx');
          var cc = cellRef[key] || { units: {}, infos: {} };
          var vids = Object.keys(cc.units).sort();
          var xv = Number(axisRef.xstart || 0) + Number(xidx) * Number(axisRef.xstep || 1);
          var yv = Number(axisRef.ystart || 0) + Number(yidx) * Number(axisRef.ystep || 1);
          var rowsHtml = "";
          for (var v = 0; v < vids.length; v++) {
            var infos = (cc.infos[vids[v]] || []).join(" ; ");
            rowsHtml += '<tr><td>' + esc(vids[v]) + '</td><td>' + esc(infos || "-") + '</td></tr>';
          }
          hmPoint.innerHTML =
            '<div class="title">Cell Selected</div>' +
            '<div><b>Grid Index:</b> x=' + esc(xidx) + ', y=' + esc(yidx) + '</div>' +
            '<div><b>X Value:</b> ' + esc(xv.toFixed(6)) + '</div>' +
            '<div><b>Y Value:</b> ' + esc(yv.toFixed(6)) + '</div>' +
            '<div><b>Failing Units:</b> ' + vids.length + ' / ' + total + '</div>' +
            '<table class="legend-tbl"><tr><th>Visual ID</th><th>Failing Legend</th></tr>' + rowsHtml + '</table>';
        };
      })(cell, axis, totalUnitCount));
    }
  }

  var tabBtns = document.querySelectorAll('.tab-btn');
  var viewShmoos = document.getElementById('view-shmoos');
  var viewHeatmaps = document.getElementById('view-heatmaps');
  function switchView(name){
    var isHeat = name === 'heatmaps';
    if (viewShmoos) viewShmoos.classList.toggle('active', !isHeat);
    if (viewHeatmaps) viewHeatmaps.classList.toggle('active', isHeat);
    document.body.classList.toggle('heatmaps-active', isHeat);
    for (var t = 0; t < tabBtns.length; t++) {
      tabBtns[t].classList.toggle('active', tabBtns[t].getAttribute('data-view') === name);
    }
    if (isHeat) {
      if (!hmSelectedInstance && hmOrder.length) hmSelectedInstance = hmOrder[0];
      renderHmList();
      renderHeatmap();
    }
  }
  for (var tb = 0; tb < tabBtns.length; tb++) {
    tabBtns[tb].addEventListener('click', function(){ switchView(this.getAttribute('data-view')); });
  }
  buildHeatGroups();

  function onHeatFilterChange(){
    buildHeatGroups();
    if (!hmSelectedInstance && hmOrder.length) hmSelectedInstance = hmOrder[0];
    renderHmList();
    renderHeatmap();
  }
  hmTeamFilter.addEventListener('change', onHeatFilterChange);
  hmLocationFilter.addEventListener('change', onHeatFilterChange);

  teamFilter.addEventListener('change', applyFilter);
  locationFilter.addEventListener('change', applyFilter);
  unitFilter.addEventListener('change', applyFilter);
  classFilter.addEventListener('change', applyFilter);
  vminFilter.addEventListener('change', applyFilter);
  searchBox.addEventListener('input', applyFilter);
  renderCards();
})();
</script>
</body>
</html>""")

    return "".join(parts)


def derive_report_title(entries, path_folder):
    """Return the VPO number if a single VPO is present, else the source folder name."""
    vpos = set()
    for entry in entries:
        src = entry.get("source_file") or ""
        if not src:
            continue
        base = Path(str(src).replace("\\", "/")).name
        vpo = base.split("_", 1)[0].strip()
        if vpo:
            vpos.add(vpo)

    if len(vpos) == 1:
        return next(iter(vpos))

    if path_folder:
        folder = Path(str(path_folder).replace("\\", "/")).name
        if folder:
            return folder

    return next(iter(vpos)) if vpos else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML shmoo report from shmoo_parsed.json.")
    parser.add_argument("input_json", help="Path to shmoo_parsed.json")
    parser.add_argument("-o", "--output", default="shmoo_report.html", help="Output HTML path")
    parser.add_argument("--visual-id", default="", help="Optional filter to a specific visual ID / unit")
    parser.add_argument("--team", default="", help="Optional exact team filter before report generation")
    parser.add_argument("--plist", default="", help="Optional substring filter for plist")
    parser.add_argument("--search", default="", help="Optional free-text filter across key fields")
    parser.add_argument(
      "--vmin-status",
      default="",
      choices=["", "high", "ok", "missing_found", "no_expected_match", "unknown"],
      help="Optional Vmin status filter before report generation",
    )
    parser.add_argument(
      "--limit",
      type=int,
      default=0,
      help="Optional max number of shmoos to include after filtering (0 means no limit)",
    )
    args = parser.parse_args()

    input_json = Path(args.input_json)
    output_html = Path(args.output)

    if not input_json.exists():
        raise FileNotFoundError(f"Not found: {input_json}")

    payload = load_shmoo_data(input_json)
    entries = flatten_entries(payload)

    if args.visual_id:
        entries = [entry for entry in entries if (entry.get("visual_id") or "") == args.visual_id]

    entries = apply_entry_filters(
      entries,
      team=args.team,
      plist_contains=args.plist,
      search_text=args.search,
      vmin_status=args.vmin_status,
      limit=args.limit,
    )

    slim_entries = [slim_entry(entry) for entry in entries]

    report_title = derive_report_title(slim_entries, payload.get("path_folder"))

    meta = {
        "files_scanned": payload.get("files_scanned"),
        "files_with_shmoo": payload.get("files_with_shmoo"),
        "total_shmoos": len(slim_entries),
        "visual_id_count": len({entry.get("visual_id") or "NO_VISUAL_ID" for entry in slim_entries}),
        "high_vmin_count": len(
            [
                entry
                for entry in slim_entries
            if normalize_vmin_status(entry) == "high"
            ]
        ),
        "path_folder": payload.get("path_folder"),
        "report_title": report_title,
        "filter_visual_id": args.visual_id or None,
        "filter_team": args.team or None,
        "filter_plist": args.plist or None,
        "filter_search": args.search or None,
        "filter_vmin_status": args.vmin_status or None,
        "limit": args.limit or None,
    }

    html = build_html(slim_entries, meta)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8")

    print(f"Done. {len(slim_entries)} shmoo(s), {meta['visual_id_count']} visual ID(s).")
    print(f"Report: {output_html}")

    report_uri = output_html.resolve().as_uri()
    if webbrowser.open(report_uri):
      print("Opened report in default browser.")
    else:
      print("Report generated, but browser could not be launched automatically.")


if __name__ == "__main__":
    main()
