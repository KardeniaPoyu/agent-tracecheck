from __future__ import annotations

import html
import json
from pathlib import Path

from .model import Report
from .rules import RULES


def text_report(report: Report) -> str:
    data = report.to_dict()
    s = data["summary"]
    lines = [
        f"Agent TraceCheck | {s['records']} records | {s['error']} errors | {s['warning']} warnings | {s['info']} info"
    ]
    for i in report.issues:
        location = f"{i.source.path}:{i.source.line}{i.source.pointer}#{i.pointer}"
        lines.extend(
            [f"{i.severity.upper()} {i.rule} [{i.id}] {location}", f"  {i.message}", f"  Fix: {i.suggestion}"]
        )
    return "\n".join(lines) + "\n"


def sarif_report(report: Report) -> dict:
    used = sorted({i.rule for i in report.issues})
    levels = {"error": "error", "warning": "warning", "info": "note"}
    results = []
    for i in report.issues:
        source = i.source
        uri = Path(source.path).as_uri() if Path(source.path).is_absolute() else source.path
        results.append(
            {
                "ruleId": i.rule,
                "level": levels[i.severity],
                "message": {
                    "text": f"{i.message} JSON pointer: {source.pointer}{i.pointer}. Fix: {i.suggestion}"
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": uri},
                            "region": {"startLine": source.line},
                        }
                    }
                ],
                "partialFingerprints": {"agentTracecheck/v1": i.id},
                "properties": {
                    "jsonPointer": source.pointer + i.pointer,
                    "record": source.record,
                    "related": i.related,
                },
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "agent-tracecheck",
                        "version": "0.1.0",
                        "rules": [
                            {
                                "id": k,
                                "shortDescription": {"text": RULES[k].title},
                                "help": {"text": RULES[k].suggestion},
                                "properties": {"category": RULES[k].category},
                            }
                            for k in used
                        ],
                    }
                },
                "results": results,
            }
        ],
    }


def markdown_report(report: Report) -> str:
    s = report.to_dict()["summary"]
    rows = [
        "# Agent TraceCheck",
        "",
        f"Scanned **{s['records']}** records: **{s['error']}** errors, **{s['warning']}** warnings, **{s['info']}** informational findings.",
        "",
    ]
    for i in report.issues:
        esc = lambda value: html.escape(str(value)).replace("`", "&#96;")
        rows.extend(
            [
                f"## {i.rule} · {i.severity}",
                "",
                esc(i.message),
                "",
                f"Location: `{esc(i.source.path)}:{i.source.line}` · `{esc(i.source.pointer + i.pointer)}`",
                "",
                f"Suggestion: {esc(i.suggestion)}",
                "",
                f"Issue ID: `{i.id}`",
                "",
            ]
        )
    return "\n".join(rows)


