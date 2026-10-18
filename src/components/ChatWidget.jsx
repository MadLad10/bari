import { useState, useEffect, useRef } from "react";
import { getChatMessages, API_ROOT } from "../api";
import "./ChatWidget.css";

function getOrCreateSession(propertyId) {
  const key = `bari_chat_${propertyId}`;
  let token = sessionStorage.getItem(key);
  if (!token) {
    token = Math.random().toString(36).slice(2) + Date.now().toString(36);
    sessionStorage.setItem(key, token);
  }
  return token;
}

export default function ChatWidget({ property }) {
  const { id: propertyId, owner_name } = property;
  const sessionToken = getOrCreateSession(propertyId);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [name, setName] = useState(sessionStorage.getItem("bari_chat_name") || "");
  const [nameSet, setNameSet] = useState(!!sessionStorage.getItem("bari_chat_name"));
  const [ws, setWs] = useState(null);
  const [connected, setConnected] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    getChatMessages(propertyId, sessionToken).then(setMessages).catch(() => {});
  }, [open, propertyId, sessionToken]);

  useEffect(() => {
    if (!open || !nameSet) return;

    const socket = new WebSocket(
      `${API_ROOT.replace(/^http/, "ws")}/api/chat/ws/${propertyId}/${sessionToken}`
    );
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.error) return;
      setMessages((prev) => {
        const exists = prev.some((m) => m.id === msg.id);
        return exists ? prev : [...prev, msg];
      });
    };
    setWs(socket);
    return () => socket.close();
  }, [open, nameSet, propertyId, sessionToken]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function saveName(e) {
    e.preventDefault();
    if (!name.trim()) return;
    sessionStorage.setItem("bari_chat_name", name.trim());
    setNameSet(true);
  }

  function sendMessage(e) {
    e.preventDefault();
    if (!input.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      sender: "renter",
      sender_name: name,
      content: input.trim(),
    }));
    setInput("");
  }

  return (
    <div className="cw-wrapper">
      <button className={`cw-toggle${open ? " active" : ""}`} onClick={() => setOpen((p) => !p)}>
        {open ? "✕" : "💬"} {open ? "Close chat" : `Chat with ${owner_name.split(" ")[0]}`}
      </button>

      {open && (
        <div className="cw-box">
          <div className="cw-header">
            <span>Chat with {owner_name}</span>
            <span className={`cw-dot${connected ? " online" : ""}`} />
          </div>

          {!nameSet ? (
            <form className="cw-name-form" onSubmit={saveName}>
              <p>Enter your name to start chatting</p>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                required
                autoFocus
              />
              <button type="submit">Start Chat</button>
            </form>
          ) : (
            <>
              <div className="cw-messages">
                {messages.length === 0 && (
                  <div className="cw-empty">No messages yet. Say hello!</div>
                )}
                {messages.map((m) => (
                  <div key={m.id} className={`cw-msg${m.sender === "renter" ? " mine" : " theirs"}`}>
                    <div className="cw-msg-name">{m.sender_name}</div>
                    <div className="cw-msg-bubble">{m.content}</div>
                    <div className="cw-msg-time">
                      {new Date(m.created_at).toLocaleTimeString("en-BD", { hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>

              <form className="cw-input-row" onSubmit={sendMessage}>
                <input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type a message…"
                  disabled={!connected}
                />
                <button type="submit" disabled={!connected || !input.trim()}>Send</button>
              </form>
              {!connected && <p className="cw-offline">Reconnecting…</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
