const form = document.querySelector("#detector-form");
const results = document.querySelector("#results");
const button = document.querySelector("#run-detector");
const status = document.querySelector("#search-status");
const errorBox = document.querySelector("#search-error");
const rows = document.querySelector("#result-rows");
const empty = document.querySelector("#empty-results");
const total = document.querySelector("#result-total");
const summary = document.querySelector("#result-summary");

function isoDateToday() {
  return new Date().toISOString().slice(0, 10);
}

function daysAgo(days) {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

document.querySelector("#date-from").value = daysAgo(30);
document.querySelector("#date-to").value = isoDateToday();

function clearError() {
  errorBox.hidden = true;
  errorBox.querySelector("p").textContent = "";
}

function showError(message) {
  errorBox.querySelector("p").textContent = message;
  errorBox.hidden = false;
}

function textCell(value, className = "") {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = value;
  return cell;
}

function renderResults(payload) {
  rows.replaceChildren();
  const count = payload.totalNewSpecies;
  total.textContent = count.toLocaleString();
  total.setAttribute("aria-label", `${count.toLocaleString()} new species`);
  summary.textContent = `${count.toLocaleString()} species newly recorded in iNaturalist for place ${payload.query.placeId} from ${payload.query.dateFrom} through ${payload.query.dateTo}.`;
  empty.hidden = count !== 0;
  for (const species of payload.species) {
    const row = document.createElement("tr");
    const speciesCell = document.createElement("td");
    const common = document.createElement("strong");
    common.textContent = species.commonName || species.scientificName;
    const scientific = document.createElement("em");
    scientific.textContent = species.scientificName;
    speciesCell.append(common, scientific);
    row.append(
      speciesCell,
      textCell(species.firstObservationDate, "tabular"),
      textCell(species.observer),
    );
    const linkCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = species.observationUrl;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "View on iNaturalist ↗";
    linkCell.append(link);
    row.append(linkCell);
    rows.append(row);
  }
  results.hidden = false;
  results.scrollIntoView({ behavior: "smooth", block: "start" });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  results.hidden = true;
  const placeId = document.querySelector("#place-id").value;
  const dateFrom = document.querySelector("#date-from").value;
  const dateTo = document.querySelector("#date-to").value;
  const includeCasual = document.querySelector("#include-casual").checked;
  const params = new URLSearchParams({ place_id: placeId, d1: dateFrom, d2: dateTo, include_casual: String(includeCasual) });
  button.disabled = true;
  status.textContent = "Searching iNaturalist at a respectful pace and checking each species’ place history…";
  try {
    const response = await fetch(`/api/new-county-species?${params}`, { headers: { Accept: "application/json" } });
    const payload = await response.json().catch(() => null);
    if (!response.ok) throw new Error(payload?.error?.message || `Request returned HTTP ${response.status}.`);
    renderResults(payload);
    status.textContent = "Search complete.";
  } catch (error) {
    showError(error.message || "The detector could not complete the request. Please try again.");
    status.textContent = "";
  } finally {
    button.disabled = false;
  }
});