def html_report(report: Report) -> str:
    # No remote assets, eval, or interpolation into innerHTML. Escape script terminators.
    payload = (
        json.dumps(report.to_dict(), ensure_ascii=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return HTML.replace("__REPORT_DATA__", payload)


def render(report: Report, format: str) -> str:
    if format == "json":
        return json.dumps(report.to_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if format == "sarif":
        return json.dumps(sarif_report(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if format == "html":
        return html_report(report)
    if format == "markdown":
        return markdown_report(report)
    return text_report(report)


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Agent TraceCheck · Quality report</title><style>
:root{color-scheme:dark;--bg:#101719;--panel:#182326;--line:#304044;--text:#e6eeeb;--muted:#a0b4ae;--accent:#a6efb9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:48px 28px}header{border-bottom:1px solid var(--line);padding-bottom:28px}.eyebrow{color:var(--accent);font:12px monospace;letter-spacing:2px}h1{font-size:clamp(32px,5vw,58px);line-height:1.1;margin:16px 0}p{color:var(--muted)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:30px 0}.stat{padding:22px;background:var(--panel);border:1px solid var(--line);border-radius:10px}.stat strong{font-size:32px;display:block}.stat span{color:var(--muted)}.toolbar{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px}input,select{background:var(--panel);color:var(--text);border:1px solid var(--line);padding:12px;border-radius:7px;font:inherit}input{flex:1;min-width:220px}label{display:flex;align-items:center;gap:8px}.issue{border:1px solid var(--line);border-left:3px solid var(--accent);background:var(--panel);border-radius:8px;margin:12px 0;padding:20px}.issue.error{border-left-color:#ff9c89}.issue.warning{border-left-color:#f6d58f}.meta{color:var(--muted);font:12px monospace;overflow-wrap:anywhere}.title{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.badge{text-transform:uppercase;font:11px monospace;padding:4px 7px;border:1px solid var(--line);border-radius:4px}.error .badge{color:#ff9c89}.warning .badge{color:#f6d58f}h2{font-size:17px;margin:0}.issue p{margin:10px 0}.fix{color:var(--text)}details{margin-top:12px}summary{cursor:pointer;color:var(--accent)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 monospace;color:var(--muted)}footer{margin-top:40px;color:var(--muted);font-size:12px}#empty{padding:32px;text-align:center;border:1px dashed var(--line)}button{background:var(--panel);color:var(--accent);border:1px solid var(--line);border-radius:5px;padding:8px 16px;cursor:pointer}button:disabled{opacity:.4}nav{display:flex;gap:16px;align-items:center;margin-top:20px}@media(max-width:650px){main{padding:28px 16px}.stats{grid-template-columns:repeat(2,1fr)}.stat{padding:14px}}
</style></head><body><main><header><div class="eyebrow">AGENT TRACECHECK / DATA QUALITY</div><h1>Trust the trajectory.</h1><p>Inspect the evidence before it becomes a training signal.</p></header>
<section class="stats" aria-label="Summary" id="stats"></section>
<div class="toolbar"><input id="search" type="search" aria-label="Search findings" placeholder="Search rule, file, message…"><label>Severity <select id="severity"><option value="">All</option><option>error</option><option>warning</option><option>info</option></select></label><label>Rule <select id="rule"><option value="">All rules</option></select></label></div>
<p id="count" role="status" aria-live="polite"></p><section id="issues" aria-label="Findings"></section><nav aria-label="Results pages"><button id="prev">Previous</button><span id="page"></span><button id="next">Next</button></nav>
<footer>Local, deterministic analysis · No network requests · Reward/outcome warnings require policy review.<br>Reports contain source paths and diagnostics; reproductions contain original data. Review before sharing.</footer></main>
<script type="application/json" id="data">__REPORT_DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent), $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e};
for(const [key,label] of [['records','Records scanned'],['error','Errors'],['warning','Warnings'],['info','Informational']]){const e=el('div','','stat');e.append(el('strong',data.summary[key]),el('span',label));$('stats').append(e)}
for(const rule of [...new Set(data.issues.map(i=>i.rule))].sort()){$('rule').append(el('option',rule))}
let page=0,filtered=[];const size=50;
function draw(){const query=$('search').value.toLowerCase();filtered=data.issues.filter(i=>(!$('severity').value||i.severity===$('severity').value)&&(!$('rule').value||i.rule===$('rule').value)&&[i.rule,i.message,i.source.path,i.pointer].join(' ').toLowerCase().includes(query));
const pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages-1);$('issues').replaceChildren();$('count').textContent=filtered.length+' of '+data.issues.length+' findings';
if(!filtered.length){const e=el('div',data.issues.length?'No findings match these filters.':'No findings under the enabled rules.');e.id='empty';$('issues').append(e)}
for(const i of filtered.slice(page*size,(page+1)*size)){const card=el('article','','issue '+i.severity),head=el('div','','title');head.append(el('span',i.severity,'badge'),el('h2',i.rule));card.append(head,el('p',i.message),el('div',i.source.path+':'+i.source.line+' · '+i.source.pointer+i.pointer,'meta'),el('p','Fix: '+i.suggestion,'fix'));const d=el('details');d.append(el('summary','Evidence & reproduction'),el('pre',JSON.stringify({issue_id:i.id,record:i.source.record,record_sha256:i.record_sha256,related:i.related,details:i.details},null,2)),el('pre','agent-tracecheck repro report.json '+i.id+' --output repro.jsonl'));card.append(d);$('issues').append(card)}
$('page').textContent=(page+1)+' / '+pages;$('prev').disabled=page===0;$('next').disabled=page>=pages-1}
for(const id of ['search','severity','rule']){$(id).addEventListener('input',()=>{page=0;draw()})}$('prev').onclick=()=>{page--;draw()};$('next').onclick=()=>{page++;draw()};draw();
</script></body></html>"""
