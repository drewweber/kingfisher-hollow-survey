import { Temporal } from "@js-temporal/polyfill";

const WEEKLY_MINIMUM_DAYS = 4;
const DAYPART_MINIMUM_DAYS = 3;
const PERIODS = [
  { id: "morning", label: "Morning", startHour: 6, endHour: 10 },
  { id: "midday", label: "Midday", startHour: 10, endHour: 14 },
  { id: "afternoon", label: "Afternoon", startHour: 14, endHour: 18 },
];

function byNameAndCode(left, right) {
  return left.name.localeCompare(right.name) || left.code.localeCompare(right.code);
}

function weekCoverage(start, daysByDate, relevantMinutes) {
  const coverage = {
    range: { start: start.toString(), end: start.add({ days: 6 }).toString() },
    returnedDates: [],
    recordedDates: [],
    noRecordingDates: [],
    missingDates: [],
    detectionOnlyDates: [],
    listeningMinutes: 0,
  };
  for (let offset = 0; offset < 7; offset += 1) {
    const date = start.add({ days: offset }).toString();
    const day = daysByDate.get(date);
    if (!day) {
      coverage.missingDates.push(date);
      continue;
    }
    coverage.returnedDates.push(date);
    coverage.listeningMinutes += day.listening_minutes;
    const hasDetection = (relevantMinutes.get(date) ?? []).some(({ minutes }) => minutes.length > 0);
    if (day.listening_minutes > 0 || hasDetection) {
      coverage.recordedDates.push(date);
      if (day.listening_minutes === 0) coverage.detectionOnlyDates.push(date);
    } else {
      coverage.noRecordingDates.push(date);
    }
  }
  return coverage;
}

function weeklySummary(weeks, relevantMinutes) {
  const comparable = weeks[2].recordedDates.length >= WEEKLY_MINIMUM_DAYS
    && weeks[3].recordedDates.length >= WEEKLY_MINIMUM_DAYS;
  const species = new Map();
  for (const [weekIndex, week] of weeks.entries()) {
    for (const date of week.recordedDates) {
      for (const { code, name, minutes } of relevantMinutes.get(date) ?? []) {
        if (!minutes.length) continue;
        const entry = species.get(code) ?? {
          code, name, firstDetectedDate: date, datesByWeek: Array.from({ length: 4 }, () => new Set()),
        };
        entry.datesByWeek[weekIndex].add(date);
        species.set(code, entry);
      }
    }
  }
  const rows = [...species.values()].map(({ code, name, firstDetectedDate, datesByWeek }) => {
    const detectedDays = datesByWeek.map((dates) => dates.size);
    let change = "insufficient";
    let deltaFraction = null;
    if (comparable) {
      deltaFraction = detectedDays[3] / weeks[3].recordedDates.length
        - detectedDays[2] / weeks[2].recordedDates.length;
      const deltaDays = detectedDays[3] - detectedDays[2];
      if (detectedDays[3] > 0 && detectedDays.slice(0, 3).every((count) => count === 0)) {
        change = "first-in-window";
      } else if (deltaFraction >= 0.25 && deltaDays >= 2) {
        change = "more-often";
      } else if (deltaFraction <= -0.25 && deltaDays <= -2) {
        change = "less-often";
      } else {
        change = "similar";
      }
    }
    return { code, name, detectedDays, firstDetectedDate, change, deltaFraction };
  });
  return {
    state: comparable ? "comparable" : "insufficient",
    minimumRecordedDays: WEEKLY_MINIMUM_DAYS,
    weeks,
    species: rows.sort((left, right) => right.detectedDays[3] - left.detectedDays[3] || byNameAndCode(left, right)),
  };
}

function daypartGroup(counts, recordedDays) {
  if (recordedDays < DAYPART_MINIMUM_DAYS) return "mixed";
  const allDayMinimum = Math.max(2, Math.ceil(recordedDays / 2));
  if (counts.every((count) => count >= allDayMinimum)) return "all-day";
  const highest = Math.max(...counts);
  const total = counts.reduce((sum, count) => sum + count, 0);
  if (highest >= 2 && highest >= total / 2 && counts.filter((count) => count === highest).length === 1) {
    return PERIODS[counts.indexOf(highest)].id;
  }
  return "mixed";
}

function daypartSummary(coverage, relevantMinutes) {
  const species = new Map();
  for (const date of coverage.recordedDates) {
    for (const { code, name, minutes } of relevantMinutes.get(date) ?? []) {
      const presentPeriods = new Set();
      for (const minute of minutes) {
        const hour = Number(minute.slice(0, 2));
        const period = PERIODS.findIndex(({ startHour, endHour }) => hour >= startHour && hour < endHour);
        if (period !== -1) presentPeriods.add(period);
      }
      if (!presentPeriods.size) continue;
      const entry = species.get(code) ?? {
        code, name, dates: new Set(), datesByPeriod: PERIODS.map(() => new Set()),
      };
      entry.dates.add(date);
      for (const period of presentPeriods) entry.datesByPeriod[period].add(date);
      species.set(code, entry);
    }
  }
  return {
    state: coverage.recordedDates.length >= DAYPART_MINIMUM_DAYS ? "available" : "insufficient",
    minimumRecordedDays: DAYPART_MINIMUM_DAYS,
    coverage,
    periods: PERIODS.map((period) => ({ ...period })),
    species: [...species.values()].map(({ code, name, dates, datesByPeriod }) => {
      const daysByPeriod = datesByPeriod.map((periodDates) => periodDates.size);
      return {
        code, name, daysByPeriod, detectedDates: dates.size,
        group: daypartGroup(daysByPeriod, coverage.recordedDates.length),
      };
    }).sort(byNameAndCode),
  };
}

/**
 * Summarize completed Eastern calendar dates without adding upstream requests.
 * The caller supplies normalized days and already accepted, unambiguous minutes.
 */
export function summarizeYardmicInsights(days, relevantMinutes, today) {
  const currentDate = Temporal.PlainDate.from(today);
  const daysByDate = new Map(days.map((day) => [day.date, day]));
  const weeks = Array.from({ length: 4 }, (_, index) =>
    weekCoverage(currentDate.subtract({ days: 28 - index * 7 }), daysByDate, relevantMinutes));
  return {
    weekly: weeklySummary(weeks, relevantMinutes),
    dayparts: daypartSummary(weeks[3], relevantMinutes),
  };
}
