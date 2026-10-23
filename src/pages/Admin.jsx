import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { adminDecisions, adminLLMUsage, adminQueue, downloadPrivateDocument, reviewContent, reviewListing } from "../api";
import { useAuth } from "../auth/AuthContext";
import NavAuth from "../auth/NavAuth";
import "./Admin.css";
import AdminCases from "../components/AdminCases";
import { AdminWomenSafety } from "../components/WomenSafetyPanel";

const TABS = [["queue", "Review queue"], ["women-safety", "Women-only safety"], ["cases", "Investigations"], ["decisions", "Decision log"], ["usage", "LLM usage"]];

function Labels({ labels }) {
  return <span className="adm-labels">{(labels || []).map((l) => <span key={l} className={`adm-label ${l}`}>{l.replace("_", " ")}</span>)}</span>;
}

function Queue() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  const load = () => adminQueue().then(setData).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function act(key, fn) {
    setBusy(key);
    try { await fn(); await load(); } catch (e) { setError(e.message); } finally { setBusy(null); }
  }

  if (error) return <p className="adm-error">{error}</p>;
  if (!data) return <p className="adm-muted">Loading…</p>;
  const empty = !data.listings.length && !data.content.length;

  return (
    <div className="adm-queue">
      {empty && <p className="adm-muted">Nothing waiting for review. 🎉</p>}
      {data.listings.length > 0 && <h3>Held listings ({data.listings.length})</h3>}
      {data.listings.map((l) => (
        <article key={`l${l.id}`} className="adm-item">
          <header>
            <Link to={`/property/${l.id}`} target="_blank">#{l.id} {l.title}</Link>
            <Labels labels={l.decision?.labels} />
          </header>
          <p className="adm-meta">৳{Number(l.price).toLocaleString()} · {l.area} · by {l.owner_name}</p>
          <p className="adm-reason"><strong>Why:</strong> {l.reason}</p>
          {l.verification && <section>
            <h4>Document checks: {l.verification.status.replaceAll("_", " ")}</h4>
            <ul>{l.verification.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
            {l.verification.documents.map(doc => <button key={doc.id} disabled={busy}
              onClick={() => act(`doc${doc.id}`, () => downloadPrivateDocument(doc.url, doc.name))}>
              Download {doc.name}
            </button>)}
          </section>}
          <details><summary>Description</summary><p className="adm-text">{l.description}</p></details>
          {l.decision?.signals && <details><summary>Signals</summary><pre>{JSON.stringify(l.decision.signals, null, 2)}</pre></details>}
          <div className="adm-actions">
            <button className="approve" disabled={busy} onClick={() => act(`l${l.id}`, () => reviewListing(l.id, "approve"))}>{l.is_female_only ? "Approve documents & moderation" : "Approve & publish"}</button>
            <button className="reject" disabled={busy} onClick={() => act(`l${l.id}`, () => reviewListing(l.id, "reject"))}>Reject</button>
          </div>
        </article>
      ))}
      {data.content.length > 0 && <h3>Held community content ({data.content.length})</h3>}
      {data.content.map((c) => (
        <article key={`${c.kind}${c.id}`} className="adm-item">
          <header>
            <span>{c.kind} #{c.id}: {c.title}</span>
            <Labels labels={c.decision?.labels} />
          </header>
          <p className="adm-meta">by {c.author}</p>
          <p className="adm-text">{c.text}</p>
          <p className="adm-reason"><strong>Why:</strong> {c.reason}</p>
          <div className="adm-actions">
            <button className="approve" disabled={busy} onClick={() => act(`${c.kind}${c.id}`, () => reviewContent(c.kind, c.id, "approve"))}>Approve</button>
            <button className="reject" disabled={busy} onClick={() => act(`${c.kind}${c.id}`, () => reviewContent(c.kind, c.id, "remove"))}>Remove</button>
          </div>
        </article>
      ))}
    </div>
  );
}

