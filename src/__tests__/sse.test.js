import { describe, expect, it } from "vitest";
import { createSSEParser, splitCitations } from "../lib/sse";

describe("createSSEParser", () => {
  it("parses events split across arbitrary chunk boundaries", () => {
    const events = [];
    const p = createSSEParser((type, data) => events.push([type, data]));
    const stream = 'event: step\ndata: {"tool":"search_properties","status":"running"}\n\n' +
      'event: token\ndata: {"text":"Hello "}\n\nevent: done\ndata: {"text":"Hello [listing:9]"}\n\n';
    for (let i = 0; i < stream.length; i += 7) p.push(stream.slice(i, i + 7));
    expect(events).toEqual([
      ["step", { tool: "search_properties", status: "running" }],
      ["token", { text: "Hello " }],
      ["done", { text: "Hello [listing:9]" }],
    ]);
  });

  it("handles CRLF, multi-line data and non-JSON payloads", () => {
    const events = [];
    const p = createSSEParser((type, data) => events.push([type, data]));
    p.push("event: note\r\ndata: line one\r\ndata: line two\r\n\r\n");
    expect(events).toEqual([["note", "line one\nline two"]]);
  });

  it("keeps Bangla text intact", () => {
    const events = [];
    const p = createSSEParser((type, data) => events.push(data));
    p.push('event: token\ndata: {"text":"ধানমন্ডি লেক"}\n\n');
    expect(events[0].text).toBe("ধানমন্ডি লেক");
  });
});

describe("splitCitations", () => {
  it("separates text and citation groups", () => {
    expect(splitCitations("Try this [listing:9, post:3]. Also [note].")).toEqual([
      { type: "text", value: "Try this " },
      { type: "refs", refs: [{ kind: "listing", id: 9 }, { kind: "post", id: 3 }] },
      { type: "text", value: ". Also [note]." },
    ]);
  });

  it("returns plain text untouched", () => {
    expect(splitCitations("No sources here")).toEqual([{ type: "text", value: "No sources here" }]);
  });
});
