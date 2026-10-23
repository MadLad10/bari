import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { addCaseNote, claimCase, decideCase, fetchAdminCases, fetchCase } from "../api";
import { useAuth } from "../auth/AuthContext";
import useBookingResource from "../lib/useBookingResource";
import { CASE_CATEGORIES, CASE_STATUSES, caseClosed, caseTime } from "../lib/cases";
import CaseTimeline from "./CaseTimeline";
import "../pages/MyBookings.css";
import "../pages/Reports.css";

function CaseInvestigation({ id, onChanged }) {
  const { user } = useAuth();
  const fetcher = useCallback(() => fetchCase(id), [id]);
  const { data, error, loading, refresh } = useBookingResource(fetcher, user.id);
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const [hold, setHold] = useState(false);
  const [note, setNote] = useState("");
  const [internal, setInternal] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  useEffect(() => {
    const allowed = data?.allowed_statuses || [];
    setStatus(allowed.includes("investigating") ? "investigating" : allowed.includes("awaiting_reporter") ? "awaiting_reporter" : allowed[0] || "");
  }, [data?.status]);
  async function act(fn, clear) {
    setBusy(true); setActionError(null);
    try { await fn(); clear?.(); await refresh(); await onChanged(); }
    catch (e) { setActionError(e.message); if (e.status === 409) await refresh(); }
    finally { setBusy(false); }
  }
  if (loading) return <div className="case-panel" role="status">Loading investigation…</div>;
  if (!data) return <div role="alert" className="mb-error">{error?.message || "Case unavailable"}<button onClick={refresh}>Refresh</button></div>;
  return <section className="case-panel">
    <div className="case-heading"><div><span className="mb-eyebrow">CASE #{data.id} · {CASE_CATEGORIES[data.category]}</span><h2>{data.title}</h2></div><span className={`case-badge ${data.status}`}>{data.status === "awaiting_reporter" ? "Awaiting reporter" : CASE_STATUSES[data.status]}</span></div>
    <p className="case-help">Reported by {data.reporter_name}{!data.reporter_id && " (legacy public report; no linked account)"} · {caseTime(data.created_at)}</p><p className="case-body">{data.description}</p>
    <div className="case-actions">{data.property_id && <Link className="mb-text-link" to={`/property/${data.property_id}`}>Listing #{data.property_id}: {data.property_title} ↗</Link>}{data.booking_id && <Link className="mb-text-link" to={`/bookings/${data.booking_id}`}>Booking #{data.booking_reference} ↗</Link>}{data.forum_post_id && <Link className="mb-text-link" to={`/forum?post=${data.forum_post_id}`}>Source forum report ↗</Link>}</div>
    <div className="case-heading"><p className="case-help">Assigned to: {data.assigned_name || "Unassigned"}</p>{!caseClosed(data) && data.assigned_to !== user.id && <button className="mb-button secondary" disabled={busy} onClick={() => act(() => claimCase(id, data.version))}>Assign to me</button>}</div>
    {(error || actionError) && <p className="mb-error" role="alert">{actionError || error.message}</p>}
    {data.resolution && <div className="case-resolution"><h3>Resolution shared with reporter</h3><p>{data.resolution}</p></div>}
    <form className="case-form case-decision-form" onSubmit={e => { e.preventDefault(); act(() => decideCase(id, { expected_version: data.version, status, message, hold_listing: hold }), () => { setMessage(""); setHold(false); }); }}>
      <h3>{caseClosed(data) ? "Reopen investigation" : "Investigation decision"}</h3>
      <label>New case status<select value={status} onChange={e => setStatus(e.target.value)} required>{data.allowed_statuses.map(s => <option key={s} value={s}>{s === "awaiting_reporter" ? "Request more information" : CASE_STATUSES[s]}</option>)}</select></label>
      <label>{["resolved", "dismissed"].includes(status) ? "Resolution for reporter" : "Update for reporter"}<textarea value={message} onChange={e => setMessage(e.target.value)} required minLength={["resolved", "dismissed"].includes(status) ? 10 : 5} maxLength={10000} rows={4} placeholder="Explain the action, next step or outcome. The reporter can read this." /></label>
      {data.property_id && <label className="case-check"><input type="checkbox" checked={hold} onChange={e => setHold(e.target.checked)} />Hold linked listing for admin review</label>}
      <p className="case-help">Holding a listing hides it from public browsing. Resolve open cases, then use the review queue to approve publication; document checks still apply.</p>
      <button className="mb-button" disabled={busy}>{busy ? "Saving…" : "Save decision & share update"}</button>
    </form>
    {!caseClosed(data) && <form className="case-form" onSubmit={e => { e.preventDefault(); act(() => addCaseNote(id, note, internal), () => setNote("")); }}>
      <h3>Investigation notes & messages</h3><label>Note or message<textarea value={note} onChange={e => setNote(e.target.value)} required minLength={2} maxLength={10000} rows={3} /></label>
      <label className="case-check"><input type="checkbox" checked={internal} onChange={e => setInternal(e.target.checked)} />Admin-only investigation note</label>
      <p className="case-help">{internal ? "This note is visible only to admins." : "This message will appear in the reporter’s case updates."}</p>
      <button className="mb-button secondary" disabled={busy}>{busy ? "Saving…" : internal ? "Add private note" : "Send update to reporter"}</button>
    </form>}
    <div className="case-heading"><h3>Full case timeline</h3><button className="mb-refresh" disabled={busy} onClick={refresh}>↻ Refresh</button></div><CaseTimeline updates={data.updates} />
  </section>;
}

export default function AdminCases() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const [skip, setSkip] = useState(0);
  const fetcher = useCallback(() => fetchAdminCases({ status, category, q, skip, limit: 20 }), [status, category, q, skip]);
  const { data, loading, error, refreshing, refresh } = useBookingResource(fetcher, user.id);
  const rows = data || [];
  const selected = Number(params.get("case")) || rows[0]?.id;
  return <div className="case-admin">
    <div className="case-private-banner">Reports have their own investigation workflow. Private notes stay with admins; reporter-facing updates and outcomes appear in My reports.</div>
    <div className="case-admin-tools"><label>Status<select value={status} onChange={e => { setStatus(e.target.value); setSkip(0); }}><option value="">All statuses</option>{Object.entries(CASE_STATUSES).map(([key, label]) => <option key={key} value={key}>{key === "awaiting_reporter" ? "Awaiting reporter" : label}</option>)}</select></label>
      <label>Category<select value={category} onChange={e => { setCategory(e.target.value); setSkip(0); }}><option value="">All categories</option>{Object.entries(CASE_CATEGORIES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Search cases<input type="search" value={q} onChange={e => { setQ(e.target.value); setSkip(0); }} placeholder="Title or property" /></label><button className="mb-button secondary" disabled={refreshing} onClick={refresh}>↻ Refresh queue</button></div>
    {error && <div role="alert" className="mb-error">{error.message}</div>}
    {loading ? <p role="status">Loading case queue…</p> : <div className="case-admin-grid"><div className="case-admin-list">{!rows.length && <p className="case-help">No cases match this view.</p>}{rows.map(row => <button key={row.id} className={row.id === selected ? "active" : ""} onClick={() => setParams({ tab: "cases", case: row.id })}>
      <small>CASE #{row.id} · {CASE_CATEGORIES[row.category]}</small><strong>{row.title}</strong><span className={`case-badge ${row.status}`}>{row.status === "awaiting_reporter" ? "Awaiting reporter" : CASE_STATUSES[row.status]}</span><p className="case-help">{row.assigned_name || "Unassigned"}</p></button>)}
      <div className="case-pagination"><button className="mb-button secondary" disabled={!skip} onClick={() => setSkip(p => Math.max(0, p - 20))}>Previous</button><button className="mb-button secondary" disabled={rows.length < 20} onClick={() => setSkip(p => p + 20)}>Next</button></div></div>
      <div className="case-admin-detail">{selected ? <CaseInvestigation key={selected} id={selected} onChanged={refresh} /> : <section className="case-panel"><h2>Your investigation queue is clear.</h2><p className="case-help">New private reports and forum reports will appear here.</p></section>}</div>
    </div>}
  </div>;
}
