import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { summarizeYardmic } from "../src/yardmic.mjs";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/yardmic-2026-11-15--18.json", import.meta.url)));
const kingfisher = (minutes, confirmed = "reviewed") => ({
  code: "belkin1", name: "Belted Kingfisher", confirmed, minutes,
});
const day = (date, species = []) => ({ date, listening_minutes: 800, species });

test("derives the eight accepted recent species from the sample and omits the rejected sparrow", () => {
  const summary = summarizeYardmic(fixture, { now: "2026-11-18T17:47:58Z" });
  const recent = summary.recentHour;
  assert.equal(recent.state, "available");
  assert.equal(recent.start, "2026-11-18T16:47:00.000Z");
  assert.deepEqual(
    recent.species.map(({ code, status, latestLocal, detectedMinutes }) => [code, status, latestLocal.slice(-5), detectedMinutes]),
    [
      ["whbnut", "auto", "12:45", 4],
      ["rebwoo", "reviewed", "12:43", 2],
      ["rebnut", "reviewed", "12:41", 1],
      ["amegfi", "reviewed", "12:38", 12],
      ["bkcchi", "auto", "12:36", 8],
      ["tuftit", "reviewed", "12:34", 16],
      ["haiwoo", "auto", "12:30", 4],
      ["blujay", "auto", "12:23", 4],
    ],
  );
  for (const species of recent.species) {
    assert.equal(species.minuteStarts.length, species.detectedMinutes);
    assert.deepEqual(species.minuteStarts, [...new Set(species.minuteStarts)].sort());
    assert.equal(species.minuteStarts.at(-1), species.latestAt);
    for (const minute of species.minuteStarts) {
      assert.match(minute, /T\d{2}:\d{2}:00\.000Z$/);
      assert.ok(minute > recent.start && minute <= recent.end);
    }
  }
  assert.equal(summary.latestDetectionAt, "2026-11-18T17:45:00.000Z");
  assert.deepEqual(summary.range.requested, { start: "2026-10-19", end: "2026-11-18" });
  assert.deepEqual(summary.range.returned, { start: "2026-11-15", end: "2026-11-18" });
  assert.deepEqual(summary.dailyEffort.at(-1), { date: "2026-11-18", listeningMinutes: 755 });
  assert.deepEqual(summary.kingfisher, {
    state: "detected",
    latestAt: "2026-11-18T15:56:00.000Z",
    latestLocal: "2026-11-18T10:56",
    status: "reviewed",
    elapsedMinutes: 111,
    complete: false,
    ambiguous: false,
  });
});

test("derives clock-hour recurrence and overnight counts from completed Eastern dates", () => {
  const summary = summarizeYardmic(fixture, { now: "2026-11-18T17:47:58Z" });
  assert.deepEqual(summary.patterns.range, { start: "2026-11-11", end: "2026-11-17" });
  assert.deepEqual(summary.patterns.dates, ["2026-11-15", "2026-11-16", "2026-11-17"]);
  assert.deepEqual(summary.patterns.recurringHour, {
    code: "bkcchi",
    name: "Black-capped Chickadee",
    hour: 15,
    dates: 3,
    minutesByDate: [
      { date: "2026-11-15", detectedMinutes: 49 },
      { date: "2026-11-16", detectedMinutes: 46 },
      { date: "2026-11-17", detectedMinutes: 48 },
    ],
  });
  assert.deepEqual(summary.patterns.overnight.map(({ name, dates, detectedMinutes }) => [name, dates, detectedMinutes]), [
    ["Barred Owl", 2, 5],
    ["Canada Goose", 2, 3],
    ["Northern Saw-whet Owl", 2, 2],
  ]);
});

