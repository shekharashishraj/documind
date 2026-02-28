/* ── API helpers ─────────────────────────────────────────────────── */

const API_KEY_STORAGE = "maldoc_openai_key";
const API_KEY_SESSION = "maldoc_openai_key_session";

export function getStoredApiKey() {
  return sessionStorage.getItem(API_KEY_SESSION) || localStorage.getItem(API_KEY_STORAGE) || "";
}

export function setStoredApiKey(key, remember = false) {
  const trimmed = (key || "").trim();
  if (!trimmed) return;
  if (remember) {
    localStorage.setItem(API_KEY_STORAGE, trimmed);
    sessionStorage.removeItem(API_KEY_SESSION);
  } else {
    sessionStorage.setItem(API_KEY_SESSION, trimmed);
    localStorage.removeItem(API_KEY_STORAGE);
  }
}

export function clearStoredApiKey() {
  localStorage.removeItem(API_KEY_STORAGE);
  sessionStorage.removeItem(API_KEY_SESSION);
}

function buildHeaders(extra = {}) {
  const headers = { ...extra };
  const apiKey = getStoredApiKey();
  if (apiKey) headers["x-openai-api-key"] = apiKey;
  return headers;
}

export async function apiGet(path) {
  const resp = await fetch(path, { headers: buildHeaders() });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.detail || `Request failed: ${resp.status}`);
  return payload;
}

export async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: buildHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.detail || `Request failed: ${resp.status}`);
  return payload;
}

export async function apiPostForm(path, formData) {
  const resp = await fetch(path, { method: "POST", headers: buildHeaders(), body: formData });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.detail || `Request failed: ${resp.status}`);
  return payload;
}