function Decisions() {
  const [rows, setRows] = useState(null);
  useEffect(() => { adminDecisions().then(setRows).catch(() => setRows([])); }, []);
  if (!rows) return <p className="adm-muted">Loading…</p>;
  return (
    <div className="adm-table-wrap">
      <table className="adm-table">
        <thead><tr><th>When</th><th>Target</th><th>Workflow</th><th>Decision</th><th>Labels</th><th>Reasons</th><th>Review</th></tr></thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id}>
              <td>{d.created_at && new Date(d.created_at).toLocaleString("en-BD")}</td>
              <td>{d.target}</td><td>{d.workflow}</td>
              <td className={d.decision}>{d.decision}</td>
              <td><Labels labels={d.labels} /></td>
              <td className="adm-reasons">{d.reasons.join("; ")}</td>
              <td>{d.review_status || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Usage() {
  const [data, setData] = useState(null);
  useEffect(() => { adminLLMUsage().then(setData).catch(() => setData({ by_model: [], recent_agent_runs: [] })); }, []);
  if (!data) return <p className="adm-muted">Loading…</p>;
  const total = data.by_model.reduce((a, r) => ({ calls: a.calls + r.calls, cost: a.cost + r.cost_usd }), { calls: 0, cost: 0 });
  return (
    <>
      <p className="adm-muted">{total.calls} LLM calls · est. ${total.cost.toFixed(4)} at paid-tier prices</p>
      <div className="adm-table-wrap">
        <table className="adm-table">
          <thead><tr><th>Provider</th><th>Model</th><th>Purpose</th><th>Calls</th><th>Prompt tok</th><th>Completion tok</th><th>Avg latency</th><th>Errors</th><th>Est. cost</th></tr></thead>
          <tbody>
            {data.by_model.map((r, i) => (
              <tr key={i}><td>{r.provider}</td><td>{r.model}</td><td>{r.purpose}</td><td>{r.calls}</td>
                <td>{r.prompt_tokens.toLocaleString()}</td><td>{r.completion_tokens.toLocaleString()}</td>
                <td>{(r.avg_latency_ms / 1000).toFixed(1)} s</td><td>{r.errors}</td><td>${r.cost_usd.toFixed(4)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Recent assistant runs</h3>
      <div className="adm-table-wrap">
        <table className="adm-table">
          <thead><tr><th>Question</th><th>Model</th><th>Tools</th><th>Citations</th><th>Status</th><th>Latency</th></tr></thead>
          <tbody>
            {data.recent_agent_runs.map((r) => (
              <tr key={r.id}><td className="adm-reasons">{r.question}</td><td>{r.model}</td><td>{r.tools.join(", ")}</td>
                <td>{r.citations.length}{r.unsupported.length ? ` (+${r.unsupported.length} dropped)` : ""}</td>
                <td className={r.status}>{r.status}</td><td>{(r.latency_ms / 1000).toFixed(1)} s</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function Admin() {
  const { user, ready, openAuth } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([key]) => key === params.get("tab")) ? params.get("tab") : "queue";

  return (
    <div className="adm-layout">
      <nav className="browse-nav">
        <Link to="/" className="nav-logo">bari<span>.com</span></Link>
        <div className="browse-nav-right"><NavAuth /></div>
      </nav>
      <main className="adm-main">
        <h1>Moderation</h1>
        {!ready ? <p role="status">Loading your account…</p> : user?.role !== "admin" ? (
          <div className="auth-gate">
            This page is for bari admins.
            {!user && <><br /><button onClick={() => openAuth({ reason: "Log in with an admin account." })}>Log in</button></>}
          </div>
        ) : (
          <>
            <div className="adm-tabs" role="tablist">
              {TABS.map(([k, label]) => (
                <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setParams(k === "queue" ? {} : { tab: k })}>{label}</button>
              ))}
            </div>
            {tab === "queue" && <Queue />}
            {tab === "cases" && <AdminCases />}
            {tab === "women-safety" && <AdminWomenSafety />}
            {tab === "decisions" && <Decisions />}
            {tab === "usage" && <Usage />}
          </>
        )}
      </main>
    </div>
  );
}
