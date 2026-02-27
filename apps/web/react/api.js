/* ── API helpers ─────────────────────────────────────────────────── */

export async function apiGet(path) {
  const resp = await fetch(path);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.detail || `Request failed: ${resp.status}`);
  return payload;
}

export async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.detail || `Request failed: ${resp.status}`);
  return payload;
}

export async function apiPostForm(path, formData) {
  const resp = await fetch(path, { method: "POST", body: formData });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(payload.detail || `Request failed: ${resp.status}`);
  return payload;
}
