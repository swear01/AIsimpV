#!/usr/bin/env python3
"""Render a self-contained, read-only source comparison from frozen snapshots."""
import argparse
from difflib import unified_diff
from html import escape
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / 'experiments/freestyle_axilxbar'


def rows(side, name, source, marks):
    result = []
    for number, line in enumerate(source.splitlines(), 1):
        label = ', '.join(str(index + 1) for index, card in enumerate(marks)
                          if any(loc['file'] == f'{side}/{name}' and loc['start'] <= number <= loc['end']
                                 for loc in card[f'{side}_locations']))
        result.append(f'<div class="line" id="{side}-{name}-{number}">'
                      f'<span class="number">{number}</span><span class="mark">{escape(label)}</span>'
                      f'<code>{escape(line) or " "}</code></div>')
    return '\n'.join(result)


def validate(cards, sources):
    for card in cards:
        for side in ('original', 'candidate'):
            for loc in card[f'{side}_locations']:
                name = loc['file']
                if (name not in sources or not name.startswith(f'{side}/') or
                    not isinstance(loc['start'], int) or not isinstance(loc['end'], int) or
                    not 1 <= loc['start'] <= loc['end'] <= len(sources[name].splitlines())):
                    raise ValueError(f'invalid source location: {loc}')


def render(candidate, review, output, case=CASE):
    task = json.loads((case / 'task.json').read_text())
    sources = {f'original/{name.removeprefix("original/")}': (case / name).read_text()
               for name in task['files']}
    sources['original/task.json'] = (case / 'task.json').read_text()
    outputs = task.get('candidate_outputs', {
        'axilxbar_v': 'axilxbar.v', 'property_v': 'property.v',
        'explanation': 'explanation.md', 'environment_changes': 'environment.md'})
    explanation_name = outputs['explanation']
    environment_name = outputs['environment_changes']
    candidate_names = set(outputs.values())
    candidate_names.update(('frontend.txt', 'bound_frontend.txt'))
    sources.update({f'candidate/{name}': (candidate / name).read_text()
                    for name in sorted(candidate_names) if (candidate / name).is_file() and name != explanation_name})
    if (candidate / 'first-output/axilxbar.txt').is_file():
        sources['candidate/first-output/axilxbar.txt'] = (candidate / 'first-output/axilxbar.txt').read_text()
    cards = review['changes']
    validate(cards, sources)
    design_name = outputs['axilxbar_v']
    primary = next(name for name in sources if name.startswith('original/') and name.endswith('/axilxbar.v'))
    candidate_primary = f'candidate/{design_name}'
    sections = [(primary, candidate_primary)]
    used = {primary, candidate_primary}
    for name in sources:
        if name in used or name.startswith('candidate/'):
            continue
        candidate_key = f'candidate/{Path(name).name}'
        pair = (name, candidate_key) if candidate_key in sources and candidate_key not in used else (name,)
        sections.append(pair)
        used.update(pair)
    sections.extend((name,) for name in sources if name not in used)
    panes = []
    for section in sections:
        columns = []
        for key in section:
            side, name = key.split('/', 1)
            columns.append(f'<section class="codepane"><h3>{escape(key)}</h3>'
                           f'<div class="source">{rows(side, name, sources[key], cards)}</div></section>')
        panes.append(f'<details {"open" if primary in section else ""}>'
                     f'<summary>{escape(Path(section[0]).name)}</summary><div class="pair">{"".join(columns)}</div></details>')
    change_cards = []
    for index, card in enumerate(cards):
        change_cards.append(f'<article class="card" onclick="focusCard({index})" tabindex="0" '
                            f'onkeydown="if(event.key===\'Enter\')focusCard({index})">'
                            f'<h3>{index + 1}. {escape(card["title"])}</h3>'
                            f'<p>{escape(card["analysis"])}</p>'
                            f'<p><strong>Property：</strong>{escape(card["property_impact"])}</p>'
                            f'<p><strong>疑點：</strong>{escape(card["concern"])}</p>'
                            f'<p><strong>人工狀態：</strong>{escape(card.get("human_status", "未核對"))}</p>'
                            f'<p>{escape(card.get("human_note", ""))}</p>'
                            f'</article>')
    diff = ''.join(unified_diff(sources[primary].splitlines(True),
                                sources[candidate_primary].splitlines(True),
                                primary, candidate_primary))
    status = escape(review.get('frontend', 'NOT_RUN'))
    metadata = escape(review.get('metadata', ''))
    intro = escape(review.get('summary', ''))
    explanation = escape((candidate / explanation_name).read_text())
    environment = escape((candidate / environment_name).read_text())
    manual = escape(review.get('manual_note', '尚未人工核對'))
    locations = json.dumps([{'original': card['original_locations'], 'candidate': card['candidate_locations']}
                            for card in cards])
    html = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>RTL freestyle rewrite 審查</title>
