import { Temporal } from "@js-temporal/polyfill";
import { summarizeYardmicInsights } from "./yardmic_insights.mjs";

export const YARDMIC_TIME_ZONE = "America/New_York";
const MINUTE_MS = 60_000;
const DAY_MS = 24 * 60 * MINUTE_MS;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const CLOCK_MINUTE = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const SPECIES_CODE = /^[a-z0-9]{1,24}$/;
const SPECIES_NAME = /^[\p{L}\p{M}\p{N} .,'’()\-–/]{1,120}$/u;
const KINGFISHER = "belkin1";

function calendarDate(instant) {
  return Temporal.Instant.fromEpochMilliseconds(instant)
    .toZonedDateTimeISO(YARDMIC_TIME_ZONE).toPlainDate();
}

export function yardmicRanges(now) {
  const today = calendarDate(now);
  return {
    recent: { start: today.subtract({ days: 1 }).toString(), end: today.toString() },
    history: { start: today.subtract({ days: 30 }).toString(), end: today.subtract({ days: 2 }).toString() },
    patterns: { start: today.subtract({ days: 7 }).toString(), end: today.subtract({ days: 1 }).toString() },
  };
}

export function shiftYardmicRange(range, days) {
  const shift = (date) => Temporal.PlainDate.from(date).add({ days }).toString();
  return { start: shift(range.start), end: shift(range.end) };
}

function inRange(date, range) {
  return date >= range.start && date <= range.end;
}

function validDate(value) {
  if (typeof value !== "string" || !DATE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === value;
}

function invalidPayload() {
  return new TypeError("Invalid YardMic minute data");
}

/** Retain only fields used in the public derivation, including in the edge cache. */
export function normalizeYardmicDays(payload, { range, apiKey } = {}) {
  if (!Array.isArray(payload?.days) || payload.days.length > 31) throw invalidPayload();
  const dates = new Set();
  return payload.days.map((day) => {
    const { date, listening_minutes, species } = day ?? {};
    if (!validDate(date) || (range && !inRange(date, range)) || dates.has(date)
      || !Number.isInteger(listening_minutes) || listening_minutes < 0 || listening_minutes > 1500
      || !Array.isArray(species) || species.length > 512) {
      throw invalidPayload();
    }
    dates.add(date);
    const codes = new Set();
    return {
      date,
      listening_minutes,
      species: species.map((bird) => {
        const { code, name, confirmed, minutes } = bird ?? {};
        if (typeof code !== "string" || !SPECIES_CODE.test(code) || codes.has(code)
          || typeof name !== "string" || !SPECIES_NAME.test(name) || name.trim() !== name
          || (apiKey && (code.includes(apiKey) || name.includes(apiKey)))
          || (confirmed !== "reviewed" && confirmed !== "auto" && confirmed !== false)
          || !Array.isArray(minutes) || minutes.length > 1500
          || minutes.some((minute) => typeof minute !== "string" || !CLOCK_MINUTE.test(minute))) {
          throw invalidPayload();
        }
        codes.add(code);
        return { code, name, confirmed, minutes: [...new Set(minutes)].sort() };
      }),
    };
  }).sort((left, right) => left.date.localeCompare(right.date));
}

function minuteResolver(date) {
  const day = Temporal.PlainDate.from(date);
  const start = day.toZonedDateTime(YARDMIC_TIME_ZONE);
  const nextStart = day.add({ days: 1 }).toZonedDateTime(YARDMIC_TIME_ZONE);
  const midnight = start.epochMilliseconds;
  const minuteFromMidnight = (minute) => (Number(minute.slice(0, 2)) * 60 + Number(minute.slice(3))) * MINUTE_MS;
  const clockShift = DAY_MS - (nextStart.epochMilliseconds - midnight);
  if (clockShift === 0) return (minute) => midnight + minuteFromMidnight(minute);

  // Use the zone's transition to separate ordinary minutes from the clock change.
  const transition = start.getTimeZoneTransition("next").epochMilliseconds;
  const firstAffected = transition + Math.min(0, clockShift);
  const firstAfter = transition + Math.max(0, clockShift);
  const resolved = new Map();
  return (minute) => {
    const beforeShift = midnight + minuteFromMidnight(minute);
    if (beforeShift < firstAffected) return beforeShift;
    if (beforeShift >= firstAfter) return beforeShift - clockShift;
    if (!resolved.has(minute)) {
      const plain = day.toPlainDateTime(minute);
      const earlier = plain.toZonedDateTime(YARDMIC_TIME_ZONE, { disambiguation: "earlier" });
      const later = plain.toZonedDateTime(YARDMIC_TIME_ZONE, { disambiguation: "later" });
      let value = null;
      if (earlier.epochMilliseconds === later.epochMilliseconds) {
        value = earlier.epochMilliseconds;
      } else if (earlier.toPlainDateTime().equals(plain)) {
        value = { earlier: earlier.epochMilliseconds, later: later.epochMilliseconds };
      }
      resolved.set(minute, value);
    }
    return resolved.get(minute);
  };
}

function iso(epoch) {
  return epoch === null ? null : new Date(epoch).toISOString();
}

function countHistoryPatterns(days, range, relevantMinutes) {
  const hourly = Array.from({ length: 24 }, (_, hour) => ({ hour, dates: 0, speciesMinutes: 0 }));
  const overnight = new Map();
  const recurringHours = new Map();
  const speciesHours = new Map();
  for (const day of days) {
    const perDayHour = Array(24).fill(0);
    for (const { code, name, minutes } of relevantMinutes.get(day.date)) {
      const perSpeciesHour = Array(24).fill(0);
      let overnightMinutes = 0;
      for (const minute of minutes) {
        const hour = Number(minute.slice(0, 2));
        perDayHour[hour] += 1;
        perSpeciesHour[hour] += 1;
        if (hour >= 20 || hour <= 5) overnightMinutes += 1;
      }

      const composition = speciesHours.get(code) ?? {
        code, name, daysByHour: Array(24).fill(0), detectedDates: 0,
      };
      composition.detectedDates += 1;
      perSpeciesHour.forEach((detectedMinutes, hour) => {
        if (detectedMinutes > 0) composition.daysByHour[hour] += 1;
      });
      speciesHours.set(code, composition);

      if (overnightMinutes > 0) {
        const entry = overnight.get(code) ?? { code, name, detectedMinutes: 0, days: [] };
        entry.detectedMinutes += overnightMinutes;
        entry.days.push({ date: day.date, detectedMinutes: overnightMinutes });
        overnight.set(code, entry);
      }

      perSpeciesHour.forEach((detectedMinutes, hour) => {
        if (detectedMinutes < 10) return;
        const key = `${code}:${hour}`;
        const entry = recurringHours.get(key) ?? { code, name, hour, minutesByDate: [] };
        entry.minutesByDate.push({ date: day.date, detectedMinutes });
        recurringHours.set(key, entry);
      });
    }

    perDayHour.forEach((speciesMinutes, hour) => {
      if (speciesMinutes === 0) return;
      hourly[hour].dates += 1;
      hourly[hour].speciesMinutes += speciesMinutes;
    });
  }

  const rankedHours = [...recurringHours.values()]
    .filter(({ minutesByDate }) => minutesByDate.length >= 3)
    .map((entry) => {
      const dates = entry.minutesByDate.length;
      const mean = entry.minutesByDate.reduce((total, day) => total + day.detectedMinutes, 0) / dates;
      return { entry: { ...entry, dates }, mean };
    }).sort((left, right) => right.mean - left.mean || right.entry.dates - left.entry.dates
      || left.entry.hour - right.entry.hour || left.entry.code.localeCompare(right.entry.code));

  return {
    range,
    dates: days.map(({ date }) => date),
    hourly: hourly.filter(({ dates }) => dates >= 3)
      .sort((left, right) => right.dates - left.dates || right.speciesMinutes - left.speciesMinutes || left.hour - right.hour),
    speciesHours: [...speciesHours.values()]
      .map((entry) => ({ ...entry, peakHour: entry.daysByHour.indexOf(Math.max(...entry.daysByHour)) }))
      .sort((left, right) => left.peakHour - right.peakHour || right.detectedDates - left.detectedDates
        || left.name.localeCompare(right.name) || left.code.localeCompare(right.code)),
    recurringHour: rankedHours[0]?.entry ?? null,
    overnight: [...overnight.values()]
      .filter(({ days: observedDays }) => observedDays.length >= 2)
      .map((entry) => ({ ...entry, dates: entry.days.length }))
      .sort((left, right) => right.dates - left.dates || right.detectedMinutes - left.detectedMinutes
        || left.code.localeCompare(right.code)),
  };
}

function publicDetection(detection) {
  return {
    latestAt: iso(detection?.epoch ?? null),
    latestLocal: detection?.local ?? null,
    status: detection?.status ?? null,
  };
}

function sampleFreshness(days, range, retrievedAt) {
  return days.some(({ date }) => inRange(date, range))
    ? { state: "fresh", retrievedAt }
    : { state: "unavailable", retrievedAt: null };
}

function recentSnapshot(freshness, retrievedAt, nowMs) {
  // The API supplies no recording-end timestamp. These are response/retrieval
  // estimates only; detection times and the current clock cannot replace them.
  const declared = freshness?.snapshot;
  const candidates = declared ? [declared] : [
    { estimatedAt: freshness?.sourceCache?.cachedAt, basis: "source-response-estimate" },
    { estimatedAt: freshness?.retrievedAt ?? retrievedAt, basis: "retrieval-estimate" },
  ];
  for (const { estimatedAt, basis } of candidates) {
    const epoch = typeof estimatedAt === "string" ? Date.parse(estimatedAt) : NaN;
    if (Number.isFinite(epoch) && epoch <= nowMs
      && (basis === "source-response-estimate" || basis === "retrieval-estimate")) {
      return { estimatedAt: iso(epoch), basis, end: Math.floor(epoch / MINUTE_MS) * MINUTE_MS };
    }
  }
  return { estimatedAt: null, basis: "unknown", end: null };
}

function summarizeRecentHour(days, snapshot) {
  const cutoff = snapshot.end === null ? null : snapshot.end - 60 * MINUTE_MS;
  const range = snapshot.end === null ? null : {
    start: calendarDate(cutoff + MINUTE_MS).toString(),
    end: calendarDate(snapshot.end).toString(),
  };
  const relevantDays = range === null ? [] : days.filter(({ date }) => inRange(date, range));
  const recent = new Map();
  let ambiguous = false;
  for (const day of relevantDays) {
    const resolve = minuteResolver(day.date);
    for (const { code, name, confirmed: status, minutes } of day.species) {
      if (status === false) continue;
      for (const minute of minutes) {
        const epoch = resolve(minute);
        if (epoch === null) continue;
        if (typeof epoch === "object") {
          if ([epoch.earlier, epoch.later].some((candidate) => candidate > cutoff && candidate <= snapshot.end)) {
            ambiguous = true;
          }
          continue;
        }
        if (epoch <= cutoff || epoch > snapshot.end) continue;
        const entry = recent.get(code) ?? { minuteStarts: [] };
        entry.minuteStarts.push(iso(epoch));
        if (entry.epoch === undefined || epoch > entry.epoch) {
          Object.assign(entry, { code, name, epoch, local: `${day.date}T${minute}`, status });
        }
        recent.set(code, entry);
      }
    }
  }
  const requiredDates = range?.start === range?.end ? 1 : 2;
  return {
    state: relevantDays.length
      ? (relevantDays.length === requiredDates && !ambiguous ? "available" : "partial")
      : "unavailable",
    start: iso(cutoff),
    end: iso(snapshot.end),
    windowBasis: snapshot.basis,
    snapshotEstimatedAt: snapshot.estimatedAt,
    recordingEndAt: null,
    ambiguous,
    species: [...recent.values()]
      .sort((left, right) => right.epoch - left.epoch || left.code.localeCompare(right.code))
      .map((entry) => ({
        code: entry.code,
        name: entry.name,
        ...publicDetection(entry),
        detectedMinutes: entry.minuteStarts.length,
        minuteStarts: entry.minuteStarts.sort(),
      })),
  };
}

/** Summarize UTC instants and Eastern calendar dates. The fixture wrapper is local-only. */
export function summarizeYardmic(payload, { now = Date.now(), freshness, recentSnapshotDays, historyAnchorDate, companionDay } = {}) {
  const nowMs = new Date(now).valueOf();
  const windows = yardmicRanges(nowMs);
  const requested = { start: windows.history.start, end: windows.recent.end };
  let allDays = normalizeYardmicDays(payload?.data ?? payload ?? { days: [] });
  if (companionDay) {
    const [day] = normalizeYardmicDays({ days: [companionDay] });
    allDays = [...allDays.filter((entry) => entry.date !== day.date), day].sort((a, b) => a.date.localeCompare(b.date));
  }
  const days = allDays.filter(({ date }) => inRange(date, requested));
  const anchor = Temporal.PlainDate.from(historyAnchorDate ?? windows.recent.end);
  const patternsRange = { start: anchor.subtract({ days: 7 }).toString(), end: anchor.subtract({ days: 1 }).toString() };
  const displayed = { start: anchor.subtract({ days: 30 }).toString(), end: anchor.toString() };
  const historicalDays = allDays.filter(({ date }) => inRange(date, displayed));
  const retrievedAt = (typeof payload?.fetched_at === "string" && Number.isFinite(Date.parse(payload.fetched_at)))
    ? iso(Date.parse(payload.fetched_at)) : null;
  const freshnessByRange = freshness ?? {
    recent: sampleFreshness(days, windows.recent, retrievedAt),
    history: sampleFreshness(days, windows.history, retrievedAt),
  };
  const snapshot = recentSnapshot(freshnessByRange.recent, retrievedAt, nowMs);
  const snapshotDays = recentSnapshotDays === undefined ? days
    : normalizeYardmicDays({ days: recentSnapshotDays });
  const returnedDates = days.map(({ date }) => date);
  const historyMinutes = new Map();
  let kingfisherAmbiguous = null;
  let latestDetectionAt = null;
  let latestKingfisher = null;

  for (const day of allDays) {
    const current = inRange(day.date, requested);
    const inHistoricalView = inRange(day.date, displayed);
    const kingfisherEligible = current || (freshnessByRange.history.state === "stale" && inHistoricalView);
    const isPatternDate = inHistoricalView && day.date < displayed.end;
    if (!kingfisherEligible && !isPatternDate) continue;
    const resolve = minuteResolver(day.date);
    const patternSpecies = [];
    for (const { code, name, confirmed: status, minutes } of day.species) {
      if (status === false) continue;
      const patternMinutes = [];
      for (let index = minutes.length - 1; index >= 0; index -= 1) {
        const minute = minutes[index];
        const epoch = resolve(minute);
        if (epoch === null) continue;
        if (typeof epoch === "object") {
          if (kingfisherEligible && epoch.earlier <= nowMs) {
            if (code === KINGFISHER) {
              const local = `${day.date}T${minute}`;
              if (kingfisherAmbiguous === null || local > kingfisherAmbiguous) kingfisherAmbiguous = local;
            }
          }
          continue;
        }
        if (epoch > nowMs) continue;

        if (current && (latestDetectionAt === null || epoch > latestDetectionAt)) latestDetectionAt = epoch;
        if (kingfisherEligible && code === KINGFISHER && (!latestKingfisher || epoch > latestKingfisher.epoch)) {
          latestKingfisher = { epoch, local: `${day.date}T${minute}`, status };
        }
        if (!isPatternDate) break;
        patternMinutes.push(minute);
      }
      if (patternMinutes.length) patternSpecies.push({ code, name, minutes: patternMinutes });
    }
    historyMinutes.set(day.date, patternSpecies);
  }

  const ambiguousLatest = kingfisherAmbiguous !== null
    && (!latestKingfisher || kingfisherAmbiguous > latestKingfisher.local);
  if (ambiguousLatest) latestKingfisher = null;

  const allDatesReturned = days.length === 31;
  const patternsDays = historicalDays.filter(({ date }) => inRange(date, patternsRange));
  const patterns = countHistoryPatterns(patternsDays, patternsRange, historyMinutes);
  if (historyAnchorDate) {
    patterns.dailyEffort = patternsDays.map(({ date, listening_minutes }) => ({ date, listeningMinutes: listening_minutes }));
  }

  return {
    state: days.length ? (allDatesReturned ? "available" : "partial") : "unavailable",
    generatedAt: iso(nowMs),
    timeZone: YARDMIC_TIME_ZONE,
    latestDetectionAt: iso(latestDetectionAt),
    range: {
      requested,
      ...(historyAnchorDate && { displayed, historyAnchorDate }),
      returned: days.length ? { start: returnedDates[0], end: returnedDates.at(-1) } : null,
      returnedDates,
    },
    freshness: freshnessByRange,
    dailyEffort: days.map(({ date, listening_minutes }) => ({ date, listeningMinutes: listening_minutes })),
    recentHour: summarizeRecentHour(snapshotDays, snapshot),
    kingfisher: {
      state: latestKingfisher ? "detected" : (days.length && !ambiguousLatest ? "no-match" : "unavailable"),
      ...publicDetection(latestKingfisher),
      elapsedMinutes: latestKingfisher ? Math.floor((nowMs - latestKingfisher.epoch) / MINUTE_MS) : null,
      complete: allDatesReturned && !ambiguousLatest
        && freshnessByRange.recent.state === "fresh" && freshnessByRange.history.state === "fresh",
      ambiguous: ambiguousLatest,
    },
    patterns,
    insights: summarizeYardmicInsights(historicalDays, historyMinutes, displayed.end),
  };
}
