import { useState, useEffect, useRef } from "react";
import { getChatMessages, sendChatMessage, API_ROOT } from "../api";
import { useAuth } from "../auth/AuthContext";
import "./ChatWidget.css";

function getOrCreateSession(propertyId, user) {
  // Logged-in students have one thread per listing tied to their account, so messages Scout sent for them
  // (after their approval) show up here too.
  if (user) return `user-${user.id}`;
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
  const { user } = useAuth();
  const sessionToken = getOrCreateSession(propertyId, user);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [name, setName] = useState(sessionStorage.getItem("bari_chat_name") || "");
  const [nameSet, setNameSet] = useState(!!sessionStorage.getItem("bari_chat_name"));
  const [ws, setWs] = useState(null);
  const [connected, setConnected] = useState(false);
  // Serverless hosts (Vercel) can't hold WebSockets: if the socket never opens, poll over REST instead.
  const [polling, setPolling] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    getChatMessages(propertyId, sessionToken).then(setMessages).catch(() => {});
  }, [open, propertyId, sessionToken]);

  useEffect(() => {
    if (!open || !nameSet) return;

    const wsRoot = (API_ROOT || window.location.origin).replace(/^http/, "ws");
    const socket = new WebSocket(`${wsRoot}/api/chat/ws/${propertyId}/${sessionToken}`);
    let opened = false;
    socket.onopen = () => { opened = true; setConnected(true); };
    socket.onclose = () => { setConnected(false); if (!opened) setPolling(true); };
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
    if (!open || !polling) return;
    const refresh = () => getChatMessages(propertyId, sessionToken).then(setMessages).catch(() => {});
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [open, polling, propertyId, sessionToken]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function saveName(e) {
    e.preventDefault();
    if (!name.trim()) return;
    sessionStorage.setItem("bari_chat_name", name.trim());
    setNameSet(true);
  }

  async function sendMessage(e) {
    e.preventDefault();
    const content = input.trim();
    if (!content) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ sender: "renter", sender_name: name, content }));
    } else if (polling) {
      const msg = await sendChatMessage({ property_id: propertyId, session_token: sessionToken,
                                          sender: "renter", sender_name: name, content }).catch(() => null);
      if (msg) setMessages((prev) => [...prev, msg]);
    } else {
      return;
    }
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
            <span className={`cw-dot${connected || polling ? " online" : ""}`} />
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
                  disabled={!(connected || polling)}
                />
                <button type="submit" disabled={!(connected || polling) || !input.trim()}>Send</button>
              </form>
              {!connected && !polling && <p className="cw-offline">Connecting…</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
