import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cancelAction, confirmAction, createHunt, deleteHunt, getHunt, listHunts, parseHunt, runHunt, updateHunt } from "../api";
import { useAuth } from "../auth/AuthContext";
import NavAuth from "../auth/NavAuth";
import { PendingActionCard } from "../components/AIAssistant";
import { splitCitations } from "../lib/sse";
import "./Scout.css";

const UNIVERSITIES = ["", "BRAC University", "North South University", "Dhaka University", "BUET", "IUB", "AIUB",
  "East West University", "Jahangirnagar University"];
const EXAMPLE = "Two of us (female) want a 2-bed near BRAC under 25k from January for 6 months. Quiet street, " +
  "line gas preferred. We'd like to know if guests are allowed.";

function Cited({ text }) {
  return splitCitations(text).map((p, i) => p.type === "text" ? <span key={i}>{p.value}</span> : (
    <span key={i} className="sc-refs">
      {p.refs.map((r) => r.kind === "listing"
        ? <Link key={`${r.kind}${r.id}`} to={`/property/${r.id}`} className="sc-ref">#{r.id}</Link>
        : <span key={`${r.kind}${r.id}`} className="sc-ref muted">{r.kind} {r.id}</span>)}
    </span>
  ));
}

function NewHunt({ onCreated }) {
  const [brief, setBrief] = useState("");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function read() {
    setBusy(true); setError(null);
    try {
      const d = await parseHunt(brief);
      setDraft({ ...d, preferences: d.preferences.join(", "), questions: d.questions.join("\n"), move_in: d.move_in || "" });
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const setC = (k, v) => setDraft((d) => ({ ...d, criteria: { ...d.criteria, [k]: v === "" ? undefined : v } }));

  async function save(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const criteria = Object.fromEntries(Object.entries(draft.criteria).filter(([, v]) => v !== undefined && v !== null && v !== ""));
      const hunt = await createHunt({
        title: draft.title, brief, criteria, stay_months: Number(draft.stay_months) || 6,
        move_in: draft.move_in || null,
        preferences: draft.preferences.split(",").map((s) => s.trim()).filter(Boolean),
        questions: draft.questions.split("\n").map((s) => s.trim()).filter(Boolean),
      });
      setBrief(""); setDraft(null); onCreated(hunt);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="sc-new">
      <h2>Start a hunt</h2>
      <p className="sc-muted">Describe what you need. Scout checks new listings every day, reads safety reviews and the
        forum, and drafts questions to owners and a booking. Nothing is sent or booked until you approve it.</p>
      <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3} placeholder={EXAMPLE} />
      <div className="sc-row">
        <button className="sc-btn" disabled={busy || brief.trim().length < 10} onClick={read}>
          {busy && !draft ? "Reading…" : "Fill in from my description"}
        </button>
        {!brief && <button className="sc-link" onClick={() => setBrief(EXAMPLE)}>Use the example</button>}
      </div>
      {error && <p className="sc-error">{error}</p>}
      {draft && (
        <form className="sc-form" onSubmit={save}>
          <label>Title<input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} required minLength={3} /></label>
          <div className="sc-grid">
            <label>Max rent (৳)<input type="number" value={draft.criteria.max_price ?? ""} onChange={(e) => setC("max_price", e.target.value && Number(e.target.value))} /></label>
            <label>Bedrooms (min)<input type="number" min="0" value={draft.criteria.bedrooms ?? ""} onChange={(e) => setC("bedrooms", e.target.value && Number(e.target.value))} /></label>
            <label>University<select value={draft.criteria.nearby_university ?? ""} onChange={(e) => setC("nearby_university", e.target.value)}>
              {UNIVERSITIES.map((u) => <option key={u} value={u}>{u || "Any"}</option>)}</select></label>
            <label>Min safety (0–5)<input type="number" step="0.5" min="0" max="5" value={draft.criteria.min_safety_score ?? ""} onChange={(e) => setC("min_safety_score", e.target.value && Number(e.target.value))} /></label>
            <label>Move-in<input type="date" value={draft.move_in} onChange={(e) => setDraft({ ...draft, move_in: e.target.value })} /></label>
            <label>Months<input type="number" min="1" max="24" value={draft.stay_months} onChange={(e) => setDraft({ ...draft, stay_months: e.target.value })} /></label>
          </div>
          <label className="sc-check"><input type="checkbox" checked={!!draft.criteria.is_female_only} onChange={(e) => setC("is_female_only", e.target.checked || undefined)} /> Women-only listings</label>
          <label>Nice to have (comma-separated)<input value={draft.preferences} onChange={(e) => setDraft({ ...draft, preferences: e.target.value })} /></label>
          <label>Questions for owners (one per line)<textarea rows={3} value={draft.questions} onChange={(e) => setDraft({ ...draft, questions: e.target.value })} /></label>
          <button className="sc-btn primary" disabled={busy}>{busy ? "Saving…" : "Save hunt"}</button>
        </form>
      )}
    </section>
  );
}

