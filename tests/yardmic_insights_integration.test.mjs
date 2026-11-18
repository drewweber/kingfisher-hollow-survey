import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeYardmic } from '../src/yardmic.mjs';

const bird = (code, minutes, confirmed = 'auto') => ({code, name:`Bird ${code}`, minutes, confirmed});
const day = (date, species, listening_minutes = 600) => ({date,species,listening_minutes});

test('full summary integrates28 completed dates while retaining accepted and DST eligibility', () => {
  const payload={fetched_at:'2026-11-18T20:00:00Z',days:[
    day('2026-10-20',[bird('outside',['07:00'])]),
    day('2026-10-21',[bird('earliest',['07:00'])]),
    day('2026-11-01',[bird('ambiguous',['01:30']),bird('afterclock',['02:30'])]),
    day('2026-11-15',[bird('regular',['06:00','10:00','14:00']),bird('falsebird',['09:00'],false)]),
    day('2026-11-16',[bird('regular',['06:00','10:00','14:00'])]),
    day('2026-11-17',[bird('regular',['06:00','10:00','14:00'])]),
    day('2026-11-18',[bird('today',['07:00'])]),
  ]};
  const summary=summarizeYardmic(payload,{now:payload.fetched_at});
  const weekly=summary.insights.weekly;
  assert.deepEqual(weekly.species.map(x=>x.code).sort(),['afterclock','earliest','regular']);
  assert.deepEqual(weekly.species.find(x=>x.code==='earliest').detectedDays,[1,0,0,0]);
  assert.deepEqual(summary.insights.dayparts.species.find(x=>x.code==='regular').daysByPeriod,[3,3,3]);
  assert.equal(summary.insights.dayparts.species[0].group,'all-day');
  assert.equal(weekly.state,'insufficient');
  assert.deepEqual(summary.patterns.range,{start:'2026-11-11',end:'2026-11-17'});
});
