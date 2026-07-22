(() => {
  "use strict";

  const GROUP_LABELS = {
    moths: "Moths",
    butterflies: "Butterflies",
    odonates: "Dragons"
  };
  const MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];
  const MONTH_SHORT = MONTH_NAMES.map((month) => month.slice(0, 3));
  const CURRENT_MONTH = new Date().getMonth() + 1;

  const state = {
    data: null,
    targets: [],
    group: "all",
    query: "",
    habitat: "",
    method: "",
    registration: null,
    offlinePhase: "checking",
    offlineTimer: null,
    detailId: null,
    detailHistoryOwned: false,
    detailTrigger: null,
    closingFromHistory: false
  };

  const elements = {
    dataDate: document.querySelector("#data-date"),
    networkState: document.querySelector("#network-state"),
    networkLabel: document.querySelector("#network-label"),
    offlineStatus: document.querySelector("#offline-status"),
    offlineAction: document.querySelector("#offline-action"),
    offlineActionLabel: document.querySelector("#offline-action-label"),
    form: document.querySelector("#target-filters"),
    search: document.querySelector("#target-search"),
    filterToggle: document.querySelector("#filter-toggle"),
    filterCount: document.querySelector("#filter-count"),
    filterPanel: document.querySelector("#filter-panel"),
    habitat: document.querySelector("#habitat-filter"),
    method: document.querySelector("#method-filter"),
    clearFilters: document.querySelector("#clear-filters"),
    resultCount: document.querySelector("#result-count"),
    resultsHeading: document.querySelector("#results-heading"),
    statePanel: document.querySelector("#state-panel"),
    targetList: document.querySelector("#target-list"),
    dialog: document.querySelector("#target-dialog"),
    dialogGroup: document.querySelector("#dialog-group"),
    dialogTitle: document.querySelector("#dialog-title"),
    dialogContent: document.querySelector("#dialog-content"),
    dialogClose: document.querySelector("#dialog-close")
  };

  function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined && text !== null) element.textContent = text;
    return element;
  }

  function cleanString(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function cleanStringList(value) {
    if (!Array.isArray(value)) return [];
    return value.map(cleanString).filter(Boolean);
  }

  function cleanTraits(value) {
    if (!Array.isArray(value)) return [];
    return value.map((item) => {
      if (!item || typeof item !== "object") return null;
      const label = cleanString(item.label);
      const detail = cleanString(item.detail);
      return label && detail ? { label, detail } : null;
    }).filter(Boolean);
  }

  function cleanOnlineUrl(value) {
    const raw = cleanString(value);
    if (!raw) return "";
    try {
      const url = new URL(raw, document.baseURI);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function cleanImageUrl(value) {
    const raw = cleanString(value);
    if (!raw) return "";
    try {
      const url = new URL(raw, document.baseURI);
      return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
    } catch (_error) {
      return "";
    }
  }

  function normalizeImage(raw, fallbackAlt) {
    if (!raw || typeof raw !== "object") return null;
    const image = cleanImageUrl(raw.image);
    if (!image) return null;
    return {
      image,
      alt: cleanString(raw.image_alt) || fallbackAlt,
      attribution: cleanString(raw.image_attribution),
      license: cleanString(raw.image_license),
      licenseUrl: cleanOnlineUrl(raw.image_license_url),
      sourceUrl: cleanOnlineUrl(raw.image_source_url)
    };
  }

  function normalizeSearch(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLocaleLowerCase();
  }

  function normalizeTarget(raw) {
    if (!raw || typeof raw !== "object") return null;

    const id = raw.id === undefined || raw.id === null ? "" : String(raw.id).trim();
    const group = cleanString(raw.group).toLocaleLowerCase();
    if (!id || !GROUP_LABELS[group]) return null;

    const commonName = cleanString(raw.common_name) || "Unnamed target";
    const scientificName = cleanString(raw.scientific_name);
    const activeMonths = Array.isArray(raw.active_months)
      ? [...new Set(raw.active_months.map(Number).filter((month) => Number.isInteger(month) && month >= 1 && month <= 12))].sort((a, b) => a - b)
      : [];
    const regionalValue = Number(raw.regional_count);
    const habitatTags = cleanStringList(raw.habitat_tags);
    const methodTags = cleanStringList(raw.method_tags);
    const findingHelp = cleanStringList(raw.finding_help);
    const idHelp = cleanStringList(raw.id_help);
    const photoChecklist = cleanStringList(raw.photo_checklist);
    const images = (Array.isArray(raw.images) ? raw.images : [])
      .map((image, index) => normalizeImage(
        image,
        `Reference photograph ${index + 1} of ${commonName}${scientificName ? ` (${scientificName})` : ""}`
      ))
      .filter(Boolean);
    const legacyImage = normalizeImage(raw, `Reference photograph of ${commonName}${scientificName ? ` (${scientificName})` : ""}`);
    if (!images.length && legacyImage) images.push(legacyImage);

    const lookalikes = Array.isArray(raw.lookalikes)
      ? raw.lookalikes
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          name: cleanString(item.name) || "Unnamed lookalike",
          scientificName: cleanString(item.scientific_name),
          distinction: cleanString(item.distinction),
          traits: cleanTraits(item.traits),
          decision: cleanString(item.decision),
          image: normalizeImage(
            item,
            `Reference photograph of ${cleanString(item.name) || cleanString(item.scientific_name) || "a lookalike"}`
          )
        }))
      : [];

    const target = {
      id,
      group,
      commonName,
      scientificName,
      familyName: cleanString(raw.family_name),
      familyCommon: cleanString(raw.family_common),
      images,
      regionalCount: Number.isFinite(regionalValue) && regionalValue >= 0 ? Math.round(regionalValue) : null,
      seasonLabel: cleanString(raw.season_label) || seasonFromMonths(activeMonths),
      activeMonths,
      habitatTags,
      methodTags,
      targetReason: cleanString(raw.target_reason),
      findingHelp,
      idHelp,
      idTraits: cleanTraits(raw.id_traits),
      lookalikes,
      photoChecklist,
      idLimitations: cleanString(raw.id_limitations),
      taxonUrl: cleanOnlineUrl(raw.taxon_url)
    };

    target.searchText = normalizeSearch([
      target.commonName,
      target.scientificName,
      target.familyName,
      target.familyCommon,
      target.targetReason,
      ...target.habitatTags,
      ...target.methodTags,
      ...target.findingHelp,
      ...target.idHelp
    ].join(" "));
    return target;
  }

  function seasonFromMonths(months) {
    if (!months.length) return "Timing not listed";
    if (months.length === 1) return MONTH_NAMES[months[0] - 1];
    return `${MONTH_SHORT[months[0] - 1]} to ${MONTH_SHORT[months[months.length - 1] - 1]}`;
  }

  function formatTag(value) {
    const spaced = String(value).replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
    return spaced ? spaced.charAt(0).toLocaleUpperCase() + spaced.slice(1) : "";
  }

  function formatDataDate(value) {
    const raw = cleanString(value);
    if (!raw) return "Unknown";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw.slice(0, 10);
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric"
    }).format(date);
  }

  function groupLabel(group) {
    return GROUP_LABELS[group] || "Targets";
  }

  function regionalLabel(count) {
    if (count === null) return "";
    return `${count.toLocaleString()} nearby ${count === 1 ? "record" : "records"}`;
  }

  function setLoadingState() {
    elements.targetList.hidden = true;
    elements.statePanel.hidden = false;
    elements.statePanel.className = "state-panel loading-state";
    elements.statePanel.setAttribute("aria-busy", "true");
    elements.statePanel.replaceChildren();

    const announcement = makeElement("p", "sr-only", "Loading target list...");
    const grid = makeElement("div", "skeleton-grid");
    grid.setAttribute("aria-hidden", "true");
    for (let index = 0; index < 3; index += 1) {
      const card = makeElement("div", "skeleton-card");
      card.append(document.createElement("span"), document.createElement("i"), document.createElement("i"), document.createElement("i"));
      grid.append(card);
    }
    elements.statePanel.append(announcement, grid);
    elements.resultCount.textContent = "Loading target list...";
  }

  function showState(title, message, actionLabel, action, isError = false) {
    elements.targetList.hidden = true;
    elements.statePanel.hidden = false;
    elements.statePanel.className = "state-panel";
    elements.statePanel.removeAttribute("aria-busy");

    const copy = makeElement("div", `state-copy${isError ? " error-state" : ""}`);
    copy.append(makeElement("h3", "", title), makeElement("p", "", message));
    if (actionLabel && action) {
      const button = makeElement("button", "", actionLabel);
      button.type = "button";
      button.addEventListener("click", action, { once: true });
      copy.append(button);
    }
    elements.statePanel.replaceChildren(copy);
  }

  function populateSelect(select, values, firstLabel) {
    const current = select.value;
    const fragment = document.createDocumentFragment();
    const first = document.createElement("option");
    first.value = "";
    first.textContent = firstLabel;
    fragment.append(first);

    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = formatTag(value);
      fragment.append(option);
    });
    select.replaceChildren(fragment);
    if (values.includes(current)) select.value = current;
  }

  function populateFilters() {
    const habitats = [...new Set(state.targets.flatMap((target) => target.habitatTags))]
      .sort((a, b) => formatTag(a).localeCompare(formatTag(b)));
    const methods = [...new Set(state.targets.flatMap((target) => target.methodTags))]
      .sort((a, b) => formatTag(a).localeCompare(formatTag(b)));
    populateSelect(elements.habitat, habitats, "Any habitat");
    populateSelect(elements.method, methods, "Any method");
  }

  async function loadTargets() {
    setLoadingState();
    try {
      const response = await fetch("./targets.json", {
        headers: { accept: "application/json" }
      });
      if (!response.ok) throw new Error(`Target data returned ${response.status}`);

      const payload = await response.json();
      if (!payload || typeof payload !== "object" || !Array.isArray(payload.targets)) {
        throw new Error("Target data has an unexpected shape");
      }

      const seen = new Set();
      const targets = payload.targets
        .map(normalizeTarget)
        .filter((target) => {
          if (!target || seen.has(target.id)) return false;
          seen.add(target.id);
          return true;
        });
      if (payload.targets.length > 0 && targets.length === 0) {
        throw new Error("Target data contains no usable records");
      }

      state.data = {
        version: payload.version === undefined || payload.version === null ? "" : String(payload.version),
        generatedAt: cleanString(payload.generated_at),
        counts: payload.counts && typeof payload.counts === "object" ? payload.counts : {}
      };
      state.targets = targets;
      elements.dataDate.textContent = formatDataDate(state.data.generatedAt);
      if (state.data.generatedAt) elements.dataDate.dateTime = state.data.generatedAt;
      populateFilters();
      renderTargets();
      syncDetailFromLocation(history.state, true);
      if (state.registration) verifyOfflineCopy();
    } catch (error) {
      console.error(error);
      state.data = null;
      state.targets = [];
      elements.dataDate.textContent = "Unavailable";
      elements.resultCount.textContent = "No data";
      const message = navigator.onLine
        ? "The target data could not be read. Check the data file and try again."
        : "This target list is not stored on this device yet. Connect to the internet and try again.";
      showState("Targets could not load", message, "Retry", loadTargets, true);
    }
  }

  function filteredTargets() {
    const query = normalizeSearch(state.query.trim());
    return state.targets.filter((target) => {
      if (state.group !== "all" && target.group !== state.group) return false;
      if (state.habitat && !target.habitatTags.includes(state.habitat)) return false;
      if (state.method && !target.methodTags.includes(state.method)) return false;
      return !query || target.searchText.includes(query);
    });
  }

  function createImageFrame(imageData, fallbackText, className, eager = false) {
    const frame = makeElement("div", className);
    const fallback = makeElement("span", "image-fallback", fallbackText);

    if (imageData?.image) {
      const image = document.createElement("img");
      image.src = imageData.image;
      image.alt = imageData.alt;
      image.loading = eager ? "eager" : "lazy";
      image.decoding = "async";
      fallback.hidden = true;
      image.addEventListener("error", () => {
        image.hidden = true;
        fallback.hidden = false;
      }, { once: true });
      frame.append(image, fallback);
    } else {
      frame.append(fallback);
    }
    return frame;
  }

  function createReferenceGallery(target, className, eager = false) {
    const gallery = makeElement("div", className);
    const photos = target.images.slice(0, 2);
    photos.forEach((image, index) => {
      const frame = createImageFrame(
        image,
        `${groupLabel(target.group)} reference image not available`,
        "reference-media",
        eager && index === 0
      );
      gallery.append(frame);
    });
    if (!photos.length) {
      gallery.append(createImageFrame(null, `${groupLabel(target.group)} image not available`, "reference-media"));
    }
    return gallery;
  }

  function createMonthRail(target, detailed = false) {
    const active = new Set(target.activeMonths);
    const activeText = target.activeMonths.length
      ? target.activeMonths.map((month) => MONTH_NAMES[month - 1]).join(", ")
      : "not listed";

    if (detailed) {
      const rail = makeElement("div", "detail-months");
      rail.setAttribute("role", "img");
      rail.setAttribute("aria-label", `Active months: ${activeText}. Current month: ${MONTH_NAMES[CURRENT_MONTH - 1]}.`);
      MONTH_SHORT.forEach((label, index) => {
        const month = index + 1;
        const item = makeElement("span", `detail-month${active.has(month) ? " is-active" : ""}${month === CURRENT_MONTH ? " is-current" : ""}`);
        item.setAttribute("aria-hidden", "true");
        item.append(makeElement("span", "", label));
        rail.append(item);
      });
      return rail;
    }

    const rail = makeElement("div", "month-rail");
    rail.setAttribute("role", "img");
    rail.setAttribute("aria-label", `Active months: ${activeText}`);
    MONTH_NAMES.forEach((_label, index) => {
      const month = index + 1;
      const mark = makeElement("span", `${active.has(month) ? "is-active" : ""}${month === CURRENT_MONTH ? `${active.has(month) ? " " : ""}is-current` : ""}`);
      mark.setAttribute("aria-hidden", "true");
      rail.append(mark);
    });
    return rail;
  }

  function createTagList(target, includeAll = false) {
    const habitatLimit = includeAll ? target.habitatTags.length : 2;
    const methodLimit = includeAll ? target.methodTags.length : 1;
    const tags = [
      ...target.habitatTags.slice(0, habitatLimit).map((value) => ({ value, method: false })),
      ...target.methodTags.slice(0, methodLimit).map((value) => ({ value, method: true }))
    ];
    if (!tags.length) return null;

    const list = makeElement("ul", "tag-list");
    tags.forEach((tag) => list.append(makeElement("li", tag.method ? "method-tag" : "", formatTag(tag.value))));
    return list;
  }

  function createTargetCard(target, index) {
    const item = document.createElement("li");
    const card = makeElement("article", `target-card group-${target.group}`);
    const button = makeElement("button", "card-open");
    button.type = "button";
    button.dataset.targetId = target.id;
    button.setAttribute("aria-label", `Open ${target.commonName} details`);

    const media = createReferenceGallery(target, "card-media-grid");
    media.append(makeElement("span", "group-badge", groupLabel(target.group)));

    const body = makeElement("div", "card-body");
    const heading = makeElement("div", "card-heading");
    const headingId = `target-name-${index}`;
    const name = makeElement("h3", "", target.commonName);
    name.id = headingId;
    heading.append(name);
    if (target.scientificName) heading.append(makeElement("p", "scientific-name", target.scientificName));

    const season = makeElement("div", "season-row");
    season.append(makeElement("span", "season-label", target.seasonLabel));
    const regional = regionalLabel(target.regionalCount);
    if (regional) season.append(makeElement("span", "regional-count", regional));

    body.append(heading, season, createMonthRail(target));
    const reason = target.targetReason || target.findingHelp[0];
    if (reason) body.append(makeElement("p", "target-reason", reason));
    const tags = createTagList(target);
    if (tags) body.append(tags);

    const chevron = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    chevron.setAttribute("class", "card-chevron");
    chevron.setAttribute("viewBox", "0 0 24 24");
    chevron.setAttribute("aria-hidden", "true");
    const chevronPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    chevronPath.setAttribute("d", "m9 5 7 7-7 7");
    chevron.append(chevronPath);

    card.append(button, media, body, chevron);
    item.append(card);
    return item;
  }

  function renderTargets() {
    const matches = filteredTargets();
    const total = state.targets.length;
    const noun = matches.length === 1 ? "target" : "targets";
    elements.resultCount.textContent = matches.length === total
      ? `${matches.length} ${noun}`
      : `${matches.length} of ${total} targets`;
    updateFilterCount();

    if (!matches.length) {
      const hasFilters = state.group !== "all" || state.query || state.habitat || state.method;
      const message = total === 0
        ? "No field targets are included in this data release."
        : "Try another group, search term, habitat, or method.";
      showState(
        hasFilters ? "No targets match" : "No targets available",
        message,
        hasFilters ? "Clear filters" : "Retry",
        hasFilters ? clearAllFilters : loadTargets
      );
      return;
    }

    const fragment = document.createDocumentFragment();
    matches.forEach((target, index) => fragment.append(createTargetCard(target, index)));
    elements.targetList.replaceChildren(fragment);
    elements.targetList.hidden = false;
    elements.statePanel.hidden = true;
    elements.statePanel.removeAttribute("aria-busy");
  }

  function updateFilterCount() {
    const count = Number(Boolean(state.habitat)) + Number(Boolean(state.method));
    elements.filterCount.textContent = String(count);
    elements.filterCount.hidden = count === 0;
    elements.filterCount.setAttribute("aria-label", `${count} active ${count === 1 ? "filter" : "filters"}`);
  }

  function clearAllFilters() {
    state.group = "all";
    state.query = "";
    state.habitat = "";
    state.method = "";
    elements.form.reset();
    elements.search.value = "";
    elements.habitat.value = "";
    elements.method.value = "";
    renderTargets();
    elements.resultsHeading.focus({ preventScroll: true });
  }

  function appendTextListSection(container, title, items, listClass = "guidance-list") {
    if (!items.length) return;
    const section = makeElement("section", "detail-section");
    section.append(makeElement("h3", "", title));
    const list = makeElement("ul", listClass);
    items.forEach((item) => list.append(makeElement("li", "", item)));
    section.append(list);
    container.append(section);
  }

  function appendTraitList(container, traits, listClass = "trait-list") {
    if (!traits.length) return;
    const list = makeElement("ul", listClass);
    traits.forEach((trait) => {
      const item = makeElement("li", "");
      item.append(makeElement("strong", "trait-label", `${trait.label}: `), document.createTextNode(trait.detail));
      list.append(item);
    });
    container.append(list);
  }

  function appendLookalikes(container, target) {
    const lookalikes = target.lookalikes;
    if (!lookalikes.length) return;
    const section = makeElement("section", "detail-section");
    section.append(makeElement("h3", "", "Lookalikes"));
    const list = makeElement("ul", "lookalike-list");
    lookalikes.forEach((lookalike) => {
      const item = document.createElement("li");
      const comparison = makeElement("div", "comparison-photo-grid");
      const targetPhoto = target.images[0] || null;
      const targetFigure = document.createElement("figure");
      targetFigure.append(
        createImageFrame(targetPhoto, `${target.commonName} image not available`, "comparison-media"),
        makeElement("figcaption", "comparison-label", target.commonName)
      );
      const peerFigure = document.createElement("figure");
      peerFigure.append(
        createImageFrame(lookalike.image, `${lookalike.name} image not available`, "comparison-media"),
        makeElement("figcaption", "comparison-label", lookalike.name)
      );
      comparison.append(targetFigure, peerFigure);
      item.append(comparison);
      const name = makeElement("div", "lookalike-name");
      name.append(makeElement("strong", "", lookalike.name));
      if (lookalike.scientificName) name.append(makeElement("em", "", lookalike.scientificName));
      item.append(name);
      if (lookalike.traits.length) {
        item.append(makeElement("p", "comparison-intro", `Check these traits against ${target.commonName}:`));
        appendTraitList(item, lookalike.traits, "comparison-trait-list");
      } else if (lookalike.distinction) {
        item.append(makeElement("p", "", lookalike.distinction));
      }
      if (lookalike.decision) item.append(makeElement("p", "comparison-decision", lookalike.decision));
      list.append(item);
    });
    section.append(list);
    container.append(section);
  }

  function createOnlineLink(label, url) {
    if (!url) return null;
    const link = makeElement("a", "online-link", `${label} / Online`);
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", `${label}, online, opens in a new tab`);
    return link;
  }

  function appendCredits(container, target) {
    const hasCredits = target.images.length || target.taxonUrl;
    if (!hasCredits) return;

    const section = makeElement("section", "detail-section");
    section.append(makeElement("h3", "", "Record and image"));
    const creditLines = makeElement("div", "credit-lines");
    target.images.forEach((image, index) => {
      const source = [image.attribution, image.license].filter(Boolean).join(" · ");
      if (source) creditLines.append(makeElement("p", "", `Reference ${index + 1}: ${source}`));
    });
    target.lookalikes.forEach((lookalike) => {
      const image = lookalike.image;
      const source = [image?.attribution, image?.license].filter(Boolean).join(" · ");
      if (source) creditLines.append(makeElement("p", "", `Comparison ${lookalike.name}: ${source}`));
    });
    if (creditLines.childElementCount) section.append(creditLines);

    const links = makeElement("div", "online-links");
    const taxonLink = createOnlineLink("View taxon on iNaturalist", target.taxonUrl);
    if (taxonLink) links.append(taxonLink);
    target.images.forEach((image, index) => {
      const sourceLink = createOnlineLink(`Reference ${index + 1} image`, image.sourceUrl);
      const licenseLink = createOnlineLink(`Reference ${index + 1} license`, image.licenseUrl);
      if (sourceLink) links.append(sourceLink);
      if (licenseLink) links.append(licenseLink);
    });
    target.lookalikes.forEach((lookalike) => {
      const image = lookalike.image;
      const sourceLink = createOnlineLink(`${lookalike.name} image`, image?.sourceUrl);
      const licenseLink = createOnlineLink(`${lookalike.name} license`, image?.licenseUrl);
      if (sourceLink) links.append(sourceLink);
      if (licenseLink) links.append(licenseLink);
    });
    if (links.childElementCount) section.append(links);
    container.append(section);
  }

  function renderDetail(target) {
    elements.dialogGroup.textContent = `${groupLabel(target.group)} field target`;
    elements.dialogTitle.textContent = target.commonName;

    const hero = makeElement("div", "detail-hero");
    hero.append(createReferenceGallery(target, "detail-reference-grid", true));

    const summary = makeElement("div", "detail-summary");
    if (target.scientificName) summary.append(makeElement("p", "detail-scientific", target.scientificName));
    const familyParts = [target.familyCommon, target.familyName].filter(Boolean);
    if (familyParts.length) summary.append(makeElement("p", "family-line", familyParts.join(" / ")));

    const seasonRow = makeElement("div", "detail-season-row");
    seasonRow.append(makeElement("strong", "", target.seasonLabel));
    const regional = regionalLabel(target.regionalCount);
    if (regional) seasonRow.append(makeElement("span", "regional-count", regional));
    summary.append(seasonRow, createMonthRail(target, true));

    const tags = createTagList(target, true);
    if (tags) summary.append(tags);
    if (target.targetReason) {
      const reason = makeElement("p", "detail-reason");
      reason.append(makeElement("strong", "", "Why target it: "), document.createTextNode(target.targetReason));
      summary.append(reason);
    }
    hero.append(summary);

    const sections = makeElement("div", "detail-sections");
    appendTextListSection(sections, "Where to look", target.findingHelp);
    if (target.idTraits.length) {
      const identification = makeElement("section", "detail-section");
      identification.append(makeElement("h3", "", "Traits to check"));
      appendTraitList(identification, target.idTraits);
      sections.append(identification);
    } else {
      appendTextListSection(sections, "Traits to check", target.idHelp);
    }
    appendLookalikes(sections, target);
    appendTextListSection(sections, "Photographs to take", target.photoChecklist, "photo-list");
    if (target.idLimitations) {
      const limitations = makeElement("section", "detail-section");
      limitations.append(makeElement("h3", "", "Identification limits"), makeElement("p", "", target.idLimitations));
      sections.append(limitations);
    }
    appendCredits(sections, target);
    elements.dialogContent.replaceChildren(hero, sections);
  }

  function targetIdFromLocation() {
    if (!location.hash.startsWith("#")) return "";
    return new URLSearchParams(location.hash.slice(1)).get("target") || "";
  }

  function locationWithoutHash() {
    return `${location.pathname}${location.search}`;
  }

  function openDetail(target, trigger, pushHistory) {
    if (!target) return;
    state.detailId = target.id;
    if (trigger) state.detailTrigger = trigger;
    renderDetail(target);

    if (!elements.dialog.open) elements.dialog.showModal();
    if (pushHistory) {
      const nextUrl = `${locationWithoutHash()}#target=${encodeURIComponent(target.id)}`;
      history.pushState({ fieldTarget: target.id }, "", nextUrl);
      state.detailHistoryOwned = true;
    }
    requestAnimationFrame(() => elements.dialogClose.focus({ preventScroll: true }));
  }

  function finishClosingDetail() {
    if (elements.dialog.open) elements.dialog.close();
    const trigger = state.detailTrigger;
    state.detailId = null;
    state.detailHistoryOwned = false;
    state.detailTrigger = null;
    state.closingFromHistory = false;
    requestAnimationFrame(() => {
      if (trigger && document.contains(trigger)) trigger.focus({ preventScroll: true });
      else elements.resultsHeading.focus({ preventScroll: true });
    });
  }

  function requestDetailClose() {
    if (!elements.dialog.open) return;
    const currentId = targetIdFromLocation();
    if (state.detailHistoryOwned && currentId === state.detailId) {
      state.closingFromHistory = true;
      history.back();
      return;
    }
    if (currentId) history.replaceState(null, "", locationWithoutHash());
    finishClosingDetail();
  }

  function syncDetailFromLocation(historyState, ensureBackEntry = false) {
    if (!state.targets.length && !state.data) return;
    const targetId = targetIdFromLocation();
    if (!targetId) {
      if (elements.dialog.open) finishClosingDetail();
      return;
    }

    const target = state.targets.find((item) => item.id === targetId);
    if (!target) {
      history.replaceState(null, "", locationWithoutHash());
      if (elements.dialog.open) finishClosingDetail();
      return;
    }
    if (ensureBackEntry && (!historyState || historyState.fieldTarget !== targetId)) {
      const targetUrl = `${locationWithoutHash()}#target=${encodeURIComponent(targetId)}`;
      history.replaceState({ fieldBase: true }, "", locationWithoutHash());
      history.pushState({ fieldTarget: targetId }, "", targetUrl);
      historyState = { fieldTarget: targetId };
    }
    state.detailHistoryOwned = Boolean(historyState && historyState.fieldTarget === targetId);
    openDetail(target, null, false);
  }

  function updateNetworkState() {
    const online = navigator.onLine;
    elements.networkState.dataset.online = String(online);
    elements.networkLabel.textContent = online ? "Online" : "Offline";
  }

  function setOfflineState(phase, detail = {}) {
    state.offlinePhase = phase;
    const completed = Number(detail.completed ?? detail.complete ?? detail.cached ?? detail.current);
    const total = Number(detail.total ?? detail.count);
    const hasProgress = Number.isFinite(completed) && Number.isFinite(total) && total > 0;
    const states = {
      checking: ["Checking offline copy...", "Download offline", true],
      unavailable: ["Offline copy not checked", "Retry offline", false],
      "not-ready": ["Not downloaded", "Download offline", false],
      stale: ["Update available", "Update offline", false],
      downloading: [hasProgress ? `Saving ${completed} of ${total}...` : "Saving field guide...", "Downloading...", true],
      verifying: ["Verifying offline copy...", "Verifying...", true],
      ready: ["Ready offline", "Update offline", false],
      error: [cleanString(detail.message) || "Offline setup failed", "Retry offline", false],
      unsupported: ["Offline setup unavailable", "Offline unavailable", true]
    };
    const current = states[phase] || states.error;
    elements.offlineStatus.textContent = current[0];
    elements.offlineActionLabel.textContent = current[1];
    elements.offlineAction.disabled = current[2];
  }

  function workerForScope() {
    const worker = navigator.serviceWorker.controller
      || state.registration?.active
      || state.registration?.waiting
      || state.registration?.installing;
    if (!worker) return null;
    const scopeUrl = new URL("./", location.href).href;
    return worker.scriptURL.startsWith(scopeUrl) ? worker : null;
  }

  function sendWorkerCommand(type) {
    const worker = workerForScope();
    if (!worker) return false;

    const payload = {
      type,
      action: type === "PREPARE_OFFLINE" ? "prepare" : "verify",
      version: state.data?.version || null,
      generated_at: state.data?.generatedAt || null,
      data_url: new URL("./targets.json", location.href).href
    };

    if ("MessageChannel" in window) {
      const channel = new MessageChannel();
      channel.port1.addEventListener("message", (event) => handleWorkerMessage(event.data));
      channel.port1.start();
      worker.postMessage(payload, [channel.port2]);
    } else {
      worker.postMessage(payload);
    }
    return true;
  }

  function armOfflineTimeout() {
    window.clearTimeout(state.offlineTimer);
    state.offlineTimer = window.setTimeout(() => {
      if (state.offlinePhase === "checking" || state.offlinePhase === "verifying") {
        setOfflineState("unavailable");
      }
    }, 8000);
  }

  function verifyOfflineCopy() {
    if (!state.registration) return;
    setOfflineState("verifying");
    if (!sendWorkerCommand("OFFLINE_STATUS")) {
      setOfflineState("unavailable");
      return;
    }
    armOfflineTimeout();
  }

  function normalizedWorkerStatus(message) {
    const type = cleanString(message.type).replace(/[-\s]+/g, "_").toLocaleUpperCase();
    const status = cleanString(message.status || message.state).replace(/[-\s]+/g, "_").toLocaleUpperCase();
    return { type, status, combined: `${type} ${status}` };
  }

  function handleWorkerMessage(message) {
    if (!message || typeof message !== "object") return;
    const { type, status, combined } = normalizedWorkerStatus(message);
    const relevant = /OFFLINE|CACHE|PREPARE|VERIFY|VERIFIED|READY/.test(combined)
      || message.ready !== undefined
      || message.verified !== undefined;
    if (!relevant) return;

    window.clearTimeout(state.offlineTimer);
    const reportedVersion = message.version === undefined || message.version === null ? "" : String(message.version);
    const versionMismatch = Boolean(state.data?.version && reportedVersion && state.data.version !== reportedVersion);
    const reportsReady = message.ready === true
      || message.verified === true
      || status === "READY"
      || status === "VERIFIED"
      || type === "OFFLINE_READY"
      || type === "OFFLINE_VERIFIED";

    if (reportsReady) {
      setOfflineState(versionMismatch ? "stale" : "ready");
      return;
    }
    if (/ERROR|FAILED|FAILURE/.test(combined) || message.error) {
      setOfflineState("error", { message: cleanString(message.error || message.message) });
      return;
    }
    if (/STALE|OUTDATED|UPDATE_AVAILABLE/.test(combined)) {
      setOfflineState("stale");
      return;
    }
    if (/PROGRESS|DOWNLOADING|CACHING|SAVING/.test(combined)) {
      setOfflineState("downloading", message);
      return;
    }
    if (/PREPARED|PREPARE_COMPLETE/.test(combined) || (message.complete === true && /PREPARE/.test(combined))) {
      setOfflineState("verifying");
      sendWorkerCommand("OFFLINE_STATUS");
      armOfflineTimeout();
      return;
    }
    if (/VERIFYING|CHECKING/.test(combined)) {
      setOfflineState("verifying");
      armOfflineTimeout();
      return;
    }
    if (/NOT_READY|MISSING|INCOMPLETE|PARTIAL|EMPTY/.test(combined) || message.complete === false || message.ready === false) {
      setOfflineState("not-ready");
    }
  }

  async function initServiceWorker() {
    if (!("serviceWorker" in navigator) || !window.isSecureContext) {
      setOfflineState("unsupported");
      return;
    }

    navigator.serviceWorker.addEventListener("message", (event) => handleWorkerMessage(event.data));
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      loadTargets().then(() => verifyOfflineCopy());
    });
    try {
      state.registration = await navigator.serviceWorker.register("./service-worker.js", {
        scope: "./",
        updateViaCache: "none"
      });
      if (navigator.onLine) {
        try {
          await state.registration.update();
        } catch (error) {
          console.warn("Could not check for a newer field guide release", error);
        }
      }
      await navigator.serviceWorker.ready;
      verifyOfflineCopy();
    } catch (error) {
      console.error(error);
      setOfflineState("error", { message: "Offline setup unavailable" });
    }
  }

  function bindEvents() {
    elements.form.addEventListener("submit", (event) => event.preventDefault());
    elements.form.addEventListener("change", (event) => {
      if (event.target.name === "group") state.group = event.target.value;
      if (event.target === elements.habitat) state.habitat = elements.habitat.value;
      if (event.target === elements.method) state.method = elements.method.value;
      renderTargets();
    });
    elements.search.addEventListener("input", () => {
      state.query = elements.search.value;
      renderTargets();
    });
    elements.filterToggle.addEventListener("click", () => {
      const expanded = elements.filterToggle.getAttribute("aria-expanded") === "true";
      elements.filterToggle.setAttribute("aria-expanded", String(!expanded));
      elements.filterPanel.hidden = expanded;
    });
    elements.clearFilters.addEventListener("click", clearAllFilters);
    elements.targetList.addEventListener("click", (event) => {
      const button = event.target.closest(".card-open");
      if (!button) return;
      const target = state.targets.find((item) => item.id === button.dataset.targetId);
      openDetail(target, button, true);
    });
    elements.dialogClose.addEventListener("click", requestDetailClose);
    elements.dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      requestDetailClose();
    });
    elements.dialog.addEventListener("pointerdown", (event) => {
      if (event.target === elements.dialog) requestDetailClose();
    });
    elements.offlineAction.addEventListener("click", () => {
      if (!navigator.onLine) {
        verifyOfflineCopy();
        return;
      }
      setOfflineState("downloading");
      if (!sendWorkerCommand("PREPARE_OFFLINE")) {
        setOfflineState("error", { message: "Offline worker is not ready" });
      }
    });
    window.addEventListener("popstate", (event) => {
      state.closingFromHistory = false;
      syncDetailFromLocation(event.state);
    });
    window.addEventListener("online", () => {
      updateNetworkState();
      if (state.registration && state.offlinePhase !== "downloading") verifyOfflineCopy();
    });
    window.addEventListener("offline", updateNetworkState);
  }

  function init() {
    bindEvents();
    updateNetworkState();
    setOfflineState("checking");
    initServiceWorker();
    loadTargets();
  }

  init();
})();
