"""Standalone offline HTML dashboard for the audited source-coverage JSON.

Rendering is pure, escaped, privacy-conscious, and requires no network.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

_STATUS_NL = {
    "direct_attempt_succeeded": "Direct geprobeerd: geslaagd",
    "direct_attempt_failed": "Direct geprobeerd: mislukt",
    "not_selected_within_round_limit": "Niet geselecteerd in deze ronde",
    "google_query_planned_not_executed": "Google-query gepland, niet uitgevoerd",
    "google_batch_succeeded_query_unconfirmed": "Google-batch geslaagd; bron onbewezen",
    "google_query_not_executed_or_provider_blocked": "Google geblokkeerd of niet uitgevoerd",
    "not_attempted": "Nog niet geprobeerd",
    "not_applicable": "Geen vacaturebron",
    "excluded": "Uitgesloten",
    "google_provider_batch_succeeded": "Google-bronbatch geslaagd",
    "google_provider_not_configured": "Google niet geconfigureerd",
    "google_provider_not_verified_free_or_insufficient_quota": "Gratis quota niet bevestigd",
    "google_provider_ready": "Google gereed, nog niet doorzocht",
}


def _safe(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def render_coverage_dashboard(report: dict[str, Any]) -> str:
    data = report.get("coverage")
    if not isinstance(data, dict) or data.get("schema") != "registered-source-coverage.v1":
        raise ValueError("Missing verified source coverage report")
    entries = data.get("sources")
    if not isinstance(entries, list):
        raise ValueError("Missing source rows")
    summary = data.get("summary") or {}
    modes = data.get("mode") or report.get("mode") or "unknown"
    metadata = (
        ("Actief", summary.get("active_total", 0)),
        ("Directe adapterbron", summary.get("adapter_registered", 0)),
        ("Google-site mogelijk", summary.get("google_site_eligible", 0)),
        ("Google-site gepland", summary.get("google_site_planned", 0)),
        ("Niet-actief", summary.get("inactive_total", 0)),
    )
    kpis = "\n".join(
        f'<div class="metric"><span>{_safe(key)}</span><strong>{_safe(value)}</strong></div>'
        for key, value in metadata
    )
    rows = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        status = str(row.get("execution") or "not_attempted")
        route = str(row.get("coverage_route") or "unavailable")
        rows.append(
            '<tr data-route="' + _safe(route) +
            '" data-state="' + _safe(status) + '"><td class="source">' +
            _safe(row.get("source_id")) + '</td><td>' +
            _safe(row.get("source_type")) + '</td><td>' +
            _safe(row.get("registry_status")) + '</td><td>' +
            _safe(route.replace("_", " ")) + '</td><td><span class="status">' +
            _safe(_STATUS_NL.get(status, status.replace("_", " "))) +
            '</span></td></tr>'
        )
    route_choices = sorted({str(r.get("coverage_route") or "unavailable")
                            for r in entries if isinstance(r, dict)})
    choices = '\n'.join(
        '<option value="' + _safe(route) + '">' +
        _safe(route.replace("_", " ")) + '</option>'
        for route in route_choices
    )
    notes = (
        "Check-modus: er zijn geen zoekrequests gedaan."
        if modes == "check" else
        "Google-hits zijn alleen ontdekking, geen bewijs van een rechtstreeks "
        "doorzochte bron of van een geschikte vacature."
    )
    return """<!doctype html>
