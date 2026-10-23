import { useEffect, useId, useRef, useState } from "react";
import useConversation from "../lib/useConversation";
import "./Conversation.css";

export default function Conversation({ propertyId, sessionToken, owner = false }) {
  const { messages, error, sending, connected, send } = useConversation(propertyId, sessionToken);
  const [input, setInput] = useState("");
  const inputId = useId();
  const bottom = useRef(null);
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: "nearest" }); }, [messages.at(-1)?.id]);
  async function submit(e) {
    e.preventDefault();
    if (await send(input)) setInput("");
  }
  return <div className="conversation">
    <small className="conversation-connection">{connected ? "Live conversation" : "Checking for new messages every few seconds"}</small>
    <div className="conversation-messages" role="log" aria-label="Conversation messages" aria-live="polite">
      {!messages.length && <p className="conversation-empty">No messages yet. Start the conversation.</p>}
      {messages.map(m => <div key={m.id} className={`conversation-message ${m.sender === (owner ? "owner" : "renter") ? "mine" : "theirs"}`}>
        <strong>{m.sender_name}</strong><p>{m.content}</p>
        <time dateTime={m.created_at}>{new Date(m.created_at).toLocaleString("en-BD", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</time>
      </div>)}
      <div ref={bottom} />
    </div>
    {error && <p role="alert" className="conversation-error">{error}</p>}
    <form className="conversation-compose" onSubmit={submit}>
      <label className="sr-only" htmlFor={inputId}>Your message</label>
      <textarea id={inputId} value={input} onChange={e => setInput(e.target.value)} placeholder="Ask a question or send a reply…" rows={2} maxLength={5000} required />
      <button type="submit" disabled={sending || !input.trim()}>{sending ? "Sending…" : "Send message"}</button>
    </form>
  </div>;
}
