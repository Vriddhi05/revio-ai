const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export async function apiRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Tenant-Slug", "revio-demo");
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE}/api/v1${path}`, { ...options, headers, cache: "no-store" });
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error || {};
    throw new Error(error.message || body?.detail?.message || `Request failed (${response.status}).`);
  }
  return body;
}

export function apiBaseUrl() {
  return API_BASE;
}
