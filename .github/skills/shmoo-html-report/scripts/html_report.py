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


def slim_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only fields needed by the report."""
    failing_data = entry.get("failing_data") if isinstance(entry.get("failing_data"), dict) else {}
    instance = entry.get("instance") or ""
    team = entry.get("team") or infer_team(instance)
    classification = entry.get("classification") if isinstance(entry.get("classification"), dict) else None

    return {
        "visual_id": entry.get("visual_id"),
        "die_id": entry.get("die_id"),
        "instance": instance,
        "team": team,
        "plist": entry.get("plist"),
        "vmin_found": entry.get("vmin_found"),
      "vmin_status": entry.get("vmin_status"),
      "vmin_expected_mv": entry.get("vmin_expected_mv"),
      "vmin_found_mv": entry.get("vmin_found_mv"),
      "vmin_delta_mv": entry.get("vmin_delta_mv"),
      "vmin_expected_rail": entry.get("vmin_expected_rail"),
      "vmin_expected_freq": entry.get("vmin_expected_freq"),
        "source_file": entry.get("source_file"),
        "axis": entry.get("axis") if isinstance(entry.get("axis"), dict) else {},
        "legends": entry.get("legends") if isinstance(entry.get("legends"), dict) else {},
        "rows": failing_data.get("rows") if isinstance(failing_data.get("rows"), list) else [],
        "classification": classification,
    }


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
.wrap{display:flex;height:calc(100vh - 110px)}
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
.meta-item .v{font-size:.84rem;margin-top:2px;word-break:break-all;font-family:Consolas,monospace}
#shmoo-grid{width:100%;overflow:auto;display:flex;justify-content:center;padding:10px 0}
#shmoo-grid table{border-collapse:collapse;margin:0 auto}
#shmoo-grid td{width:24px;height:24px;text-align:center;font-size:13px;font-family:Consolas,monospace;border:1px solid #e8ede9}
#shmoo-grid td.pass{background:#b7e4c7;color:#155d27}
#shmoo-grid td.fail{color:#fff}
#point-selected{margin-top:8px;background:#f7faf8;border:1px solid #e0ebe5;border-radius:6px;padding:8px 10px;font-size:.82rem;color:#1f3a31}
#point-selected .title{font-weight:700;margin-bottom:4px;color:#1a3b2e}
#point-selected .empty{padding:0;text-align:left}
.legend-tbl{width:100%;border-collapse:collapse;font-size:.82rem;margin-top:6px}
.legend-tbl th,.legend-tbl td{border:1px solid #dde5dd;padding:5px 7px;text-align:left}
.legend-tbl th{background:#f2f7f3}
.empty{padding:20px;text-align:center;color:#5a6e66}
@media (max-width: 980px){.wrap{display:block;height:auto}.sidebar{width:100%;border-right:none;border-bottom:1px solid #d4ddd8;max-height:42vh}}
</style>
</head>
<body>
<header>
  <h1>Shmoo HTML Report</h1>
  <div class="info" id="hdr-info"></div>
  <div class="filters">
    <select id="team-filter"><option value="">All Teams</option></select>
    <select id="unit-filter"><option value="">All Units</option></select>
    <select id="class-filter"><option value="">All Classifications</option></select>
    <select id="vmin-filter"><option value="">All Vmin Status</option></select>
    <input id="search" placeholder="Search instance, plist..." />
  </div>
</header>
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
<script id="report-data" type="application/json">""")

    parts.append(payload)

    parts.append("""</script>
<script>
(function(){
  var data = JSON.parse(document.getElementById("report-data").textContent);
  var entries = data.entries || [];
  var meta = data.meta || {};

  var hdrInfo = document.getElementById("hdr-info");
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
  var unitFilter = document.getElementById("unit-filter");

  var classFilter = document.getElementById("class-filter");
  var vminFilter = document.getElementById("vmin-filter");

  var teamSet = {};
  var unitSet = {};
  var classSet = {};
  var vminSet = {};
  for (var i = 0; i < entries.length; i++) {
    teamSet[entries[i].team || "UNKNOWN"] = true;
    unitSet[entries[i].visual_id || "NO_VISUAL_ID"] = true;
    var cl = entries[i].classification;
    classSet[cl && cl.category ? cl.category : "unclassified"] = true;
    vminSet[deriveVminStatus(entries[i])] = true;
  }

  Object.keys(teamSet).sort().forEach(function(team){
    var opt = document.createElement("option");
    opt.value = team;
    opt.textContent = team;
    teamFilter.appendChild(opt);
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
    opt.textContent = vs;
    vminFilter.appendChild(opt);
  });

  var filtered = entries.slice();
  var selectedIdx = 0;
  var COLORS = ["#e76f51","#f4a261","#e9c46a","#2a9d8f","#457b9d","#f72585","#4361ee","#7209b7","#ef476f","#06d6a0","#ff7f11","#1d3557","#8ecae6","#e63946","#fb8500"];

  function esc(v){ return (v === null || v === undefined || v === "") ? "-" : String(v); }
  function shortFile(v){ if(!v) return "-"; var p=v.replace(/\\\\/g,"/").split("/"); return p[p.length-1] || v; }
  function getColor(sym, idx){ return sym === "*" ? "#b7e4c7" : COLORS[idx % COLORS.length]; }
  function categoryClassName(cat){ return (cat || "").toLowerCase().replace(/\\s+/g, "_"); }
  function vminClassName(status){ return (status || "unknown").toLowerCase().replace(/\\s+/g, "_"); }
  function formatVminDisplay(vminFound, vminStatus){
    var raw = vminFound ? String(vminFound) : "";
    raw = raw.replace(/^Vmin Found(?: \\(High\\))?:\\s*/i, "");
    if (!raw) raw = "N/A";
    if (vminStatus === "high") return "High: " + raw;
    if (vminStatus === "ok") return "OK: " + raw;
    return raw;
  }
  function deriveVminStatus(e){
    if (e.vmin_status) return String(e.vmin_status);
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
        var clCat = (e.classification && e.classification.category) ? e.classification.category : '';
        var clCatClass = categoryClassName(clCat);
        var clConf = (e.classification && e.classification.confidence) ? (e.classification.confidence * 100).toFixed(0) + '%' : '';
        var vmStat = deriveVminStatus(e);
        var vmClass = vminClassName(vmStat);
        html += '<div class="inst">' + esc(e.instance) + '</div>';
        html += '<span class="team-tag">' + esc(e.team) + '</span>';
        if (clCat) { html += '<span class="class-tag ' + clCatClass + '">' + clCat + (clConf ? ' ' + clConf : '') + '</span>'; }
        if (vmStat && vmStat !== 'unknown') { html += '<span class="vmin-tag ' + vmClass + '">VMIN ' + esc(vmStat.toUpperCase()) + '</span>'; }
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
    var clText = clInfo ? clInfo.category + ' (' + ((clInfo.confidence||0)*100).toFixed(0) + '% confidence)' : 'unclassified';
    var vminStatus = deriveVminStatus(e);
    var vminDisplay = formatVminDisplay(e.vmin_found, vminStatus);
    var xRange = esc(e.axis.xstart) + " to " + esc(e.axis.xstop) + " step " + esc(e.axis.xstep);
    var yRange = esc(e.axis.ystart) + " to " + esc(e.axis.ystop) + " step " + esc(e.axis.ystep);
    var items = [
      ["Visual ID", e.visual_id],
      ["Team", e.team],
      ["Classification", clText],
      ["Vmin Status", vminStatus],
      ["Die ID", e.die_id],
      ["Instance", e.instance],
      ["PList", e.plist],
      ["Vmin Found", vminDisplay],
      ["Vmin Expected (mV)", e.vmin_expected_mv],
      ["Vmin Found (mV)", e.vmin_found_mv],
      ["Vmin Delta (mV)", e.vmin_delta_mv],
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
          html += '<td class="fail" data-xidx="' + x2 + '" data-yidx="' + y + '" data-x="' + xValCell + '" data-y="' + yValCell + '" data-symbol="' + ch + '" style="background:' + bg + '">' + ch + '</td>';
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
        var failInfo = (e.legends && e.legends[symbol]) ? e.legends[symbol] : '-';

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
    var unitVal = unitFilter.value;
    var classVal = classFilter.value;
    var vminVal = vminFilter.value;
    var q = searchBox.value.trim().toLowerCase();

    filtered = [];
    for (var i = 0; i < entries.length; i++) {
      var e = entries[i];
      if (teamVal && (e.team || "UNKNOWN") !== teamVal) continue;
      if (unitVal && (e.visual_id || "") !== unitVal) continue;
      if (classVal) {
        var eCat = (e.classification && e.classification.category) ? e.classification.category : "unclassified";
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
          e.source_file,
          e.team,
          e.vmin_found,
          e.vmin_status,
          e.vmin_expected_rail,
          e.vmin_expected_freq
        ].join(' ').toLowerCase();
        if (hay.indexOf(q) === -1) continue;
      }
      filtered.push(e);
    }

    selectedIdx = 0;
    renderCards();
  }

  teamFilter.addEventListener('change', applyFilter);
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HTML shmoo report from shmoo_parsed.json.")
    parser.add_argument("input_json", help="Path to shmoo_parsed.json")
    parser.add_argument("-o", "--output", default="shmoo_report.html", help="Output HTML path")
    parser.add_argument("--visual-id", default="", help="Optional filter to a specific visual ID / unit")
    parser.add_argument(
        "--open",
        dest="open_report",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open the generated report in the default web browser (default: enabled)",
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

    slim_entries = [slim_entry(entry) for entry in entries]

    meta = {
        "files_scanned": payload.get("files_scanned"),
        "files_with_shmoo": payload.get("files_with_shmoo"),
        "total_shmoos": len(slim_entries),
        "visual_id_count": len({entry.get("visual_id") or "NO_VISUAL_ID" for entry in slim_entries}),
      "high_vmin_count": len(
        [
          entry
          for entry in slim_entries
          if str(entry.get("vmin_status") or "").lower() == "high"
          or "(high)" in str(entry.get("vmin_found") or "").lower()
        ]
      ),
        "path_folder": payload.get("path_folder"),
        "filter_visual_id": args.visual_id or None,
    }

    html = build_html(slim_entries, meta)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8")

    print(f"Done. {len(slim_entries)} shmoo(s), {meta['visual_id_count']} visual ID(s).")
    print(f"Report: {output_html}")

    if args.open_report:
        report_uri = output_html.resolve().as_uri()
        if webbrowser.open(report_uri):
            print("Opened report in default browser.")
        else:
            print("Report generated, but browser could not be launched automatically.")


if __name__ == "__main__":
    main()
