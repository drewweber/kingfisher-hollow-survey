const REPO_OWNER = "drewweber";
const REPO_NAME = "kingfisher-hollow-survey";
const WORKFLOW_FILE = "update.yml";
const REF = "main";

function json(body, init = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      ...(init.headers || {}),
    },
  });
}

export async function onRequestGet() {
  return json({
    ok: true,
    message: "POST to this endpoint to trigger the survey update workflow.",
  });
}

export async function onRequestPost({ request, env }) {
  const expectedKey = env.UPDATE_TRIGGER_KEY;
  const githubToken = env.GITHUB_DISPATCH_TOKEN;

  if (!expectedKey || !githubToken) {
    return json({
      ok: false,
      error: "Update trigger is not configured.",
      detail: "Set UPDATE_TRIGGER_KEY and GITHUB_DISPATCH_TOKEN in Cloudflare Pages.",
    }, { status: 503 });
  }

  const providedKey = request.headers.get("x-kh-update-key") || "";
  if (providedKey !== expectedKey) {
    return json({ ok: false, error: "Unauthorized." }, { status: 401 });
  }

  const url = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "accept": "application/vnd.github+json",
      "authorization": `Bearer ${githubToken}`,
      "content-type": "application/json",
      "user-agent": "kingfisher-hollow-survey-update-button",
      "x-github-api-version": "2022-11-28",
    },
    body: JSON.stringify({ ref: REF }),
  });

  if (!response.ok) {
    const text = await response.text();
    return json({
      ok: false,
      error: "GitHub did not start the workflow.",
      status: response.status,
      detail: text.slice(0, 1000),
    }, { status: 502 });
  }

  return json({
    ok: true,
    message: "Survey update started.",
    workflow: `https://github.com/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${WORKFLOW_FILE}`,
  }, { status: 202 });
}
