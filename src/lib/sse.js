// Minimal Server-Sent Events parser for fetch() streams. EventSource can't POST or send auth headers.

export function createSSEParser(onEvent) {
  let buffer = "";
  return {
    push(chunk) {
      buffer += chunk.replace(/\r\n/g, "\n");
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        let type = "message";
        const data = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) type = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (!data.length) continue;
        let payload = data.join("\n");
        try { payload = JSON.parse(payload); } catch { /* plain text payload */ }
        onEvent(type, payload);
      }
    },
  };
}

export async function streamSSE(url, { body, headers = {}, signal, onEvent }) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...headers },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : `Request failed (${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSSEParser(onEvent);
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.push(decoder.decode() + "\n\n");
}

// Split assistant text into plain segments and citation groups: "[listing:3, post:9]".
const BRACKET = /\[([^[\]]{1,200})\]/g;
const REF = /\b(listing|post|comment|safety)\s*[:#]\s*(\d+)\b/gi;

export function splitCitations(text) {
  const parts = [];
  let last = 0;
  for (const m of (text || "").matchAll(BRACKET)) {
    const refs = [...m[1].matchAll(REF)].map((r) => ({ kind: r[1].toLowerCase(), id: Number(r[2]) }));
    if (!refs.length) continue;
    if (m.index > last) parts.push({ type: "text", value: text.slice(last, m.index) });
    parts.push({ type: "refs", refs });
    last = m.index + m[0].length;
  }
  if (last < (text || "").length) parts.push({ type: "text", value: text.slice(last) });
  return parts;
}
