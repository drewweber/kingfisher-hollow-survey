import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
const source=readFileSync(new URL('../report.py',import.meta.url),'utf8');
const script=source.split('PLOTLY_SCRIPT = """')[1].split('"""')[0];
function harness({plot=()=>Promise.resolve(),tables=false,inventoryLink=false,lazy=false}={}) {
  const elements=[],scripts=[],listeners={},timers=new Map();let timer=0;
  const document={activeElement:null};
  function element(tag='div') {
    const attrs={},events={};
    const e={tag,children:[],dataset:{},hidden:false,textContent:'',
      append(...children){this.children.push(...children);},
      setAttribute(k,v){attrs[k]=v;},getAttribute(k){return attrs[k];},removeAttribute(k){delete attrs[k];},
      addEventListener(k,fn){events[k]=fn;},click(){events.click?.();},
      before(node){this.panel=node;},remove(){this.removed=true;},
      focus(){document.activeElement=this;},closest(){return null;},
    }; elements.push(e); return e;
  }
  const charts=['a','b'].map(id=>Object.assign(element(),{id,dataset:{plotlySrc:`/${id}.js`}}));
  if(tables)charts.forEach(chart=>{
    const summary=element('summary'),table=element('details');table.querySelector=()=>summary;
    chart.table=table;chart.summary=summary;
    chart.closest=()=>({dataset:{chartTitle:chart.id},querySelector:selector=>selector==='[data-chart-table] summary'?summary:selector==='[data-chart-table]'?table:null});
  });
  if(inventoryLink)charts.forEach(chart=>{
    const link=element('a');link.href='/life-list/';link.textContent='Browse the Life List';
    chart.link=link;
    chart.closest=()=>({dataset:{chartTitle:chart.id},querySelector:selector=>selector==='[data-chart-link]'?link:null});
  });
  Object.assign(document,{querySelectorAll:()=>charts,getElementById:id=>charts.find(c=>c.id===id),
    createElement:element,head:{appendChild:s=>scripts.push(s)}});
  const window={__plotlyQueue:[],addEventListener:(k,fn)=>listeners[k]=fn};
  let intersect;
  class Observer {constructor(callback){intersect=callback;}observe(){}unobserve(){}}
  if(lazy)window.IntersectionObserver=Observer;
  const plots=[];
  function ready(){window.Plotly={newPlot:(...args)=>{plots.push(args);return plot(...args);},purge:()=>{}};scripts.find(s=>s.src==='__PLOTLY_CDN__'&&!s.removed).onload();}
  function payload(id){listeners['kh-plotly-payload']({detail:[id,[],{}]});scripts.find(s=>s.src===`/${id}.js`&&!s.removed)?.onload?.();}
  vm.runInNewContext(script,{window,document,Promise,Map,Set,IntersectionObserver:Observer,
    setTimeout:(fn,delay)=>{timers.set(++timer,{fn,delay});return timer;},clearTimeout:id=>timers.delete(id)});
  return {charts,scripts,window,plots,document,elements,ready,payload,timers,
    approach:chart=>intersect([{target:chart,isIntersecting:true}]),
    retry:chart=>chart.panel.children.find(e=>e.tag==='button'),
    status:chart=>chart.panel.children.find(e=>e.getAttribute('role')==='status')};
}
const settle=async()=>{await Promise.resolve();await Promise.resolve();};

