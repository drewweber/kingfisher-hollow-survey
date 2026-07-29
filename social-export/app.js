const PRESET = {
  dateFrom: "2026-07-18",
  dateTo: "2026-07-26",
  taxonGroup: "moths",
  observer: "drewweber",
  outputFormat: "instagram-square",
  gridSize: "5x4",
  maximumSlides: "10",
  includeCover: true,
  includeLabels: true,
  includeUnresolved: false,
  theme: "kingfisher-quiet",
};

const form = document.querySelector("#export-form");
const presetControl = document.querySelector("#preset");
const searchButton = document.querySelector("#find-photos");
const searchStatus = document.querySelector("#search-status");
const searchError = document.querySelector("#search-error");
const review = document.querySelector("#review");
const speciesGrid = document.querySelector("#species-grid");
const reviewSummary = document.querySelector("#review-summary");
const capacityCount = document.querySelector("#capacity-count");
const exportDescription = document.querySelector("#export-description");
const downloadButton = document.querySelector("#download-export");
const exportStatus = document.querySelector("#export-status");
const exportError = document.querySelector("#export-error");
const dialog = document.querySelector("#photo-dialog");
const dialogTitle = document.querySelector("#photo-dialog-title");
const dialogSpecies = document.querySelector("#photo-dialog-species");
const candidateGrid = document.querySelector("#candidate-grid");

let searchData = null;
let exportSpecies = [];
let activeSpeciesKey = null;
let lastDialogTrigger = null;

function setValue(selector, value) {
  document.querySelector(selector).value = value;
}

function applyPreset() {
  invalidateReview();
  if (presetControl.value !== "national-moth-week-2026") return;
  setValue("#date-from", PRESET.dateFrom);
  setValue("#date-to", PRESET.dateTo);
  setValue("#taxon-group", PRESET.taxonGroup);
  setValue("#observer", PRESET.observer);
  setValue("#output-format", PRESET.outputFormat);
  setValue("#grid-size", PRESET.gridSize);
  setValue("#maximum-slides", PRESET.maximumSlides);
  setValue("#theme", PRESET.theme);
  document.querySelector("#include-cover").checked = PRESET.includeCover;
  document.querySelector("#include-labels").checked = PRESET.includeLabels;
  document.querySelector("#include-unresolved").checked = PRESET.includeUnresolved;
}

function invalidateReview() {
  review.hidden = true;
  searchData = null;
  exportSpecies = [];
}

function markCustom(event) {
  if (presetControl.value) presetControl.value = "";
  const queryControls = new Set([
    "date-from",
    "date-to",
    "taxon-group",
    "observer",
    "include-unresolved",
  ]);
  if (queryControls.has(event.currentTarget.id)) {
    invalidateReview();
  } else if (searchData) {
    renderReview();
  }
}

for (const control of form.elements) {
  if (!control.name && !control.id) continue;
  if (control === presetControl) continue;
  control.addEventListener("change", markCustom);
}
presetControl.addEventListener("change", applyPreset);

function currentQuery() {
  return {
    dateFrom: document.querySelector("#date-from").value,
    dateTo: document.querySelector("#date-to").value,
    taxonGroup: document.querySelector("#taxon-group").value,
    observer: document.querySelector("#observer").value.trim().toLowerCase(),
    includeUnresolvedTaxa: document.querySelector("#include-unresolved").checked,
  };
}

function currentSettings() {
  const gridSize = document.querySelector("#grid-size").value;
  const [gridColumns, gridRows] = gridSize.split("x").map(Number);
  return {
    presetId: presetControl.value || null,
    outputFormat: document.querySelector("#output-format").value,
    gridSize,
    gridColumns,
    gridRows,
    maximumSlides: Number(document.querySelector("#maximum-slides").value),
    includeCover: document.querySelector("#include-cover").checked,
    includeSpeciesLabels: document.querySelector("#include-labels").checked,
    theme: document.querySelector("#theme").value,
  };
}

function showInlineError(container, message) {
  container.querySelector("p").textContent = message;
  container.hidden = false;
}

