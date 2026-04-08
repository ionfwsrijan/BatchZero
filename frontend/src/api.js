const BASE = "/api";
const MAX_ERROR_CHARS = 300;

// FastAPI returns `{"detail": ...}` (a string for HTTPException, a list for
// validation errors), but proxies and cold starts can return HTML. Normalize
// both into one short line instead of dumping a whole page into the banner.
async function responseError(res) {
  let body = "";
  try {
    body = await res.text();
  } catch {
    // Body already consumed/unreadable: fall back to the status line below.
  }
  let detail = body;
  try {
    const parsed = JSON.parse(body);
    const value = parsed?.detail ?? parsed?.error ?? body;
    detail = Array.isArray(value)
      ? value.map((item) => item?.msg || JSON.stringify(item)).join("; ")
      : value;
  } catch {
    // Plain text or HTML: keep it, the caller truncates it.
  }
  const message = String(detail || res.statusText || "request failed").trim();
  return `${res.status} ${message.length > MAX_ERROR_CHARS ? `${message.slice(0, MAX_ERROR_CHARS)}…` : message}`;
}

export async function getJSON(path, params) {
  const url = new URL(BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(await responseError(res));
  return res.json();
}

export async function postJSON(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await responseError(res));
  return res.json();
}

// POST + Server-Sent-Events: fetch keeps the body, so we parse the SSE frames
// ourselves (EventSource can only issue GETs, which can't carry the request body).
export async function streamSSE(path, body, onEvent, signal) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body || {}),
    signal,
  });
  if (!res.ok) throw new Error(await responseError(res));
  if (!res.body) throw new Error(`${res.status} stream closed before any events arrived`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE allows LF *or* CRLF line endings; servers may emit either, and a frame
    // boundary of "\r\n\r\n" never matches a search for "\n\n". Normalise first
    // (raw CR cannot appear inside a JSON payload — it would be escaped).
    buffer = buffer.replace(/\r/g, "");

    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let eventName = "message";
      const dataLines = [];
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      try {
        onEvent({ type: eventName, ...JSON.parse(dataLines.join("\n")) });
      } catch {
        onEvent({ type: eventName, raw: dataLines.join("\n") });
      }
    }
  }
}
