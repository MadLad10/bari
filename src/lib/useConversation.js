import { useCallback, useEffect, useRef, useState } from "react";
import { API_ROOT, getToken, getChatMessages, sendChatMessage } from "../api";

function belongsTo(msg, propertyId, sessionToken) {
  return msg && Number.isInteger(msg.id) && msg.property_id === Number(propertyId) && msg.session_token === sessionToken;
}

function mergeMessages(previous, incoming) {
  const byId = new Map(previous.map(msg => [msg.id, msg]));
  incoming.forEach(msg => byId.set(msg.id, msg));
  return [...byId.values()].sort((a, b) => a.id - b.id);
}

export default function useConversation(propertyId, sessionToken, enabled = true) {
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState(null);
  const [sending, setSending] = useState(false);
  const [connected, setConnected] = useState(false);
  const generation = useRef(0);
  const sendingRef = useRef(false);

  useEffect(() => {
    const version = ++generation.current;
    setMessages([]); setError(null); setConnected(false); setSending(false);
    sendingRef.current = false;
    if (!enabled || !propertyId || !sessionToken) return;
    let disposed = false;
    let live = false;
    let refreshing = false;
    let socket = null;
    let reconnectTimer = null;
    let retryDelay = 1000;
    const current = () => !disposed && generation.current === version;
    const append = rows => {
      if (current()) setMessages(prev => mergeMessages(prev, rows.filter(msg => belongsTo(msg, propertyId, sessionToken))));
    };
    const refresh = async () => {
      if (refreshing || !current()) return;
      refreshing = true;
      try {
        const rows = await getChatMessages(propertyId, sessionToken);
        if (current()) { append(rows); setError(null); }
      } catch (e) { if (current()) setError(e.message); }
      finally { refreshing = false; }
    };
    const root = (API_ROOT || window.location.origin).replace(/^http/, "ws");
    const connect = () => {
      if (!current()) return;
      socket = new WebSocket(`${root}/api/chat/ws/${propertyId}/${sessionToken}`);
      socket.onopen = () => { if (current()) socket.send(JSON.stringify({ token: getToken() })); };
      socket.onmessage = e => {
        if (!current()) return;
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }
        if (msg?.type === "ready") {
          live = true; retryDelay = 1000; setConnected(true); return;
        }
        if (msg?.error) { setError(msg.error); return; }
        append([msg]);
      };
      socket.onclose = event => {
        if (!current()) return;
        live = false; setConnected(false);
        refresh();
        if (event.code !== 1008) {
          reconnectTimer = setTimeout(connect, retryDelay);
          retryDelay = Math.min(retryDelay * 2, 15000);
        }
      };
    };
    refresh();
    connect();
    // Poll when the socket is unavailable, and recover missed messages after reconnect.
    const timer = setInterval(() => { if (!live) refresh(); }, 4000);
    return () => {
      disposed = true;
      clearInterval(timer); clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [propertyId, sessionToken, enabled]);

  const send = useCallback(async content => {
    if (!enabled || !content.trim() || sendingRef.current) return false;
    const version = generation.current;
    sendingRef.current = true;
    setSending(true); setError(null);
    try {
      const msg = await sendChatMessage({ property_id: propertyId, session_token: sessionToken, content: content.trim() });
      if (generation.current !== version) return false;
      if (!belongsTo(msg, propertyId, sessionToken)) throw new Error("The reply did not match this conversation. Please refresh.");
      setMessages(prev => mergeMessages(prev, [msg]));
      return true;
    } catch (e) { if (generation.current === version) setError(e.message); return false; }
    finally {
      if (generation.current === version) { sendingRef.current = false; setSending(false); }
    }
  }, [propertyId, sessionToken, enabled]);
  return { messages, error, sending, connected, send };
}
