const baseUrl = import.meta.env.DEV ? "/api" : "";
let csrfToken = "";

export function setCsrfToken(value) {
  csrfToken = value || "";
}

async function fetchResponse(path, options = {}) {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrfToken) headers.set("X-OpsFlow-CSRF", csrfToken);
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers,
      credentials: "same-origin",
      signal: AbortSignal.timeout(60000),
    });
  } catch {
    throw new Error(
      "Unable to reach OpsFlow. Check your connection and refresh before trying again.",
    );
  }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("opsflow:unauthorized"));
    const body = await response.json().catch(() => ({}));
    if (Array.isArray(body.detail)) {
      throw new Error(
        body.detail
          .map((issue) => `${issue.loc.slice(1).join(" · ")} — ${issue.msg}`)
          .join(". "),
      );
    }
    const error = new Error(
      body.detail || "The request could not be completed. Please try again.",
    );
    error.status = response.status;
    throw error;
  }
  return response;
}

export async function request(path, options = {}) {
  const response = await fetchResponse(path, options);
  return response.status === 204 ? null : response.json();
}

export async function downloadFile(path, filename) {
  const response = await fetchResponse(path);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function readAll(path) {
  const records = [];
  let page;
  do {
    page = await request(
      `${path}${path.includes("?") ? "&" : "?"}limit=100&offset=${records.length}`,
    );
    records.push(...page);
  } while (page.length === 100);
  return records;
}

export function today() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Dubai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

export function orderNumber(id) {
  return `ORD-${String(id).padStart(4, "0")}`;
}