<html lang="nl"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<title>Vacature Engine · Brondekking</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,
"Segoe UI",sans-serif;color:#e9edf6;background:#0d1320}
*{box-sizing:border-box}body{margin:0}main{max-width:1240px;margin:auto;padding:36px 22px 66px}
.header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;flex-wrap:wrap}
.eyebrow{letter-spacing:.16em;text-transform:uppercase;color:#9cb4d4;font-size:12px;font-weight:700}
h1{font-size:clamp(27px,4vw,43px);letter-spacing:-.035em;margin:8px 0 10px}
.description{color:#a4b4cd;max-width:760px;line-height:1.7;margin:0}
.meta{border:1px solid #344157;border-radius:12px;color:#d0deef;padding:10px 14px;
font-size:13px;background:#1a2435}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:28px 0}
.metric{background:linear-gradient(135deg,#1d2a3e,#152033);padding:19px 20px;
border:1px solid #314159;border-radius:16px;display:flex;flex-direction:column;gap:12px}
.metric span{font-size:12px;color:#a3b5ce}.metric strong{font-size:32px;letter-spacing:-.04em}
.panel{background:#152033;border:1px solid #314159;border-radius:18px;overflow:hidden}
.panelbar{padding:18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;
justify-content:space-between;border-bottom:1px solid #2c3950}
.controls{display:flex;flex-wrap:wrap;gap:8px}input,select{background:#0e1727;color:#e2ecfa;
border:1px solid #43516a;border-radius:9px;padding:10px 12px;font-size:14px}
input{min-width:260px}select{max-width:290px}
#visible{font-size:13px;color:#9bacbf;font-variant-numeric:tabular-nums}
.scroll{overflow:auto;max-height:72vh}table{width:100%;border-collapse:collapse;
font-size:13px;text-align:left}thead{position:sticky;top:0;background:#223049;z-index:2}
th,td{padding:13px 15px;border-bottom:1px solid #28364c;white-space:nowrap}
th{color:#bacce4;font-weight:600}.source{font-weight:650;color:#e1eefe}
.status{display:inline-block;max-width:440px;white-space:normal;padding:6px 9px;
border-radius:8px;background:#293b55;color:#d6eaff}
tbody tr:hover{background:#202e43}tr[hidden]{display:none}
.note{line-height:1.7;margin-top:18px;color:#99acc7;font-size:13px}
@media(max-width:600px){main{padding:24px 13px}input{min-width:180px;width:100%}
.controls{width:100%}.panelbar{align-items:stretch}th,td{padding:12px 10px}}
</style></head><body><main>
<header class="header"><div><div class="eyebrow">Webactueel · Vacature Engine</div>
<h1>Brondekking &amp; zoekrondes</h1>
<p class="description">Alle live Registerbronnen zijn opgenomen in het overzicht.
Bekijk welke bron rechtstreeks is geprobeerd, welke voor Google-discovery is
ingepland en welke nog niet is doorzocht. Een zoekresultaat is geen officiële
vacatureverificatie.</p></div><div class="meta">Ronde: ROUND &nbsp; · &nbsp;
Modus: MODE<br/>Google-status: GOOGLE</div></header>
<section class="metrics" aria-label="Kengetallen">KPI</section>
<section class="panel"><div class="panelbar"><strong>Bronnenregister</strong>
<div class="controls"><label><span class="eyebrow">Zoeken</span>
<input id="search" type="search" placeholder="Zoek bron, status of type…"
aria-label="Zoek bronnen"/></label>
<label><span class="eyebrow">Route</span><select id="route" aria-label="Filter op route">
<option value="">Alle routes</option>CHOICES</select></label></div>
<span id="visible" aria-live="polite"></span></div>
<div class="scroll"><table id="table"><thead><tr>
<th>Bron-ID</th><th>Type</th><th>Register</th><th>Uitvoerroute</th>
<th>Uitvoering</th></tr></thead><tbody>ROWS</tbody></table></div></section>
<p class="note">NOTE Brondekking is geen vacaturegeschiktheid. Geen automatische
sollicitaties, e-mails, betaalde zoekopdrachten of Registerstatuswijzigingen.</p>
</main>
<script>
"use strict";
const rows = [...document.querySelectorAll("#table tbody tr")];
const search = document.querySelector("#search");
const route = document.querySelector("#route");
const visible = document.querySelector("#visible");
function update(){
  const query = search.value.trim().toLocaleLowerCase("nl");
  const chosen = route.value;
  let count = 0;
  rows.forEach(row => {
    const match = (!chosen || row.dataset.route === chosen) &&
      (!query || row.textContent.toLocaleLowerCase("nl").includes(query));
    row.hidden = !match;
    if(match) count++;
  });
  visible.textContent = count + " / " + rows.length + " bronnen";
}
search.addEventListener("input", update);
route.addEventListener("change", update);
update();
</script></body></html>
""".replace("ROUND", _safe(data.get("round_index")))\
   .replace("MODE", _safe(modes))\
   .replace("GOOGLE", _safe(data.get("google_status")))\
   .replace("KPI", kpis).replace("CHOICES", choices)\
   .replace("ROWS", "\n".join(rows)).replace("NOTE", _safe(notes))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render privacy-conscious offline vacancy source coverage")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    view = render_coverage_dashboard(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(view, encoding="utf-8")
    print("Offline source coverage dashboard rendered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