test('CDN failure exposes retry; one retry recovers all waiting charts without duplicate library requests',async()=>{
 const h=harness();h.payload('a');h.payload('b');h.scripts[0].onerror();
 assert.match(h.status(h.charts[0]).textContent,/could not load/i);
 assert.equal(h.retry(h.charts[0]).hidden,false);
 h.retry(h.charts[0]).click();h.retry(h.charts[1]).click();
 assert.equal(h.scripts.filter(s=>s.src==='__PLOTLY_CDN__').length,2);
 h.ready();await settle();
 assert.equal(h.plots.length,2);
 assert.equal(h.charts[0].dataset.plotlyRendered,'true');
});
test('one failed payload can retry without disturbing a successful chart',async()=>{
 const h=harness();h.ready();h.payload('b');await settle();
 h.scripts.find(s=>s.src==='/a.js').onerror();
 assert.equal(h.charts[0].dataset.plotlyRendered,undefined);
 h.retry(h.charts[0]).click();h.payload('a');await settle();
 assert.equal(h.plots.length,2);
 assert.equal(h.scripts.filter(s=>s.src==='__PLOTLY_CDN__').length,1);
 assert.equal(h.charts[0].getAttribute('aria-busy'),'false');
});
test('rejected chart rendering is retryable and only marks success after resolution',async()=>{
 let fail=true;const h=harness({plot:()=>fail?Promise.reject(new Error('draw failure')):Promise.resolve()});
 h.ready();h.payload('a');await settle();
 assert.notEqual(h.charts[0].dataset.plotlyRendered,'true');
 assert.match(h.status(h.charts[0]).textContent,/draw/i);
 fail=false;h.retry(h.charts[0]).focus();h.retry(h.charts[0]).click();await settle();
 assert.equal(h.charts[0].dataset.plotlyRendered,'true');
 assert.equal(h.document.activeElement,h.charts[0]);
});
test('stalled resources time out with a usable retry instead of an endless loading state',()=>{
 const h=harness();const pending=[...h.timers.values()];
 assert.ok(pending.length);
 for(const {fn} of pending)fn();
 assert.equal(h.retry(h.charts[0]).hidden,false);
 assert.equal(h.charts[0].getAttribute('aria-busy'),'false');
});
test('loaded script without chart payload is treated as a recoverable failure',()=>{
 const h=harness();h.ready();h.scripts.find(s=>s.src==='/a.js').onload();
 assert.match(h.status(h.charts[0]).textContent,/data/i);
 assert.equal(h.retry(h.charts[0]).hidden,false);
});
test('static table remains available after a failure and its disclosure receives focus',()=>{
 const h=harness({tables:true});h.scripts[0].onerror();
 const chart=h.charts[0],data=chart.panel.children.find(e=>e.textContent==='View chart data');
 assert.equal(data.hidden,false);data.click();
 assert.equal(chart.table.open,true);
 assert.equal(h.document.activeElement,chart.summary);
});
test('lazy charts request no library or payload until they approach the viewport',()=>{
 const h=harness({lazy:true});assert.equal(h.scripts.length,0);
 h.approach(h.charts[0]);
 assert.deepEqual(h.scripts.map(s=>s.src),['__PLOTLY_CDN__','/a.js']);
 h.approach(h.charts[1]);
 assert.equal(h.scripts.filter(s=>s.src==='__PLOTLY_CDN__').length,1);
});

test('a newly visible chart does not silently retry a failed shared library',()=>{
 const h=harness({lazy:true});h.approach(h.charts[0]);h.scripts[0].onerror();
 h.approach(h.charts[1]);
 assert.equal(h.scripts.filter(s=>s.src==='__PLOTLY_CDN__').length,1);
 assert.equal(h.retry(h.charts[1]).hidden,false);
 h.retry(h.charts[1]).click();
 assert.equal(h.scripts.filter(s=>s.src==='__PLOTLY_CDN__').length,2);
});
test('finishing a retry preserves focus if the user tabs onto the data action',async()=>{
 let resolve;const h=harness({tables:true,plot:()=>new Promise(done=>{resolve=done;})});
 h.payload('a');h.scripts[0].onerror();h.retry(h.charts[0]).click();h.ready();
 const data=h.charts[0].panel.children.find(e=>e.textContent==='View chart data');
 data.focus();resolve();await settle();
 assert.equal(h.document.activeElement,h.charts[0].summary);
});


test('inventory link stays available through chart failure and successful retry',async()=>{
 const h=harness({inventoryLink:true});h.payload('a');h.scripts[0].onerror();
 const chart=h.charts[0];
 assert.match(h.status(chart).textContent,/summary and Life List are still available/);
 assert.doesNotMatch(h.status(chart).textContent,/data table/);
 assert.equal(chart.link.hidden,false);
 assert.equal(chart.link.href,'/life-list/');
 assert.equal(chart.panel.children.some(e=>e.textContent==='View chart data'),false);
 h.retry(chart).click();chart.link.focus();h.ready();await settle();
 assert.equal(chart.dataset.plotlyRendered,'true');
 assert.equal(h.document.activeElement,chart.link);
 assert.equal(chart.link.hidden,false);
});