function clearInlineError(container) {
  container.hidden = true;
  container.querySelector("p").textContent = "";
}

async function requestJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(body?.error?.message || `Request returned HTTP ${response.status}.`);
    error.retryable = body?.error?.retryable === true;
    throw error;
  }
  return body;
}

function candidateScore(candidate, metrics) {
  if (!metrics || metrics.error) return candidate.metadataScore;
  return Math.max(0, Math.min(100,
    candidate.metadataScore * .42
      + metrics.sharpness * 18
      + metrics.exposure * 13
      + metrics.contrast * 10
      + metrics.subjectOccupancy * 12
      + (1 - metrics.obstruction) * 5
  ));
}

function hammingDistance(left, right) {
  if (!left || !right || left.length !== right.length) return Infinity;
  let distance = 0;
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) distance += 1;
  }
  return distance;
}

function applyScores(species, results) {
  const byPhoto = new Map(results.map((result) => [Number(result.photoId), result]));
  const scored = species.map((group) => {
    const candidates = group.candidates.map((candidate) => {
      const metrics = byPhoto.get(candidate.photoId);
      return {
        ...candidate,
        score: Math.round(candidateScore(candidate, metrics) * 100) / 100,
        metrics: metrics?.error ? null : metrics,
      };
    }).sort((left, right) => right.score - left.score || left.photoId - right.photoId);
    for (let index = 1; index < candidates.length; index += 1) {
      const candidate = candidates[index];
      if (candidates.slice(0, index).some((better) => (
        hammingDistance(candidate.metrics?.perceptualHash, better.metrics?.perceptualHash) <= 5
      ))) {
        candidate.score = Math.max(0, Math.round((candidate.score - 8) * 100) / 100);
        candidate.nearDuplicate = true;
      }
    }
    candidates.sort((left, right) => right.score - left.score || left.photoId - right.photoId);
    return { ...group, candidates, selectedPhotoId: candidates[0].photoId };
  });
  const selectedHashes = [];
  const selectionOrder = [...scored].sort((left, right) => (
    right.candidates[0].score - left.candidates[0].score
      || left.speciesKey.localeCompare(right.speciesKey)
  ));
  for (const group of selectionOrder) {
    const distinct = group.candidates.find((candidate) => {
      const hash = candidate.metrics?.perceptualHash;
      return hash && selectedHashes.every((selectedHash) => hammingDistance(hash, selectedHash) > 5);
    });
    const selected = distinct || group.candidates[0];
    group.selectedPhotoId = selected.photoId;
    if (selected.metrics?.perceptualHash) selectedHashes.push(selected.metrics.perceptualHash);
  }
  return scored;
}

async function scorePhotos(species) {
  const photos = species.flatMap((group) => group.candidates.map((candidate) => ({
    photoId: candidate.photoId,
    url: candidate.thumbnailUrl,
  })));
  const results = [];
  for (let index = 0; index < photos.length; index += 24) {
    const batch = photos.slice(index, index + 24);
    const completed = Math.min(index + batch.length, photos.length);
    searchStatus.textContent = `Inspecting photo quality · ${completed.toLocaleString()} of ${photos.length.toLocaleString()}`;
    try {
      const response = await requestJson("/api/social-export/score", { photos: batch });
      results.push(...response.results);
    } catch (_error) {
      results.push(...batch.map((photo) => ({ photoId: photo.photoId, error: "Analysis unavailable" })));
    }
  }
  return applyScores(species, results);
}

function selectedCandidate(group) {
  return group.candidates.find((candidate) => candidate.photoId === group.selectedPhotoId)
    || group.candidates[0];
}

function capacityFor(settings) {
  const gridSlides = Math.max(0, settings.maximumSlides - (settings.includeCover ? 1 : 0));
  return gridSlides * settings.gridColumns * settings.gridRows;
}

