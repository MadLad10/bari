import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Conversation from "./Conversation";
import "./Conversation.css";
import "./ChatWidget.css";

export default function ChatWidget({ property }) {
  const { user, openAuth } = useAuth();
  const [open, setOpen] = useState(false);
  const isOwner = user && user.id === property.owner_id;
  return <div className="cw-wrapper">
    <button className={`cw-toggle${open ? " active" : ""}`} onClick={() => setOpen(v => !v)}>
      {open ? "Close chat" : `Chat with ${property.owner_name.split(" ")[0]}`}
    </button>
    {open && <div className="cw-box">
      <div className="cw-header">Chat with {property.owner_name}</div>
      {!user ? <div className="cw-name-form"><p>Log in to start a private conversation with the owner.</p>
        <button onClick={() => openAuth({ reason: "Your conversations are private and tied to your account." })}>Log in to chat</button></div>
        : isOwner ? <div className="cw-name-form"><p>Reply to renters from your dashboard inbox.</p><Link to="/owner?tab=messages">Open inbox</Link></div>
        : <Conversation key={`${property.id}-${user.id}`} propertyId={property.id} sessionToken={`user-${user.id}`} />}
    </div>}
  </div>;
}
