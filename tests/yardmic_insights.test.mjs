import assert from "node:assert/strict";
import test from "node:test";

import { summarizeYardmicInsights } from "../src/yardmic_insights.mjs";

const TODAY = "2026-11-18";
const bird = (code, minutes = ["07:00"], name = code) => ({ code, name, minutes });
const day = (date, species = [], listening_minutes = 100) => ({ date, listening_minutes, species });
const summarize = (days, today = TODAY, minutes = new Map(days.map((entry) => [entry.date, entry.species]))) =>
  summarizeYardmicInsights(days, minutes, today);
const dates = (firstDay, count) => Array.from({ length: count }, (_, index) =>
  `2026-11-${String(firstDay + index).padStart(2, "0")}`);
const countFixture = (previousDays, newestDays, counts) => [
  ...dates(4, previousDays).map((date, index) => day(date,
    Object.entries(counts).filter(([, [previous]]) => index < previous).map(([code]) => bird(code)))),
  ...dates(11, newestDays).map((date, index) => day(date,
    Object.entries(counts).filter(([, [, newest]]) => index < newest).map(([code]) => bird(code)))),
];
const rowByCode = (rows) => new Map(rows.map((row) => [row.code, row]));

test("four adjacent completed weeks exclude today and dates before the 28-day window", () => {
  const { weekly, dayparts } = summarize([
    day("2026-10-20", [bird("outside")]),
    day("2026-10-21", [bird("boundary")]),
    day("2026-10-27", [bird("boundary")]),
    day("2026-10-28", [bird("boundary")]),
    day("2026-11-03", [bird("boundary")]),
    day("2026-11-04", [bird("boundary")]),
    day("2026-11-10", [bird("boundary")]),
    day("2026-11-11", [bird("boundary")]),
    day("2026-11-17", [bird("boundary")]),
    day("2026-11-18", [bird("today")]),
    day("2026-11-19", [bird("future")]),
  ]);
  assert.deepEqual(weekly.weeks.map(({ range }) => range), [
    { start: "2026-10-21", end: "2026-10-27" },
    { start: "2026-10-28", end: "2026-11-03" },
    { start: "2026-11-04", end: "2026-11-10" },
    { start: "2026-11-11", end: "2026-11-17" },
  ]);
  assert.deepEqual(weekly.species, [{
    code: "boundary", name: "boundary", detectedDays: [2, 2, 2, 2],
    firstDetectedDate: "2026-10-21", change: "insufficient", deltaFraction: null,
  }]);
  assert.deepEqual(dayparts.coverage.range, { start: "2026-11-11", end: "2026-11-17" });
  assert.deepEqual(dayparts.species.map(({ code, detectedDates }) => [code, detectedDates]), [["boundary", 2]]);
});

test("calendar windows remain consecutive across year and leap-day boundaries", () => {
  assert.deepEqual(summarize([], "2027-01-02").weekly.weeks.map(({ range }) => range), [
    { start: "2026-12-05", end: "2026-12-11" },
    { start: "2026-12-12", end: "2026-12-18" },
    { start: "2026-12-19", end: "2026-12-25" },
    { start: "2026-12-26", end: "2027-01-01" },
  ]);
  const empty = summarize([], "2028-03-01");
  assert.deepEqual(empty.dayparts.coverage.missingDates,
    ["2028-02-23", "2028-02-24", "2028-02-25", "2028-02-26", "2028-02-27", "2028-02-28", "2028-02-29"]);
  assert.equal(empty.weekly.state, "insufficient");
  assert.equal(empty.dayparts.state, "insufficient");
  assert.deepEqual(empty.weekly.species, []);
  assert.deepEqual(empty.dayparts.species, []);
});

test("coverage separates no recording, missing, and detection-only dates using eligible minutes", () => {
  const days = [
    day("2026-11-11", [], 30),
    day("2026-11-12", [bird("ineligible")], 0),
    day("2026-11-13", [bird("accepted")], 0),
    day("2026-11-14", [bird("ineligible")], 40),
    day("2026-11-16", [bird("empty", [])], 0),
    day("2026-11-17", [], 50),
  ];
  const minutes = new Map([
    ["2026-11-13", [bird("accepted")]],
    ["2026-11-15", [bird("unreturned")]],
    ["2026-11-16", [bird("empty", [])]],
  ]);
  const { weekly, dayparts } = summarize(days.reverse(), TODAY, minutes);
  const expectedCoverage = {
    range: { start: "2026-11-11", end: "2026-11-17" },
    returnedDates: ["2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-16", "2026-11-17"],
    recordedDates: ["2026-11-11", "2026-11-13", "2026-11-14", "2026-11-17"],
    noRecordingDates: ["2026-11-12", "2026-11-16"],
    missingDates: ["2026-11-15"],
    detectionOnlyDates: ["2026-11-13"],
    listeningMinutes: 120,
  };
  assert.deepEqual(weekly.weeks[3], expectedCoverage);
  assert.deepEqual(dayparts.coverage, expectedCoverage);
  assert.deepEqual(weekly.species.map(({ code, detectedDays }) => [code, detectedDays]), [["accepted", [0, 0, 0, 1]]]);
  assert.deepEqual(dayparts.species.map(({ code }) => code), ["accepted"]);
});