function makeSpeciesCard(group) {
  const candidate = selectedCandidate(group);
  group.rotation = Number(group.rotation) || 0;
  const article = document.createElement("article");
  article.className = "species-card";
  article.dataset.speciesKey = group.speciesKey;
  const photo = document.createElement("div");
  photo.className = "species-photo";
  const image = document.createElement("img");
  image.src = candidate.renderUrl;
  image.alt = `${group.commonName || group.scientificName}, iNaturalist observation ${candidate.observationId}`;
  image.loading = "lazy";
  image.decoding = "async";
  image.style.transform = `rotate(${group.rotation}deg)`;
  const score = document.createElement("span");
  score.className = "score-badge";
  score.textContent = `${Math.round(candidate.score)} quality`;
  photo.append(image, score);

  const info = document.createElement("div");
  info.className = "species-info";
  const heading = document.createElement("h3");
  heading.textContent = group.commonName || group.scientificName;
  const scientific = document.createElement("em");
  scientific.textContent = group.scientificName;
  const button = document.createElement("button");
  button.className = "replace-photo";
  button.type = "button";
  button.textContent = group.candidates.length > 1
    ? `Replace photo · ${group.candidates.length} choices`
    : "Only matching photo";
  button.disabled = group.candidates.length < 2;
  button.addEventListener("click", () => openPhotoDialog(group, button));
  const rotateButton = document.createElement("button");
  rotateButton.className = "rotate-photo";
  rotateButton.type = "button";
  rotateButton.textContent = "Rotate 90°";
  rotateButton.setAttribute(
    "aria-label",
    `Rotate ${group.commonName || group.scientificName} photo 90 degrees`,
  );
  rotateButton.addEventListener("click", () => {
    group.rotation = (group.rotation + 90) % 360;
    image.style.transform = `rotate(${group.rotation}deg)`;
    rotateButton.dataset.rotation = String(group.rotation);
  });
  const actions = document.createElement("div");
  actions.className = "photo-actions";
  actions.append(button, rotateButton);
  info.append(heading, scientific, actions);
  article.append(photo, info);
  return article;
}

function renderReview() {
  const settings = currentSettings();
  const capacity = capacityFor(settings);
  const chosenByQuality = [...searchData.species]
    .sort((left, right) => (
      selectedCandidate(right).score - selectedCandidate(left).score
      || (left.commonName || left.scientificName).localeCompare(right.commonName || right.scientificName)
    ))
    .slice(0, capacity);
  exportSpecies = chosenByQuality.sort((left, right) => (
    (left.commonName || left.scientificName).localeCompare(
      right.commonName || right.scientificName,
      "en",
      { sensitivity: "base" },
    )
  ));

  speciesGrid.replaceChildren(...exportSpecies.map(makeSpeciesCard));
  capacityCount.textContent = `${exportSpecies.length.toLocaleString()} / ${capacity.toLocaleString()}`;
  const summary = searchData.summary;
  const excluded = summary.excludedButterflyCount
    ? ` ${summary.excludedButterflyCount.toLocaleString()} butterfly observation${summary.excludedButterflyCount === 1 ? " was" : "s were"} excluded.`
    : "";
  reviewSummary.textContent = `${summary.speciesCount.toLocaleString()} eligible species from ${summary.observationCount.toLocaleString()} observations and ${summary.photoCount.toLocaleString()} observer-owned photos.${excluded}`;
  const slideCount = presetControl.value === "national-moth-week-2026"
    ? settings.maximumSlides
    : Math.min(
      settings.maximumSlides,
      (settings.includeCover ? 1 : 0)
        + Math.ceil(exportSpecies.length / (settings.gridColumns * settings.gridRows)),
    );
  exportDescription.textContent = `${slideCount} server-rendered slide${slideCount === 1 ? "" : "s"}`;
  review.hidden = false;
}