function MessageDraft({ action, onDecided }) {
  const [busy, setBusy] = useState(false);
  const decide = async (fn) => { setBusy(true); try { onDecided(await fn(action.id)); } finally { setBusy(false); } };
  return (
    <div className={`sc-msg ${action.status}`}>
      <div className="sc-msg-head">Message to the owner of <Link to={`/property/${action.summary.property_id}`}>{action.summary.title}</Link></div>
      <pre>{action.summary.message}</pre>
      {action.status === "pending" ? (
        <div className="sc-row">
          <button className="sc-btn primary" disabled={busy} onClick={() => decide(confirmAction)}>Send</button>
          <button className="sc-btn" disabled={busy} onClick={() => decide(cancelAction)}>Discard</button>
        </div>
      ) : <div className="sc-status">{{ confirmed: "Sent", cancelled: "Discarded", expired: "Expired" }[action.status] || action.status}</div>}
    </div>
  );
}

function Run({ run, onChange }) {
  const r = run.report || {};
  return (
    <article className="sc-run">
      <header>
        <span>{new Date(run.started_at).toLocaleString("en-BD")} · {run.trigger === "manual" ? "run by you" : "daily run"}</span>
        <span className={`sc-badge ${run.status}`}>{run.status.replace("_", " ")}</span>
      </header>
      {run.error && <p className="sc-error">Scout hit an error: {run.error}</p>}
      {r.summary && <p>{r.summary}</p>}
      {r.shortlist?.map((a) => (
        <div key={a.property_id} className="sc-pick">
          <div className="sc-score">{a.score}</div>
          <div><Link to={`/property/${a.property_id}`}>Listing #{a.property_id}</Link> <Cited text={a.reasons} /></div>
        </div>
      ))}
      {r.skipped?.length > 0 && (
        <details><summary>{r.skipped.length} also checked</summary>
          {r.skipped.map((a) => <p key={a.property_id} className="sc-muted">#{a.property_id}: {a.available === false ? "booked for your dates. " : ""}<Cited text={a.reasons} /></p>)}
        </details>
      )}
      {run.actions?.map((a) => a.type === "send_message"
        ? <MessageDraft key={a.id} action={a} onDecided={onChange} />
        : <PendingActionCard key={a.id} action={{ ...a, status: a.status === "pending" ? undefined : a.status }} onChange={onChange} />)}
    </article>
  );
}

function HuntCard({ hunt, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const load = () => getHunt(hunt.id).then(setDetail);

  async function act(fn) {
    setBusy(true); setError(null);
    try { await fn(); await load(); onChanged(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <section className="sc-hunt">
      <header>
        <div>
          <h3>{hunt.title}</h3>
          <p className="sc-muted">{hunt.brief}</p>
          <p className="sc-meta">{hunt.status === "active" ? `Next run ${hunt.next_run_at ? new Date(hunt.next_run_at).toLocaleString("en-BD") : "soon"}` : "Paused"} · {hunt.seen} listings checked</p>
        </div>
        <div className="sc-actions">
          <button className="sc-btn primary" disabled={busy} onClick={() => act(() => runHunt(hunt.id))}>{busy ? "Scout is working…" : "Run now"}</button>
          <button className="sc-btn" disabled={busy} onClick={() => act(() => updateHunt(hunt.id, { status: hunt.status === "active" ? "paused" : "active" }))}>{hunt.status === "active" ? "Pause" : "Resume"}</button>
          <button className="sc-link" onClick={() => (detail ? setDetail(null) : load())}>{detail ? "Hide runs" : "Show runs"}</button>
        </div>
      </header>
      {error && <p className="sc-error">{error}</p>}
      {!detail && hunt.latest_run?.report?.summary && <p className="sc-latest">Latest: {hunt.latest_run.report.summary}</p>}
      {detail && (detail.runs.length ? detail.runs.map((r) => <Run key={r.id} run={r} onChange={load} />) : <p className="sc-muted">No runs yet. Scout runs daily, or click Run now.</p>)}
      {detail && <button className="sc-link danger" onClick={() => act(async () => { await deleteHunt(hunt.id); })}>Delete hunt</button>}
    </section>
  );
}

export default function Scout() {
  const { user, ready, openAuth } = useAuth();
  const [hunts, setHunts] = useState([]);
  const load = () => listHunts().then(setHunts).catch(() => setHunts([]));
  useEffect(() => { if (user) load(); }, [user]);

  return (
    <div className="sc-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
        <div className="browse-nav-right"><NavAuth /><Link to="/browse" className="back-link">Browse listings</Link></div>
      </nav>
      <main className="sc-main">
        <h1>Scout <span>your house-hunting agent</span></h1>
        {ready && !user ? (
          <div className="auth-gate">Log in to let Scout hunt for you.<br />
            <button onClick={() => openAuth({ reason: "Log in to start a hunt." })}>Log in</button></div>
        ) : (
          <>
            <NewHunt onCreated={load} />
            {hunts.map((h) => <HuntCard key={h.id} hunt={h} onChanged={load} />)}
          </>
        )}
      </main>
    </div>
  );
}
