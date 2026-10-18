import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { cancelAction, confirmAction, getComments, getForumPost, streamAgent } from "../api";
import { useAuth } from "../auth/AuthContext";
import { splitCitations } from "../lib/sse";
import "./AIAssistant.css";

const SUGGESTIONS = [
  "2-bed near BRAC under 25k, women-only, safe area, from January",
  "Quiet room for BUET students with generator backup",
  "Does Merul Badda flood in the monsoon?",
  "বসুন্ধরায় রাতে মেয়েদের জন্য নিরাপদ বাসা আছে?",
];

const WELCOME = {
  role: "assistant",
  content:
    "Hi! Tell me what you need (budget, university, women-only, safety, move-in month) and I'll search listings, " +
    "safety reviews and the community forum for you. Every recommendation links to its evidence.",
  final: true,
};

const STEP_ICON = { running: "◌", done: "✓", error: "!" };

function Steps({ steps, live }) {
  if (!steps?.length) return null;
  return (
    <ul className={`ai-steps${live ? " live" : ""}`} aria-label="What the assistant did">
      {steps.map((s) => (
        <li key={s.id} className={`ai-step ${s.status}`} title={s.error || ""}>
          <span className="ai-step-icon">{STEP_ICON[s.status] || "◌"}</span>
          {s.label}
          {s.status === "error" && <span className="ai-step-err"> (failed)</span>}
        </li>
      ))}
    </ul>
  );
}

function Inline({ text }) {
  // **bold** only; everything else stays plain text (never injected as HTML).
  return text.split(/(\*\*[^*]+\*\*)/g).map((t, i) =>
    t.startsWith("**") && t.endsWith("**") ? <strong key={i}>{t.slice(2, -2)}</strong> : <span key={i}>{t}</span>,
  );
}

function RefChip({ r, onOpen }) {
  if (r.kind === "listing") {
    return <Link className="ai-ref listing" to={`/property/${r.id}`}>#{r.id}</Link>;
  }
  const label = { post: "post", comment: "comment", safety: "review" }[r.kind];
  return (
    <button type="button" className={`ai-ref ${r.kind}`} onClick={() => onOpen(r)}>
      {label} {r.id}
    </button>
  );
}

function RichText({ text, onOpen }) {
  const lines = (text || "").split("\n");
  return (
    <div className="ai-rich">
      {lines.map((line, li) => {
        const bullet = /^\s*([-*•]|\d+\.)\s+/.test(line);
        const body = bullet ? line.replace(/^\s*([-*•]|\d+\.)\s+/, "") : line;
        const content = splitCitations(body).map((p, i) =>
          p.type === "text"
            ? <Inline key={i} text={p.value} />
            : <span key={i} className="ai-refs">{p.refs.map((r) => <RefChip key={`${r.kind}${r.id}`} r={r} onOpen={onOpen} />)}</span>,
        );
        if (!line.trim()) return <div key={li} className="ai-gap" />;
        return bullet ? <div key={li} className="ai-bullet">• {content}</div> : <p key={li}>{content}</p>;
      })}
    </div>
  );
}