test("species-hour composition gives each completed Eastern date one vote per hour", () => {
  const payload = { days: [
    day("2026-11-10", [kingfisher(["06:00"])]),
    day("2026-11-11", [kingfisher(["05:01", "05:01", "05:02", "08:45"])]),
    day("2026-11-17", [
      kingfisher(["05:59", "23:59"], "auto"),
      { code: "houspa", name: "House Sparrow", confirmed: false, minutes: ["06:00"] },
      { code: "blujay", name: "Blue Jay", confirmed: "reviewed", minutes: [] },
    ]),
    day("2026-11-18", [
      kingfisher(["06:00"]),
      { code: "bkcchi", name: "Black-capped Chickadee", confirmed: "auto", minutes: ["07:00"] },
    ]),
  ] };
  const { patterns } = summarizeYardmic(payload, { now: "2026-11-18T17:00:00Z" });
  assert.deepEqual(patterns.range, { start: "2026-11-11", end: "2026-11-17" });
  assert.deepEqual(patterns.dates, ["2026-11-11", "2026-11-17"]);
  assert.deepEqual(patterns.speciesHours, [{
    code: "belkin1", name: "Belted Kingfisher", detectedDates: 2, peakHour: 5,
    daysByHour: [0, 0, 0, 0, 0, 2, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
  }]);

  const withEmptyDates = summarizeYardmic({ days: [
    ...payload.days,
    ...["2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16"].map((date) => day(date)),
  ] }, { now: "2026-11-18T17:00:00Z" });
  assert.deepEqual(withEmptyDates.patterns.range, patterns.range);
  assert.deepEqual(withEmptyDates.patterns.speciesHours, patterns.speciesHours);
});

test("species-hour composition includes every detected species with all 24 clock hours", () => {
  const species = Array.from({ length: 32 }, (_, index) => ({
    code: `bird${index}`, name: `Bird ${index}`, confirmed: "auto", minutes: ["07:15"],
  }));
  const { patterns } = summarizeYardmic({ days: [day("2026-11-17", species)] }, {
    now: "2026-11-18T17:00:00Z",
  });
  assert.equal(patterns.speciesHours.length, 32);
  assert.deepEqual(new Set(patterns.speciesHours.map(({ code }) => code)), new Set(species.map(({ code }) => code)));
  for (const row of patterns.speciesHours) {
    assert.deepEqual(row.daysByHour, [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    assert.equal(row.detectedDates, 1);
    assert.equal(row.peakHour, 7);
  }
});

test("species-hour composition orders by earliest peak, detected dates, name, then code", () => {
  const bird = (code, name, minutes) => ({ code, name, minutes, confirmed: "reviewed" });
  const days = [
    day("2026-11-15", [
      bird("late", "Late Bird", ["20:10"]),
      bird("zulu", "Zulu Bird", ["06:10"]),
      bird("alphab", "Alpha Bird", ["06:10"]),
      bird("alphaa", "Alpha Bird", ["06:10"]),
      bird("broad", "Broad Bird", ["06:10", "08:10"]),
      bird("early", "Early Bird", ["00:10"]),
    ]),
    day("2026-11-17", [bird("broad", "Broad Bird", ["06:10", "08:10"])]),
  ];
  const options = { now: "2026-11-18T17:00:00Z" };
  const { speciesHours } = summarizeYardmic({ days }, options).patterns;
  assert.deepEqual(speciesHours.map(({ code, peakHour, detectedDates }) => [code, peakHour, detectedDates]), [
    ["early", 0, 1], ["broad", 6, 2], ["alphaa", 6, 1], ["alphab", 6, 1], ["zulu", 6, 1], ["late", 20, 1],
  ]);
  const reversed = days.slice().reverse().map((entry) => ({ ...entry, species: entry.species.slice().reverse() }));
  assert.deepEqual(summarizeYardmic({ days: reversed }, options).patterns.speciesHours, speciesHours);
});

test("species-hour composition keeps invalid clock-change minutes ineligible", () => {
  for (const { date, now, invalidMinute, eligibleMinutes, expectedHours } of [
    { date: "2026-03-08", now: "2026-03-09T16:00:00Z", invalidMinute: "02:30", eligibleMinutes: ["01:30", "03:30"], expectedHours: [1, 3] },
    { date: "2026-11-01", now: "2026-11-02T17:00:00Z", invalidMinute: "01:30", eligibleMinutes: ["00:30", "02:30"], expectedHours: [0, 2] },
  ]) {
    const { speciesHours } = summarizeYardmic({ days: [day(date, [
      kingfisher([invalidMinute]),
      { code: "blujay", name: "Blue Jay", confirmed: "auto", minutes: [...eligibleMinutes, invalidMinute] },
    ])] }, { now }).patterns;
    assert.equal(speciesHours.length, 1);
    assert.equal(speciesHours[0].code, "blujay");
    assert.equal(speciesHours[0].detectedDates, 1);
    assert.equal(speciesHours[0].peakHour, expectedHours[0]);
    assert.deepEqual(speciesHours[0].daysByHour.flatMap((count, hour) => count ? [[hour, count]] : []),
      expectedHours.map((hour) => [hour, 1]));
  }
});

test("pending confirmation remains invalid input for composition summaries", () => {
  assert.throws(() => summarizeYardmic({ days: [
    day("2026-11-17", [kingfisher(["07:10"], "pending")]),
  ] }, { now: "2026-11-18T17:00:00Z" }), /Invalid YardMic minute data/);
});

test("includes both Eastern dates in a midnight window and excludes the cutoff and future minutes", () => {
  const payload = { fetched_at: "2026-11-18T05:10:00Z", days: [
    day("2026-11-17", [kingfisher(["23:10", "23:11", "23:59"])]),
    day("2026-11-18", [kingfisher(["00:05", "00:05", "00:11"], "auto")]),
  ] };
  const summary = summarizeYardmic(payload, { now: "2026-11-18T05:10:00Z" });
  assert.equal(summary.recentHour.state, "available");
  assert.deepEqual(summary.recentHour.species, [{
    code: "belkin1", name: "Belted Kingfisher", status: "auto",
    latestAt: "2026-11-18T05:05:00.000Z", latestLocal: "2026-11-18T00:05", detectedMinutes: 3,
    minuteStarts: [
      "2026-11-18T04:11:00.000Z", "2026-11-18T04:59:00.000Z", "2026-11-18T05:05:00.000Z",
    ],
  }]);
  assert.equal(summary.kingfisher.elapsedMinutes, 5);
});

test("a dense hour fills sixty chronological slots, including an exact end minute", () => {
  const minutes = [
    "11:30",
    ...Array.from({ length: 29 }, (_, index) => "11:" + (index + 31)),
    ...Array.from({ length: 32 }, (_, index) => "12:" + String(index).padStart(2, "0")),
  ];
  const summary = summarizeYardmic({ fetched_at: "2026-11-18T17:30:00Z", days: [
    day("2026-11-18", [kingfisher(minutes)]),
  ] }, { now: "2026-11-18T17:30:00Z" });
  const { detectedMinutes, minuteStarts } = summary.recentHour.species[0];
  assert.equal(detectedMinutes, 60);
  assert.deepEqual(minuteStarts.map((minute) => (Date.parse(minute) - Date.parse("2026-11-18T16:31:00Z")) / 60_000),
    Array.from({ length: 60 }, (_, index) => index));
});

test("reports a missing current date and keeps a limited no-match distinct from unavailable history", () => {
  const now = "2026-11-18T05:10:00Z";
  const partial = summarizeYardmic({ fetched_at: now, days: [day("2026-11-17", [kingfisher(["23:59"], false)])] }, { now });
  assert.equal(partial.recentHour.state, "partial");
  assert.deepEqual(partial.recentHour.species, []);
  assert.equal(partial.kingfisher.state, "no-match");
  assert.equal(partial.kingfisher.complete, false);

  const missing = summarizeYardmic({ fetched_at: "2026-11-18T17:00:00Z", days: [day("2026-11-17")] }, { now: "2026-11-18T17:00:00Z" });
  assert.equal(missing.recentHour.state, "unavailable");
  const empty = summarizeYardmic(null, { now });
  assert.equal(empty.kingfisher.state, "unavailable");
  assert.equal(empty.range.returned, null);
});

test("a fall-back wall minute cannot produce an exact detection or a no-match", () => {
  const summary = summarizeYardmic({ fetched_at: "2026-11-01T07:15:00Z", days: [
    day("2026-11-01", [
      kingfisher(["00:50", "01:20"]),
      { code: "blujay", name: "Blue Jay", confirmed: "auto", minutes: ["01:45", "02:05"] },
    ]),
  ] }, { now: "2026-11-01T07:15:00Z" });
  assert.equal(summary.recentHour.ambiguous, true);
  assert.equal(summary.recentHour.state, "partial");
  assert.deepEqual(summary.recentHour.species.map(({ code, minuteStarts }) => [code, minuteStarts]),
    [["blujay", ["2026-11-01T07:05:00.000Z"]]]);
  assert.equal(summary.kingfisher.state, "unavailable");
  assert.equal(summary.kingfisher.ambiguous, true);
  assert.equal(summary.kingfisher.latestAt, null);
});

test("a nonexistent spring-forward minute cannot produce a timestamp", () => {
  const summary = summarizeYardmic({ fetched_at: "2026-03-08T07:30:00Z", days: [
    day("2026-03-08", [kingfisher(["01:45", "02:50"])]),
  ] }, { now: "2026-03-08T07:30:00Z" });
  assert.equal(summary.kingfisher.latestAt, "2026-03-08T06:45:00.000Z");
  assert.equal(summary.recentHour.species[0].detectedMinutes, 1);
  assert.deepEqual(summary.recentHour.species[0].minuteStarts, ["2026-03-08T06:45:00.000Z"]);
});