<style>
:root {{font-family:system-ui,sans-serif;color:#182334;background:#f5f7fa}}
body {{margin:0}} header,main {{padding:1rem 1.4rem}} header {{background:#14283e;color:white}}
h1 {{margin:.2rem 0;font-size:1.5rem}} h2 {{margin:1.4rem 0 .5rem}} h3 {{margin:.3rem 0}}
p {{line-height:1.45}} .notice {{background:#fff4d4;padding:.7rem;border-left:4px solid #b77b00}}
.layout {{display:grid;grid-template-columns:minmax(240px,28%) 1fr;gap:1rem}}
.cards {{max-height:80vh;overflow:auto}} .card {{background:white;border:1px solid #cad3db;border-radius:7px;padding:.7rem;margin:.4rem 0;cursor:pointer}}
.card:hover,.card:focus {{border-color:#2367a2;outline:2px solid #a8c7e2}}
details {{background:white;border:1px solid #cad3db;border-radius:6px;margin:.4rem 0;padding:.5rem}}
summary {{cursor:pointer;font-weight:600}} .pair {{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem}}
.codepane {{min-width:0}} .source {{overflow:auto;max-height:62vh;background:#fdfdfd;border:1px solid #ddd;font:12px/1.4 ui-monospace,monospace}}
.line {{display:flex;white-space:pre;min-width:max-content}} .line.focus {{background:#fff0af}}
.number {{width:3.5rem;text-align:right;color:#718094;padding-right:.5rem;user-select:none}}
.mark {{width:2rem;color:#a94800;text-align:center;font-weight:bold}} code {{font:inherit}}
pre {{white-space:pre-wrap;overflow:auto;background:#eef2f5;padding:.8rem;max-height:60vh}}
@media(max-width:900px) {{.layout,.pair {{display:block}} .source {{max-height:45vh}}}}
</style>
<header><h1>axilxbar：自由改寫審查</h1><div>前端：{status}　{metadata}</div></header>
<main><p class="notice">此頁展示程式碼與解讀；前端通過及人工未見問題都不代表抽象正確。</p>
<p>{intro}</p><div class="layout"><aside><h2>概念改動</h2><div class="cards">{''.join(change_cards) or '<p>尚無標註</p>'}</div>
<h2>人工核對</h2><p>{manual}</p><h2>生成者說明</h2><pre>{explanation}</pre><h2>環境變動</h2><pre>{environment}</pre></aside>
<div><h2>完整原版與候選</h2>{''.join(panes)}<details><summary>一般 unified diff</summary><pre>{escape(diff)}</pre></details></div></div></main>
<script>const locations={locations};function focusCard(i){{document.querySelectorAll('.line.focus').forEach(x=>x.classList.remove('focus'));
for(const side of ['original','candidate']){{let first=null;for(const loc of locations[i][side]){{let name=loc.file.slice(side.length+1);
for(let n=loc.start;n<=loc.end;n++){{let e=document.getElementById(side+'-'+name+'-'+n);if(e){{e.classList.add('focus');first ??= e;}}}}
if(first){{first.closest('details').open=true;first.scrollIntoView({{block:'center'}});}}}}}}}}</script></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    render(args.candidate, json.loads(args.review.read_text()), args.out, args.case)