function openPhotoDialog(group, trigger) {
  activeSpeciesKey = group.speciesKey;
  lastDialogTrigger = trigger;
  dialogTitle.textContent = "Choose a photo";
  dialogSpecies.textContent = `${group.commonName || group.scientificName} · ${group.scientificName}`;
  candidateGrid.replaceChildren(...group.candidates.map((candidate) => {
    const button = document.createElement("button");
    button.className = "candidate";
    button.type = "button";
    button.setAttribute("aria-pressed", candidate.photoId === group.selectedPhotoId ? "true" : "false");
    button.setAttribute("aria-label", `Use photo ${candidate.photoId} from observation ${candidate.observationId}`);
    const image = document.createElement("img");
    image.src = candidate.renderUrl;
    image.alt = "";
    image.loading = "lazy";
    const detail = document.createElement("span");
    detail.textContent = `${Math.round(candidate.score)} quality · ${candidate.width}×${candidate.height}`;
    button.append(image, detail);
    if (candidate.photoId === group.selectedPhotoId) {
      const selected = document.createElement("b");
      selected.textContent = "Selected";
      button.append(selected);
    }
    button.addEventListener("click", () => chooseCandidate(candidate.photoId));
    return button;
  }));
  dialog.showModal();
  candidateGrid.querySelector('[aria-pressed="true"]')?.focus();
}

function chooseCandidate(photoId) {
  const group = searchData.species.find((item) => item.speciesKey === activeSpeciesKey);
  if (!group) return;
  group.selectedPhotoId = photoId;
  group.rotation = 0;
  const visible = speciesGrid.querySelector(`[data-species-key="${CSS.escape(activeSpeciesKey)}"]`);
  if (visible) {
    const replacement = makeSpeciesCard(group);
    visible.replaceWith(replacement);
    lastDialogTrigger = replacement.querySelector(".replace-photo");
  }
  dialog.close();
}

dialog.addEventListener("close", () => {
  lastDialogTrigger?.focus();
  activeSpeciesKey = null;
  lastDialogTrigger = null;
});
document.querySelector("#close-photo-dialog").addEventListener("click", () => dialog.close());

async function findPhotos() {
  clearInlineError(searchError);
  clearInlineError(exportError);
  review.hidden = true;
  searchButton.disabled = true;
  searchButton.textContent = "Retrieving observations…";
  searchStatus.textContent = "Querying iNaturalist and following all result pages.";
  try {
    const result = await requestJson("/api/social-export/observations", currentQuery());
    if (!result.species.length) {
      throw new Error("No eligible photographed species matched these settings. Check the dates, observer, or unresolved-taxa option.");
    }
    result.species = await scorePhotos(result.species);
    searchData = result;
    renderReview();
    searchStatus.textContent = "Automatic choices are ready for review.";
    review.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    searchStatus.textContent = "";
    showInlineError(searchError, error.message);
  } finally {
    searchButton.disabled = false;
    searchButton.textContent = "Review automatic photo choices";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  findPhotos();
});
document.querySelector("#retry-search").addEventListener("click", findPhotos);

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

async function exportCarousel() {
  if (!searchData || !exportSpecies.length) return;
  clearInlineError(exportError);
  downloadButton.disabled = true;
  downloadButton.textContent = "Rendering PNG files…";
  exportStatus.textContent = "The server is composing each slide and its attribution manifest.";
  const settings = currentSettings();
  const filename = settings.presetId === "national-moth-week-2026"
    ? "moth-week-2026.zip"
    : `social-export-${searchData.query.dateFrom}.zip`;
  try {
    const response = await fetch("/api/social-export/export", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/zip, application/json" },
      body: JSON.stringify({
        query: searchData.query,
        settings,
        selections: exportSpecies.map((group) => ({
          speciesKey: group.speciesKey,
          photoId: group.selectedPhotoId,
          rotation: group.rotation || 0,
        })),
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.error?.message || `Export returned HTTP ${response.status}.`);
    }
    downloadBlob(await response.blob(), filename);
    exportStatus.textContent = `${filename} is ready. If Safari did not open the download, tap “Download carousel ZIP” again.`;
  } catch (error) {
    exportStatus.textContent = "";
    showInlineError(exportError, error.message);
  } finally {
    downloadButton.disabled = false;
    downloadButton.textContent = "Download carousel ZIP";
  }
}

downloadButton.addEventListener("click", exportCarousel);
document.querySelector("#retry-export").addEventListener("click", exportCarousel);