test("repeated minutes and multiple periods give each date only one vote in each count", () => {
  const { weekly, dayparts } = summarize([
    day("2026-11-11", [bird("repeat", ["06:00", "06:00", "07:00", "10:00", "11:00", "14:00"])]),
    day("2026-11-12", [bird("repeat", ["06:01", "14:00", "17:59"])]),
    day("2026-11-13"),
  ]);
  assert.deepEqual(weekly.species[0].detectedDays, [0, 0, 0, 2]);
  assert.deepEqual(dayparts.species, [{
    code: "repeat", name: "repeat", daysByPeriod: [2, 1, 2], detectedDates: 2, group: "mixed",
  }]);
});

test("four recorded dates in both latest weeks enable supported changes and first-in-window", () => {
  const { weekly } = summarize(countFixture(4, 4, {
    increase: [1, 3], decrease: [4, 2], first: [0, 2], same: [2, 2], slight: [1, 2],
  }));
  assert.equal(weekly.state, "comparable");
  assert.equal(weekly.minimumRecordedDays, 4);
  const rows = rowByCode(weekly.species);
  for (const [code, change, delta] of [
    ["increase", "more-often", 0.5], ["decrease", "less-often", -0.5],
    ["first", "first-in-window", 0.5], ["same", "similar", 0], ["slight", "similar", 0.25],
  ]) {
    assert.equal(rows.get(code).change, change, code);
    assert.equal(rows.get(code).deltaFraction, delta, code);
  }
  assert.equal(rows.get("first").firstDetectedDate, "2026-11-11");
});

test("a comparable fraction uses only recorded dates, excluding returned empty and missing dates", () => {
  const days = countFixture(4, 4, { repeat: [1, 3] });
  days.push(day("2026-11-08", [], 0), day("2026-11-15", [], 0), day("2026-11-16", [], 0));
  const { weekly } = summarize(days);
  assert.equal(weekly.state, "comparable");
  assert.equal(weekly.species[0].deltaFraction, 0.5);
  assert.equal(weekly.species[0].change, "more-often");
  assert.equal(weekly.weeks[2].returnedDates.length, 5);
  assert.equal(weekly.weeks[2].recordedDates.length, 4);
  assert.equal(weekly.weeks[3].returnedDates.length, 6);
  assert.equal(weekly.weeks[3].recordedDates.length, 4);
});

test("a detection-only date can supply the fourth recorded date required for comparison", () => {
  const days = countFixture(4, 4, { regular: [1, 4] });
  days.find(({ date }) => date === "2026-11-14").listening_minutes = 0;
  const { weekly } = summarize(days);
  assert.equal(weekly.state, "comparable");
  assert.deepEqual(weekly.weeks[3].detectionOnlyDates, ["2026-11-14"]);
  assert.equal(weekly.species[0].change, "more-often");
  assert.equal(weekly.species[0].deltaFraction, 0.75);
});

test("either week with fewer than four recorded dates suppresses every trend classification", () => {
  for (const [previousDays, newestDays] of [[3, 4], [4, 3], [0, 4]]) {
    const { weekly } = summarize(countFixture(previousDays, newestDays, { repeat: [1, 3], first: [0, 2] }));
    assert.equal(weekly.state, "insufficient");
    assert.equal(weekly.species.length, 2);
    for (const row of weekly.species) {
      assert.equal(row.change, "insufficient");
      assert.equal(row.deltaFraction, null);
    }
  }
});

test("changes require both the percentage-point and absolute-date thresholds in the same direction", () => {
  for (const [previousDays, newestDays, previousCount, newestCount, change, delta] of [
    [4, 7, 3, 7, "more-often", 0.25],
    [7, 4, 7, 3, "less-often", -0.25],
    [4, 7, 1, 3, "similar", 3 / 7 - 1 / 4],
    [7, 4, 3, 1, "similar", 1 / 4 - 3 / 7],
    [7, 4, 2, 3, "similar", 3 / 4 - 2 / 7],
    [4, 7, 3, 2, "similar", 2 / 7 - 3 / 4],
    [4, 7, 4, 5, "similar", 5 / 7 - 1],
  ]) {
    const row = summarize(countFixture(previousDays, newestDays, { regular: [previousCount, newestCount] })).weekly.species[0];
    assert.equal(row.change, change, `${previousCount}/${previousDays} → ${newestCount}/${newestDays}`);
    assert.equal(row.deltaFraction, delta);
  }
});

test("first-in-window checks all older weeks and retains the earliest eligible date", () => {
  const days = [
    ...countFixture(4, 4, { returning: [0, 2], first: [0, 1] }),
    day("2026-10-28", [bird("returning")]),
    day("2026-10-21", [bird("returning")]),
  ];
  const rows = rowByCode(summarize(days.reverse()).weekly.species);
  assert.equal(rows.get("returning").change, "more-often");
  assert.equal(rows.get("returning").firstDetectedDate, "2026-10-21");
  assert.deepEqual(rows.get("returning").detectedDays, [1, 1, 0, 2]);
  assert.equal(rows.get("first").change, "first-in-window");
});

