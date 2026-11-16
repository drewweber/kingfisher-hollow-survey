#!/usr/bin/env python3
"""Generate offline inventory fixtures; open them in a browser and run the benchmark.

Example: python scripts/prepare_inventory_benchmark.py /tmp/inventory-before
No network calls or production writes. The 10k fixture repeats cached species and
is a scaling surrogate, not a larger biological inventory. Keep baseline output
before changing the controller so both runs use the same cached data and CSS.
"""
import argparse
import ast
import json
from pathlib import Path
import shutil
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import report

BENCHMARK = r'''
const run=document.getElementById('benchmark-run'),out=document.getElementById('benchmark-output');
const painted=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
run.addEventListener('click',async()=>{
  run.disabled=true;
  const samples=[],search=document.getElementById('ll-search');
  // Broad, narrow, empty and no-match results exercise collapse and expansion.
  const queries=['moth','','luna','','zzzz-no-match','','a',''];
  for(let round=0;round<5;round++)for(const query of queries){
    search.value=query;
    const start=performance.now();
    search.dispatchEvent(new Event('input',{bubbles:true}));
    const handlerMs=performance.now()-start;
    await painted();
    samples.push({query,handlerMs,paintOpportunityMs:performance.now()-start});
  }
  const summary=key=>{const values=samples.map(x=>x[key]).sort((a,b)=>a-b);
    return {median:values[Math.floor(values.length/2)],p95:values[Math.ceil(values.length*.95)-1],max:values.at(-1)};};
  const navigation=performance.getEntriesByType('navigation')[0];
  out.textContent=JSON.stringify({fixtureRows:FIXTURE_ROWS,userAgent:navigator.userAgent,
    viewport:[innerWidth,innerHeight],initMs:window.inventoryInitMs,
    domContentLoadedMs:navigation.domContentLoadedEventEnd,
    liveRows:document.querySelectorAll('.ll-row').length,
    liveElements:document.querySelectorAll('*').length,
    handlerMs:summary('handlerMs'),paintOpportunityMs:summary('paintOpportunityMs'),samples},null,2);
  run.disabled=false;
});
'''

def build(output, controller_ref=None):
    controller = report.LIFE_LIST_SCRIPT
    if controller_ref:
        source = subprocess.check_output(["/usr/bin/git", "show", controller_ref + ":report.py"], text=True)
        for statement in ast.parse(source).body:
            if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "LIFE_LIST_SCRIPT" for target in statement.targets):
                controller = ast.literal_eval(statement.value)
                break
        else:
            raise ValueError("No life-list controller in " + controller_ref)
    output.mkdir(parents=True, exist_ok=True)
    life = report.analyze.life_list(report.analyze.overview_observations(
        report.analyze.load_property(), report.analyze.load_birds()))
    shutil.copy(Path(__file__).resolve().parents[1] / 'public/assets/survey.css', output / 'survey.css')
    (output / 'life-list').mkdir(exist_ok=True)
    for count in (len(life), 10000):
        data = pd.concat([life] * ((count + len(life) - 1) // len(life)), ignore_index=True).iloc[:count].copy()
        body = report.life_list_body(data, dark=True).replace('href="/life-list/', 'href="life-list/')
        if hasattr(report, 'life_list_csv'):
            content = report.life_list_csv(data)
            (output / 'life-list' / report.inventory_csv_filename(content)).write_text(content)
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Inventory benchmark</title><link rel="stylesheet" href="survey.css">'
                '</head><body><main><h1>Inventory benchmark: ' + str(count) + ' rows</h1>'
                '<button id="benchmark-run" type="button">Run benchmark</button>'
                '<pre id="benchmark-output">Ready</pre>' + body + '</main><script>'
                'const inventoryStart=performance.now();' + controller +
                'window.inventoryInitMs=performance.now()-inventoryStart;</script><script>' +
                BENCHMARK.replace('FIXTURE_ROWS', str(count)) + '</script></body></html>')
        (output / f'{count}.html').write_text(html)
        # Full SSR fixture without enhancement verifies the no-JS fallback.
        (output / f'{count}-nojs.html').write_text(html.split('<script>')[0] + '</body></html>')
    print(json.dumps({'output': str(output), 'cached_inventory_rows':len(life)}))

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--controller-ref', help='Use another Git revision controller with identical current markup/CSS')
    args = parser.parse_args()
    build(args.output, args.controller_ref)
