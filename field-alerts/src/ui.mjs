export function checkerPage() {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#123c32">
  <title>KH Field Alert</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #17211e;
      --muted: #5e6965;
      --line: #d9dfdc;
      --green: #17624f;
      --green-dark: #123c32;
      --green-pale: #e3f2ec;
      --red: #a52b2b;
      --red-pale: #fae7e7;
      --yellow: #7a5700;
      --yellow-pale: #fff2c9;
      --surface: #ffffff;
      --page: #f2f5f4;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--page);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      background: var(--green-dark);
      color: white;
      padding: 22px 20px;
    }
    header div, main { width: min(100% - 32px, 680px); margin: 0 auto; }
    h1 { margin: 0; font-family: Georgia, serif; font-size: 28px; font-weight: 600; }
    header p { margin: 7px 0 0; color: #c8d9d3; font-size: 14px; line-height: 1.5; }
    main { padding: 24px 0 48px; }
    .tool {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 4px 18px rgba(18, 60, 50, 0.07);
    }
    form { display: grid; gap: 16px; }
    label { display: block; margin-bottom: 7px; font-size: 14px; font-weight: 650; }
    input[type="text"], input[type="password"] {
      width: 100%;
      min-height: 48px;
      border: 1px solid #abb6b1;
      border-radius: 6px;
      padding: 11px 12px;
      color: var(--ink);
      background: white;
      font: inherit;
      font-size: 16px;
    }
    input:focus-visible, button:focus-visible {
      outline: 3px solid #7bc7ad;
      outline-offset: 2px;
    }
    .checks { display: flex; flex-wrap: wrap; gap: 12px 22px; }
    .check { display: flex; align-items: center; gap: 8px; font-size: 14px; }
    .check input { width: 18px; height: 18px; accent-color: var(--green); }
    button {
      min-height: 48px;
      border: 0;
      border-radius: 6px;
      padding: 11px 18px;
      background: var(--green);
      color: white;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled { opacity: 0.55; cursor: wait; }
    .status { min-height: 20px; margin: 12px 0 0; color: var(--muted); font-size: 14px; }
    .status.error { color: var(--red); }
    .result { margin-top: 20px; border-top: 1px solid var(--line); padding-top: 20px; }
    .result[hidden] { display: none; }
    .badge {
      display: inline-block;
      border-radius: 4px;
      padding: 5px 8px;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .badge.red { color: var(--red); background: var(--red-pale); }
    .badge.yellow { color: var(--yellow); background: var(--yellow-pale); }
    .badge.none, .badge.unresolved { color: var(--green-dark); background: var(--green-pale); }
    h2 { margin: 12px 0 2px; font-family: Georgia, serif; font-size: 25px; }
    .scientific { margin: 0; color: var(--muted); font-style: italic; }
    .headline { margin: 15px 0 0; font-weight: 750; font-size: 17px; }
    .counts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; margin: 16px 0; background: var(--line); border: 1px solid var(--line); }
    .count { background: white; padding: 11px 8px; text-align: center; }
    .count strong { display: block; font-family: Georgia, serif; font-size: 24px; }
    .count span { color: var(--muted); font-size: 11px; text-transform: uppercase; }
    h3 { margin: 18px 0 8px; font-size: 15px; }
    ul { margin: 0; padding-left: 21px; }
    li { margin: 7px 0; line-height: 1.45; }
    .caveat { margin: 18px 0 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
    .obs-link { display: inline-block; margin-top: 16px; color: var(--green); font-weight: 700; }
    @media (max-width: 480px) {
      header div, main { width: min(100% - 24px, 680px); }
      .tool { padding: 16px; }
      .counts { grid-template-columns: 1fr; }
      .count { display: flex; justify-content: space-between; align-items: center; text-align: left; }
      .count strong { font-size: 21px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>KH Field Alert</h1>
      <p>Check a Kingfisher Hollow moth while it is still available for more photographs.</p>
    </div>
  </header>
  <main>
    <section class="tool" aria-labelledby="checker-title">
      <form id="checker-form">
        <div>
          <label id="checker-title" for="observation">iNaturalist observation</label>
          <input id="observation" name="observation" type="text" inputmode="url" autocomplete="off" placeholder="Paste URL or observation number" required>
        </div>
        <div>
          <label for="access-key">Access key</label>
          <input id="access-key" name="access-key" type="password" autocomplete="current-password" required>
        </div>
        <div class="checks">
          <label class="check"><input id="remember" type="checkbox"> Remember key on this device</label>
          <label class="check"><input id="notify" type="checkbox" checked> Send an alert when notable</label>
        </div>
        <button id="submit" type="submit">Check observation</button>
      </form>
      <p id="status" class="status" role="status" aria-live="polite"></p>
      <section id="result" class="result" aria-live="polite" hidden>
        <span id="badge" class="badge"></span>
        <h2 id="species"></h2>
        <p id="scientific" class="scientific"></p>
        <p id="headline" class="headline"></p>
        <div id="counts" class="counts"></div>
        <h3>Why it was flagged</h3>
        <ul id="reasons"></ul>
        <div id="lookalike-section" hidden>
          <h3>Rule out these lookalikes</h3>
          <ul id="lookalikes"></ul>
        </div>
        <h3>Decisive photographs to take now</h3>
        <ul id="evidence"></ul>
        <p id="id-limitation" class="caveat" hidden></p>
        <p id="caveat" class="caveat"></p>
        <a id="obs-link" class="obs-link" target="_blank" rel="noopener">Open observation</a>
      </section>
    </section>
  </main>
  <script>
    const form = document.getElementById("checker-form");
    const keyInput = document.getElementById("access-key");
    const remember = document.getElementById("remember");
    const submit = document.getElementById("submit");
    const status = document.getElementById("status");
    const result = document.getElementById("result");
    const savedKey = localStorage.getItem("kh-field-alert-key");
    if (savedKey) { keyInput.value = savedKey; remember.checked = true; }

    function fillList(id, values) {
      const list = document.getElementById(id);
      list.textContent = "";
      for (const value of values || []) {
        const item = document.createElement("li");
        item.textContent = value;
        list.appendChild(item);
      }
    }

    function fillCounts(counts) {
      const root = document.getElementById("counts");
      root.textContent = "";
      root.hidden = !counts;
      if (!counts) return;
      for (const pair of [["Tioga", counts.county], ["80 km region", counts.regional], ["New York", counts.state]]) {
        const box = document.createElement("div");
        box.className = "count";
        const value = document.createElement("strong");
        value.textContent = String(pair[1]);
        const label = document.createElement("span");
        label.textContent = pair[0] + " earlier";
        box.append(value, label);
        root.appendChild(box);
      }
    }

    function render(assessment, notificationSent) {
      const badge = document.getElementById("badge");
      badge.className = "badge " + assessment.level;
      badge.textContent = assessment.level === "none" ? "No rarity alert" : assessment.level;
      document.getElementById("species").textContent = assessment.species;
      document.getElementById("scientific").textContent = assessment.scientificName;
      document.getElementById("headline").textContent = assessment.headline;
      document.getElementById("caveat").textContent = assessment.caveat;
      const link = document.getElementById("obs-link");
      link.href = assessment.observationUrl;
      fillCounts(assessment.priorCounts);
      fillList("reasons", assessment.reasons);
      const identification = assessment.identification;
      const comparisons = (identification?.comparisons || []).map((item) => item.label + " — " + item.difference);
      const lookalikeSection = document.getElementById("lookalike-section");
      lookalikeSection.hidden = comparisons.length === 0;
      fillList("lookalikes", comparisons);
      fillList("evidence", identification?.photoPriorities?.length
        ? identification.photoPriorities
        : assessment.evidence);
      const limitation = document.getElementById("id-limitation");
      limitation.textContent = identification?.limitation || "";
      limitation.hidden = !identification?.limitation;
      result.hidden = false;
      if (notificationSent) status.textContent = "Assessment complete and phone alert sent.";
      result.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      status.className = "status";
      status.textContent = "Checking regional records and likely lookalikes...";
      result.hidden = true;
      submit.disabled = true;
      if (remember.checked) localStorage.setItem("kh-field-alert-key", keyInput.value);
      else localStorage.removeItem("kh-field-alert-key");
      try {
        const response = await fetch("/api/check", {
          method: "POST",
          headers: {
            "authorization": "Bearer " + keyInput.value,
            "content-type": "application/json",
          },
          body: JSON.stringify({
            observation: document.getElementById("observation").value,
            notify: document.getElementById("notify").checked,
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "The observation could not be checked.");
        render(data.assessment, data.notificationSent);
        if (!data.notificationSent) status.textContent = "Assessment complete.";
      } catch (error) {
        status.className = "status error";
        status.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
  </script>
</body>
</html>`;
}