test("three recorded dates enable daypart groups while two dates force mixed", () => {
  const days = [day("2026-11-11", [bird("morning")]), day("2026-11-12", [bird("morning")])];
  const sparse = summarize(days).dayparts;
  assert.equal(sparse.state, "insufficient");
  assert.equal(sparse.minimumRecordedDays, 3);
  assert.equal(sparse.species[0].group, "mixed");
  const available = summarize([...days, day("2026-11-13")]).dayparts;
  assert.equal(available.state, "available");
  assert.equal(available.species[0].group, "morning");
  assert.deepEqual(available.species[0].daysByPeriod, [2, 0, 0]);
});

test("all-day grouping requires at least half the recorded dates, rounded up, in every period", () => {
  for (const [recordedDays, detectionDays, expected] of [[3, 2, "all-day"], [5, 2, "mixed"], [5, 3, "all-day"], [7, 3, "mixed"], [7, 4, "all-day"]]) {
    const days = dates(11, recordedDays).map((date, index) => day(date,
      index < detectionDays ? [bird("regular", ["06:00", "10:00", "14:00"])] : []));
    const row = summarize(days).dayparts.species[0];
    assert.equal(row.group, expected, `${detectionDays} of ${recordedDays} dates`);
    assert.deepEqual(row.daysByPeriod, [detectionDays, detectionDays, detectionDays]);
  }
});

test("a named period needs a unique greatest count, at least two dates, and at least half the total", () => {
  const periods = ["06:00", "10:00", "14:00"];
  const counts = { morning: [2, 1, 1], midday: [1, 2, 1], afternoon: [1, 1, 2], tie: [2, 2, 0], sparse: [1, 0, 0], diffuse: [3, 2, 2] };
  const days = dates(11, 5).map((date, index) => day(date,
    Object.entries(counts).map(([code, values]) => bird(code, periods.filter((_, period) => index < values[period])))));
  const rows = rowByCode(summarize(days).dayparts.species);
  for (const [code, group] of [["morning", "morning"], ["midday", "midday"], ["afternoon", "afternoon"], ["tie", "mixed"], ["sparse", "mixed"], ["diffuse", "mixed"]]) {
    assert.equal(rows.get(code).group, group, code);
    assert.deepEqual(rows.get(code).daysByPeriod, counts[code]);
  }
});

test("daypart boundaries include 06, 10 and 14 and exclude 18 and overnight-only detections", () => {
  const minutes = ["05:59", "06:00", "09:59", "10:00", "13:59", "14:00", "17:59", "18:00"];
  const { dayparts, weekly } = summarize([
    day("2026-11-11", minutes.map((minute) => bird(`bird${minute.replace(":", "")}`, [minute]))),
    day("2026-11-12"), day("2026-11-13"),
  ]);
  assert.deepEqual(dayparts.periods, [
    { id: "morning", label: "Morning", startHour: 6, endHour: 10 },
    { id: "midday", label: "Midday", startHour: 10, endHour: 14 },
    { id: "afternoon", label: "Afternoon", startHour: 14, endHour: 18 },
  ]);
  assert.deepEqual(dayparts.species.map(({ code, daysByPeriod }) => [code, daysByPeriod]), [
    ["bird0600", [1, 0, 0]], ["bird0959", [1, 0, 0]],
    ["bird1000", [0, 1, 0]], ["bird1359", [0, 1, 0]],
    ["bird1400", [0, 0, 1]], ["bird1759", [0, 0, 1]],
  ]);
  assert.equal(weekly.species.length, 8);
});

test("every species remains available with deterministic newest-count and name/code ordering", () => {
  const birds = [
    ...Array.from({ length: 32 }, (_, index) => bird(`bird${index}`, ["07:00"], `Bird ${String(index).padStart(2, "0")}`)),
    bird("alphab", ["07:00"], "Alpha Bird"), bird("alphaa", ["07:00"], "Alpha Bird"),
    bird("regular", ["07:00"], "Zulu Bird"),
  ];
  const days = [day("2026-11-11", birds.reverse()), day("2026-11-12", [bird("regular", ["07:00"], "Zulu Bird")]), day("2026-11-13")];
  const { weekly, dayparts } = summarize(days);
  assert.equal(weekly.species.length, 35);
  assert.equal(dayparts.species.length, 35);
  assert.deepEqual(weekly.species.slice(0, 4).map(({ code }) => code), ["regular", "alphaa", "alphab", "bird0"]);
  assert.deepEqual(dayparts.species.slice(0, 3).map(({ code }) => code), ["alphaa", "alphab", "bird0"]);
  assert.equal(dayparts.species.at(-1).code, "regular");
  assert.deepEqual(summarize(days.slice().reverse()), { weekly, dayparts });
});
