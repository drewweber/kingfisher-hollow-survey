import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../assets/moth-explorer.js', import.meta.url), 'utf8');
class Element {
  constructor(tag='div') { this.tagName=tag.toUpperCase(); this.children=[]; this.handlers={}; this.dataset={}; this.value=''; this.open=false; this.disabled=true; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children=[...nodes]; }
  addEventListener(name, fn) { this.handlers[name]=fn; }
  async fire(name) { return this.handlers[name]?.(); }
}
function setup({search='', fail=false, back=false}={}) {
  const ids={};
  for (const id of ['moth-explorer','moth-search','moth-search-status','moth-search-results','moth-timing-result','moth-timing']) ids[id]=new Element(id==='moth-timing'?'details':'div');
  ids['moth-explorer'].dataset.src='/assets/moth-timing-version.json';
  if(back) ids['moth-timing-back']=new Element('a');
  const contextLinks=['/moths/timing/','/moths/targets/'].map(href=>Object.assign(new Element('a'),{href}));
  const data=Array.from({length:889},(_,i)=>({id:i+1,common_name:'Moth '+(i+1),scientific_name:'Taxon '+(i+1),monthly_records:[0,0,1,0,0,0,0,2,0,0,0,0],stages:[]}));
  const location={href:'https://example.org/moths/'+search,origin:'https://example.org',search,hash:''};
  const events={}; let requests=0; const pushes=[];
  vm.runInNewContext(source,{
    URL,URLSearchParams,location,
    document:{getElementById:id=>ids[id]||null,createElement:tag=>new Element(tag),querySelectorAll:()=>contextLinks},
    history:{pushState:(_,__,url)=>{pushes.push(url);const u=new URL(url,location.origin);location.search=u.search;location.hash=u.hash;}},
    window:{addEventListener:(name,fn)=>{events[name]=fn;}},
    fetch:async()=>{requests++;return {ok:!fail,json:async()=>data};},
  });
  return {ids,data,location,events,pushes,contextLinks,requests:()=>requests};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('payload waits for disclosure, searches all taxa and prints gaps as exact values',async()=>{
  const s=setup(); assert.equal(s.requests(),0);
  s.ids['moth-timing'].open=true; await s.ids['moth-timing'].fire('toggle');await settle();
  assert.equal(s.requests(),1);assert.equal(s.ids['moth-search'].disabled,false);
  s.ids['moth-search'].value='Moth 889';await s.ids['moth-search'].fire('input');
  const button=s.ids['moth-search-results'].children[0].children[0];await button.fire('click');
  const months=s.ids['moth-timing-result'].children[3];
  assert.equal(months.children.length,12);
  assert.equal(months.children[0].children[1].textContent,'0 records');
  assert.equal(months.children[7].children[1].textContent,'2 records');
  assert.match(s.pushes[0],/moth=889#mol?th-timing/);
});
test('deep-link selection preserves seasonal return context and browser back clears selection',async()=>{
  const s=setup({search:'?from=%2Fseasons%2Fautumn%2F%3Fcompare%3Dyears%23evidence&moth=889'});await settle();
  assert.equal(s.ids['moth-timing'].open,true);
  assert.equal(s.ids['moth-search'].value,'Moth 889');
  s.location.search='?from=%2Fseasons%2Fautumn%2F';s.events.popstate();
  assert.equal(s.ids['moth-timing-result'].children.length,0);
});
test('failed payload gives native-access direction',async()=>{
  const s=setup({fail:true});s.ids['moth-timing'].open=true;await s.ids['moth-timing'].fire('toggle');await settle();
  assert.match(s.ids['moth-search-status'].textContent,/Browse all monthly records/);
});
test('native page return preserves moth and season but does not become an external redirect',()=>{
  const s=setup({search:'?from=https%3A%2F%2Fevil.example&moth=12',back:true});
  assert.match(s.ids['moth-timing-back'].href,/^\/moths\/\?/);
  assert.match(s.ids['moth-timing-back'].href,/moth=12/);
});

test('Back removes stale moth and seasonal keys from both native exploration links',async()=>{
  const s=setup({search:'?from=%2Fseasons%2Fautumn%2F'});
  s.ids['moth-timing'].open=true;await s.ids['moth-timing'].fire('toggle');await settle();
  s.ids['moth-search'].value='Moth 889';await s.ids['moth-search'].fire('input');
  await s.ids['moth-search-results'].children[0].children[0].fire('click');
  for(const link of s.contextLinks){
    const url=new URL(link.href,s.location.origin);
    assert.equal(url.searchParams.get('moth'),'889');
    assert.equal(url.searchParams.get('from'),'/seasons/autumn/');
  }
  s.location.search='?from=%2Fseasons%2Fautumn%2F';s.events.popstate();
  assert.equal(s.ids['moth-timing-result'].children.length,0);
  for(const link of s.contextLinks){
    const url=new URL(link.href,s.location.origin);
    assert.equal(url.searchParams.has('moth'),false);
    assert.equal(url.searchParams.get('from'),'/seasons/autumn/');
  }
  s.location.search='';s.events.popstate();
  assert.deepEqual(s.contextLinks.map(link=>link.href),['/moths/timing/','/moths/targets/']);
});
