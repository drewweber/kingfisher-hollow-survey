import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {normalizedComparison,comparisonUrl}=require('../assets/seasons/seasonal.js');
const periods=['2024–25','2025–26'];
test('comparison accepts only known local periods and all years',()=>{
 assert.equal(normalizedComparison('?compare=years',periods),'years');
 assert.equal(normalizedComparison('?compare=2025%E2%80%9326',periods),'2025–26');
 for(const value of ['https://evil.example','2026','all','']) assert.equal(normalizedComparison('?compare='+value,periods),'all');
});
test('shareable comparison preserves selected chapter and passage and clears in one step',()=>{
 const initial='https://survey.kingfisher-hollow.com/seasons/winter/#evidence-pine';
 assert.equal(comparisonUrl(initial,'years',periods),'/seasons/winter/?compare=years#evidence-pine');
 assert.equal(comparisonUrl(initial,'2025–26',periods),'/seasons/winter/?compare=2025%E2%80%9326#evidence-pine');
 assert.equal(comparisonUrl(initial+'?bad','unknown',periods),'/seasons/winter/#evidence-pine?bad');
 assert.equal(comparisonUrl('https://survey.kingfisher-hollow.com/seasons/winter/?compare=years#evidence-pine','all',periods),'/seasons/winter/#evidence-pine');
});

import vm from 'node:vm';
import fs from 'node:fs';
test('real controller restores Back, keeps source records and propagates comparison return',()=>{
 const listeners={}, selectListeners={}, resetListeners={};
 const controls={hidden:true};
 const select={options:[{value:'all'},{value:'years'},...periods.map(value=>({value}))],value:'all', addEventListener:(e,fn)=>selectListeners[e]=fn,focus(){this.focused=true;}};
 const reset={addEventListener:(e,fn)=>resetListeners[e]=fn};
 const pooled=[{hidden:false}];
 const bands=periods.map(year=>({dataset:{year},hidden:false}));
 const empty={hidden:true};
 const calendars=[{open:false,querySelector:()=>empty,querySelectorAll:()=>bands}];
 const status={textContent:''};
 const link={href:'/plants/?from=%2Fseasons%2Fwinter%2F%23evidence-pine', getAttribute(){return this.href;},setAttribute(name,value){this.href=value;}};
 const sources=[{hidden:false}];
 const doc={querySelector:s=>({'.comparison-controls':controls,'#comparison-mode':select,'#comparison-status':status,'.reset-comparison':reset})[s],querySelectorAll:s=>({'.pooled-calendar':pooled,'.year-calendar':calendars,'.year-band':bands,'a[href*="?from="]':[link],'.landscape img, .detail-photo img, .opening-detail img':[],'.source-records':sources})[s]||[]};
 const loc=new URL('https://survey.kingfisher-hollow.com/seasons/winter/?compare=years#evidence-pine');
 const stack=[];
 const context={document:doc,location:loc,URL,URLSearchParams,history:{pushState(a,b,path){stack.push(loc.href);loc.href=new URL(path,loc).href;}},addEventListener:(e,fn)=>listeners[e]=fn};
 vm.runInNewContext(fs.readFileSync(new URL('../assets/seasons/seasonal.js',import.meta.url),'utf8'),context);
 assert.equal(controls.hidden,false); assert.equal(select.value,'years'); assert.equal(calendars[0].open,true); assert.equal(pooled[0].hidden,true);
 assert.equal(new URL(link.href,loc).searchParams.get('from'),'/seasons/winter/?compare=years#evidence-pine');
 select.value='2025–26';selectListeners.change();
 assert.equal(loc.search,'?compare=2025%E2%80%9326'); assert.equal(bands[0].hidden,true);assert.equal(bands[1].hidden,false);
 loc.href=stack.pop(); listeners.popstate(); assert.equal(select.value,'years'); assert.equal(bands[0].hidden,false);
 resetListeners.click({preventDefault(){}}); assert.equal(loc.search,''); assert.equal(select.value,'all');assert.equal(pooled[0].hidden,false);assert.equal(select.focused,true);
 assert.equal(sources[0].hidden,false); assert.equal(new URL(link.href,loc).searchParams.get('from'),'/seasons/winter/#evidence-pine');
});

test('legacy voucher links reveal their native source disclosures',()=>{
 const events={};
 const appendix={tagName:'DETAILS',open:false,parentElement:null};
 const voucher={tagName:'DETAILS',open:false,parentElement:appendix,scrollIntoView(){this.scrolled=true;}};
 const doc={querySelector:()=>null,querySelectorAll:()=>[],getElementById:id=>id==='evidence-pine'?voucher:null};
 const context={document:doc,location:{hash:'#evidence-pine'},addEventListener:(event,fn)=>events[event]=fn};
 vm.runInNewContext(fs.readFileSync(new URL('../assets/seasons/seasonal.js',import.meta.url),'utf8'),context);
 assert.equal(appendix.open,true);assert.equal(voucher.open,true);assert.equal(voucher.scrolled,true);
 appendix.open=false;voucher.open=false;events.hashchange();
 assert.equal(appendix.open,true);assert.equal(voucher.open,true);
});