function ListingCards({ cards }) {
  if (!cards?.length) return null;
  return (
    <div className="ai-cards">
      {cards.map((c) => (
        <Link key={c.id} to={c.url} className="ai-card">
          <div className="ai-card-title">{c.title}</div>
          <div className="ai-card-price">
            ৳{Number(c.price).toLocaleString()}
            <span>/{c.rental_type === "daily" ? "day" : "mo"}</span>
          </div>
          <div className="ai-card-meta">
            {c.area}
            {c.nearby_university && ` · ${c.university_distance_km} km to ${c.nearby_university}`}
          </div>
          {c.warnings?.map((w) => <div key={w} className="ai-card-warn">⚠ {w}</div>)}
          <div className="ai-card-tags">
            {c.is_female_only && <span>Women-only</span>}
            {c.safety_score != null && <span>Safety {Number(c.safety_score).toFixed(1)}</span>}
            <span>{c.bedrooms > 0 && c.property_type !== "room" ? `${c.bedrooms} bed` : c.property_type}</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

export function PendingActionCard({ action, onChange }) {
  const { user, openAuth } = useAuth();
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const s = action.summary;

  async function decide(kind) {
    setBusy(true);
    setError(null);
    try {
      const res = kind === "confirm"
        ? await confirmAction(action.id, phone ? { renter_phone: phone } : {})
        : await cancelAction(action.id);
      onChange({ ...action, status: res.status, booking: res.booking });
    } catch (e) {
      setError(e.message);
      if (e.status === 409) onChange({ ...action, status: "failed", error: e.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`ai-action ${action.status || "pending"}`}>
      <div className="ai-action-head">Booking draft · needs your confirmation</div>
      <div className="ai-action-title">{s.title}</div>
      <div className="ai-action-rows">
        <span>Dates</span><span>{s.check_in} → {s.check_out}</span>
        <span>Price</span><span>৳{Number(s.unit_price).toLocaleString()} {s.rental_type}</span>
        <span>Total</span><strong>৳{Number(s.total_price).toLocaleString()}</strong>
      </div>
      {(!action.status || action.status === "pending") && (
        <>
          {user && !user.phone && (
            <input className="ai-action-phone" value={phone} onChange={(e) => setPhone(e.target.value)}
                   placeholder="Your phone (01XXXXXXXXX)" />
          )}
          {error && <div className="ai-action-error">{error}</div>}
          {user ? (
            <div className="ai-action-buttons">
              <button className="confirm" disabled={busy || (!user.phone && phone.length < 11)} onClick={() => decide("confirm")}>
                {busy ? "Working…" : "Confirm booking"}
              </button>
              <button className="cancel" disabled={busy} onClick={() => decide("cancel")}>Cancel</button>
            </div>
          ) : (
            <button className="confirm" onClick={() => openAuth({ reason: "Log in to confirm this booking." })}>Log in to confirm</button>
          )}
          <div className="ai-action-note">Nothing is booked until you click Confirm.</div>
        </>
      )}
      {action.status === "confirmed" && (
        <div className="ai-action-result ok">Booked: request #{action.booking?.id} sent to the owner.</div>
      )}
      {action.status === "cancelled" && <div className="ai-action-result">Cancelled. Nothing was booked.</div>}
      {action.status === "failed" && <div className="ai-action-result err">{action.error || "Could not book these dates."}</div>}
      {action.status === "expired" && <div className="ai-action-result">This draft expired. Ask me again to re-check.</div>}
    </div>
  );
}

function SourceDrawer({ source, onClose }) {
  const [post, setPost] = useState(null);
  const [comments, setComments] = useState([]);
  const postId = source.kind === "post" ? source.id : source.info?.post_id;

  useEffect(() => {
    if (!postId) return;
    getForumPost(postId).then(setPost).catch(() => setPost(false));
    getComments(postId).then(setComments).catch(() => {});
  }, [postId]);

  return (
    <div className="ai-drawer" role="dialog" aria-label="Cited source">
      <div className="ai-drawer-head">
        <span>{{ post: "Forum post", comment: "Forum comment", safety: "Safety review" }[source.kind]} #{source.id}</span>
        <button onClick={onClose} aria-label="Close source">✕</button>
      </div>
      <div className="ai-drawer-body">
        <p className="ai-drawer-warn">Community content, written by users and not verified by bari.</p>
        {source.kind === "safety" && (
          <>
            <blockquote>{source.info?.snippet || "Review text unavailable."}</blockquote>
            {source.info?.property_id && <Link to={`/property/${source.info.property_id}`}>Open the listing →</Link>}
          </>
        )}
        {postId && post === null && <p>Loading…</p>}
        {post && (
          <>
            <h4>{post.title}</h4>
            <p className="ai-drawer-meta">{post.area} · by {post.author_name}</p>
            <p className="ai-drawer-text">{post.body}</p>
            {comments.length > 0 && <h5>Comments</h5>}
            {comments.map((c) => (
              <div key={c.id} className={`ai-drawer-comment${source.kind === "comment" && c.id === source.id ? " hl" : ""}`}>
                <strong>{c.author_name}</strong> {c.content}
              </div>
            ))}
            <Link to={`/forum?post=${post.id}`}>Open in forum →</Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function AIAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([WELCOME]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState("");
  const [source, setSource] = useState(null);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const patchLast = (fn) => setMessages((prev) => [...prev.slice(0, -1), fn(prev[prev.length - 1])]);

  async function send(text) {
    const history = [...messages.filter((m) => m !== WELCOME && m.final), { role: "user", content: text }]
      .map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, { role: "user", content: text, final: true },
      { role: "assistant", content: "", steps: [], streaming: true }]);
    setInput("");
    setBusy(true);
    abortRef.current = new AbortController();

    try {
      await streamAgent(history, {
        provider,
        signal: abortRef.current.signal,
        onEvent: (type, data) => {
          if (type === "token") patchLast((m) => ({ ...m, content: m.content + data.text }));
          else if (type === "step") {
            patchLast((m) => {
              const steps = m.steps.filter((s) => s.id !== data.id);
              return { ...m, steps: [...steps, data] };
            });
          } else if (type === "listing_cards") patchLast((m) => ({ ...m, cards: data.cards }));
          else if (type === "citations") patchLast((m) => ({ ...m, sources: data.items }));
          else if (type === "pending_action") patchLast((m) => ({ ...m, actions: [...(m.actions || []), data] }));
          else if (type === "error") patchLast((m) => ({ ...m, error: data.message }));
          else if (type === "done") {
            // The final text is citation-checked and PII-scrubbed on the server: it replaces the raw stream.
            patchLast((m) => ({ ...m, content: data.text || m.content, streaming: false, final: !!data.text, meta: data }));
          }
        },
      });
    } catch (e) {
      if (e.name !== "AbortError") patchLast((m) => ({ ...m, error: `Couldn't reach the assistant (${e.message}).` }));
    } finally {
      patchLast((m) => ({ ...m, streaming: false }));
      setBusy(false);
    }
  }

  function openSource(r) {
    const all = messages.flatMap((m) => m.sources || []);
    const info = all.find((s) => s.ref === `${r.kind}:${r.id}`);
    setSource({ ...r, info });
  }

  function updateAction(updated) {
    setMessages((prev) => prev.map((m) => (m.actions?.some((a) => a.id === updated.id)
      ? { ...m, actions: m.actions.map((a) => (a.id === updated.id ? updated : a)) }
      : m)));
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (input.trim() && !busy) send(input.trim());
  }

  return (
    <>
      <button className={`ai-fab${open ? " open" : ""}`} onClick={() => setOpen((p) => !p)} title="AI housing assistant" aria-label="AI housing assistant">
        {open ? "✕" : "✦"}
      </button>

      {open && (
        <div className="ai-panel">
          <div className="ai-header">
            <span className="ai-header-icon">✦</span>
            <div>
              <div className="ai-header-title">bari assistant</div>
              <div className="ai-header-sub">Searches listings, safety reviews &amp; the forum</div>
            </div>
            <select className="ai-provider" value={provider} onChange={(e) => setProvider(e.target.value)}
                    title="Which model answers" disabled={busy}>
              <option value="">Default model</option>
              <option value="api">API (Groq)</option>
              <option value="ollama">Local (Ollama)</option>
            </select>
            <button className="ai-close" onClick={() => setOpen(false)} aria-label="Close">✕</button>
          </div>

          <div className="ai-messages">
            {messages.map((m, i) => (
              <div key={i} className={`ai-msg ${m.role}`}>
                {m.role === "assistant" && <span className="ai-msg-icon">✦</span>}
                <div className="ai-msg-col">
                  {m.role === "assistant" && <Steps steps={m.steps} live={m.streaming} />}
                  {(m.content || m.role === "user") && (
                    <div className="ai-msg-bubble">
                      {m.role === "assistant" ? <RichText text={m.content} onOpen={openSource} /> : m.content}
                    </div>
                  )}
                  {m.streaming && !m.content && !m.steps?.some((s) => s.status === "running") && (
                    <div className="ai-msg-bubble ai-typing"><span /><span /><span /></div>
                  )}
                  {m.error && <div className="ai-msg-error">{m.error}</div>}
                  <ListingCards cards={m.cards} />
                  {m.actions?.map((a) => <PendingActionCard key={a.id} action={a} onChange={updateAction} />)}
                  {m.meta?.unsupported_citations?.length > 0 && (
                    <div className="ai-msg-note">Removed {m.meta.unsupported_citations.length} unverifiable citation(s).</div>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          {messages.length === 1 && (
            <div className="ai-suggestions">
              {SUGGESTIONS.map((s) => <button key={s} className="ai-suggestion" onClick={() => send(s)}>{s}</button>)}
            </div>
          )}

          <form className="ai-input-row" onSubmit={handleSubmit}>
            <input value={input} onChange={(e) => setInput(e.target.value)} disabled={busy}
                   placeholder="Ask in English or বাংলা…" />
            {busy
              ? <button type="button" onClick={() => abortRef.current?.abort()} title="Stop">■</button>
              : <button type="submit" disabled={!input.trim()}>→</button>}
          </form>

          {source && <SourceDrawer source={source} onClose={() => setSource(null)} />}
        </div>
      )}
    </>
  );
}
