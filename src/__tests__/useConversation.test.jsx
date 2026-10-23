// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, renderHook } from "@testing-library/react";

vi.mock("../api", () => ({ API_ROOT: "http://localhost:8001", getToken: vi.fn(() => "test-access-token"), getChatMessages: vi.fn(), sendChatMessage: vi.fn() }));
import { getChatMessages, sendChatMessage } from "../api";
import useConversation from "../lib/useConversation";

class Socket {
  static instances = [];
  constructor(url) { this.url = url; this.send = vi.fn(); Socket.instances.push(this); }
  open() { this.onopen?.(); }
  receive(message) { this.onmessage?.({ data: JSON.stringify(message) }); }
  close(code = 1000) { this.onclose?.({ code }); }
}
const message = (id, overrides = {}) => ({ id, property_id: 5, session_token: "user-7", content: `Message ${id}`, ...overrides });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };

beforeEach(() => {
  vi.useFakeTimers(); vi.stubGlobal("WebSocket", Socket); Socket.instances = [];
  getChatMessages.mockResolvedValue([]);
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it("authenticates in a frame and ignores messages for other renters or properties", async () => {
  const { result } = renderHook(() => useConversation(5, "user-7"));
  await act(async () => {});
  const socket = Socket.instances[0];
  act(() => { socket.open(); socket.receive({ type: "ready" }); });
  expect(socket.url).toBe("ws://localhost:8001/api/chat/ws/5/user-7");
  expect(socket.url).not.toContain("test-access-token");
  expect(socket.send).toHaveBeenCalledWith(JSON.stringify({ token: "test-access-token" }));
  act(() => {
    socket.receive(message(1));
    socket.receive(message(2, { session_token: "user-8" }));
    socket.receive(message(3, { property_id: 6 }));
  });
  expect(result.current.connected).toBe(true);
  expect(result.current.messages.map(m => m.id)).toEqual([1]);
});

it("retains newer live messages when an older REST response arrives later", async () => {
  const oldRead = deferred(); getChatMessages.mockReturnValueOnce(oldRead.promise);
  const { result } = renderHook(() => useConversation(5, "user-7"));
  act(() => Socket.instances[0].receive(message(2)));
  await act(async () => oldRead.resolve([message(1)]));
  expect(result.current.messages.map(m => m.id)).toEqual([1, 2]);
});

it("uses REST fallback while disconnected and reconnects without polling a live socket", async () => {
  const { result } = renderHook(() => useConversation(5, "user-7"));
  await act(async () => {});
  act(() => Socket.instances[0].receive({ type: "ready" }));
  getChatMessages.mockClear();
  await act(async () => vi.advanceTimersByTimeAsync(8000));
  expect(getChatMessages).not.toHaveBeenCalled();
  await act(async () => Socket.instances[0].close(1006));
  expect(getChatMessages).toHaveBeenCalledWith(5, "user-7");
  expect(result.current.connected).toBe(false);
  await act(async () => vi.advanceTimersByTimeAsync(1000));
  expect(Socket.instances).toHaveLength(2);
  act(() => { Socket.instances[1].open(); Socket.instances[1].receive({ type: "ready" }); });
  expect(result.current.connected).toBe(true);
});

it("does not retry a socket rejected for authentication or authorization", async () => {
  const { result } = renderHook(() => useConversation(5, "user-7"));
  await act(async () => {});
  await act(async () => Socket.instances[0].close(1008));
  await act(async () => vi.advanceTimersByTimeAsync(20000));
  expect(Socket.instances).toHaveLength(1);
  expect(result.current.connected).toBe(false);
});

it("does not append a delayed send or old socket frame after switching conversations", async () => {
  const pendingSend = deferred(); sendChatMessage.mockReturnValueOnce(pendingSend.promise);
  const { result, rerender } = renderHook(({ thread }) => useConversation(5, thread), { initialProps: { thread: "user-7" } });
  await act(async () => {});
  let sent;
  act(() => { sent = result.current.send("Only for renter seven"); });
  const oldSocket = Socket.instances[0];
  rerender({ thread: "user-8" });
  await act(async () => {});
  await act(async () => { oldSocket.receive(message(2)); pendingSend.resolve(message(1)); await sent; });
  expect(await sent).toBe(false);
  expect(result.current.messages).toEqual([]);
  expect(result.current.sending).toBe(false);
});

it("prevents double sends and rejects a response with the wrong conversation", async () => {
  const pendingSend = deferred(); sendChatMessage.mockReturnValueOnce(pendingSend.promise);
  const { result } = renderHook(() => useConversation(5, "user-7"));
  await act(async () => {});
  let first, second;
  act(() => { first = result.current.send("Hello"); second = result.current.send("Hello again"); });
  expect(await second).toBe(false);
  expect(sendChatMessage).toHaveBeenCalledTimes(1);
  await act(async () => { pendingSend.resolve(message(1, { session_token: "user-8" })); await first; });
  expect(result.current.messages).toEqual([]);
  expect(result.current.error).toMatch(/did not match this conversation/);
});
