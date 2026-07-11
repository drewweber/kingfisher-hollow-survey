import { notificationFor } from "./alert-core.mjs";

export async function sendNtfy(assessment, config, fetchFn = fetch) {
  if (!config.ntfyTopic) {
    throw new Error("NTFY_TOPIC is not configured.");
  }
  const notification = notificationFor(assessment);
  const headers = {
    "content-type": "text/plain; charset=utf-8",
    title: notification.title,
    priority: notification.priority,
    tags: notification.tags,
    click: notification.click,
  };
  if (config.ntfyToken) headers.authorization = `Bearer ${config.ntfyToken}`;

  const response = await fetchFn(`${config.ntfyServer}/${encodeURIComponent(config.ntfyTopic)}`, {
    method: "POST",
    headers,
    body: notification.message,
  });
  if (!response.ok) {
    throw new Error(`ntfy returned HTTP ${response.status}.`);
  }
  return true;
}
