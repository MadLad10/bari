import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { createCase, fetchCase, fetchMyCases, sendCaseMessage } from "../api";
import { useAuth } from "../auth/AuthContext";
import BookingsLayout from "../components/BookingsLayout";
import CaseTimeline from "../components/CaseTimeline";
import useBookingResource from "../lib/useBookingResource";
import { CASE_STATUSES, CASE_CATEGORIES, caseClosed, caseTime } from "../lib/cases";
import "./Reports.css";

export default function Reports({ create = false }) {
  const { user, ready, openAuth } = useAuth();
  const { id } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [skip, setSkip] = useState(0);
  const fetcher = useCallback(() => id ? fetchCase(id) : fetchMyCases({ status, skip, limit: 20 }), [id, status, skip]);
  const { data, loading, refreshing, error, refresh } = useBookingResource(fetcher, create ? null : user?.id);
  const [form, setForm] = useState(() => ({ category: params.get("booking_id") ? "booking_dispute" : params.get("property_id") ? "unsafe_listing" : "other", title: "", description: "", property_id: params.get("property_id") || "", booking_id: params.get("booking_id") || "" }));
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(null);
  useEffect(() => { setBody(""); setActionError(null); }, [id, user?.id]);
  async function submit(e) {
    e.preventDefault(); setBusy(true); setActionError(null);
    try {
      if (create) {
        const result = await createCase({ ...form, property_id: form.property_id ? Number(form.property_id) : null, booking_id: form.booking_id ? Number(form.booking_id) : null });
        navigate(`/reports/${result.id}`);
      } else { await sendCaseMessage(id, body); setBody(""); await refresh(); }
    } catch (e) { setActionError(e.message); }
    finally { setBusy(false); }
  }
  const change = e => setForm(p => ({ ...p, [e.target.name]: e.target.value }));
  return <BookingsLayout>
    <Link className="mb-back" to={id || create ? "/my-reports" : "/forum"}>← {id || create ? "My reports" : "Community forum"}</Link>
    <div className="mb-heading"><div><span className="mb-eyebrow">REPORTS & RESOLUTIONS</span><h1>{create ? "Report a concern" : id ? `Case #${id}` : "My reports"}</h1><p>{create ? "Send details privately to the admin team." : "Follow your case, respond to questions and see the outcome."}</p></div>{!create && <Link className="mb-button" to="/reports/new">+ New report</Link>}</div>
    {!ready ? <p role="status">Loading your account…</p> : !user ? <div className="mb-empty"><h2>Your reports are private.</h2><p>Log in to submit a concern or track a case.</p><button className="mb-button" onClick={() => openAuth({ reason: "Log in to contact the admin team." })}>Log in to manage reports</button></div> : <>
      {(error || actionError) && <div role="alert" className="mb-error">{actionError || error.message}{!create && <button onClick={refresh}>Refresh</button>}</div>}
      {create ? <form className="case-panel case-form" onSubmit={submit}>
        <p className="case-help">Only you and admins can read this case. Use the forum separately if you want to share a public warning.</p>
        <label>Concern type<select name="category" value={form.category} onChange={change}>{Object.entries(CASE_CATEGORIES).filter(([k]) => k !== "forum_report").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        <label>Title<input name="title" value={form.title} onChange={change} required minLength={5} maxLength={200} placeholder="Briefly describe the issue" /></label>
        <label>Details and evidence<textarea name="description" value={form.description} onChange={change} required minLength={10} maxLength={15000} rows={6} placeholder="What happened, when it happened, and relevant details or evidence references" /></label>
        <div className="case-form-grid"><label>Property number {form.category === "unsafe_listing" ? "(required)" : "(optional)"}<input type="number" min="1" name="property_id" value={form.property_id} onChange={change} required={form.category === "unsafe_listing"} /></label>
          <label>Booking number {form.category === "booking_dispute" ? "(required)" : "(optional)"}<input type="number" min="1" name="booking_id" value={form.booking_id} onChange={change} required={form.category === "booking_dispute"} /></label></div>
        <p className="case-help">For booking disputes, use a booking you made or manage. Evidence can be included as text; file attachments aren’t supported here.</p>
        <button className="mb-button" disabled={busy}>{busy ? "Submitting…" : "Submit private report"}</button>
      </form> : loading ? <p role="status">Loading your cases…</p> : id && data ? <>
        <section className="case-panel"><div className="case-heading"><div><span className="mb-eyebrow">{CASE_CATEGORIES[data.category]}</span><h2>{data.title}</h2></div><span className={`case-badge ${data.status}`}>{CASE_STATUSES[data.status]}</span></div>
          <p className="case-body">{data.description}</p><p className="case-help">{data.property_title && `Property: ${data.property_title} · `}{data.booking_reference && `Booking #${data.booking_reference} · `}Submitted {caseTime(data.created_at)}</p>
          {data.resolution && <div className="case-resolution"><h3>Admin outcome</h3><p>{data.resolution}</p></div>}
          {data.status === "awaiting_reporter" && <div className="mb-notice">An admin needs more information. Add your response below to continue the investigation.</div>}
          <div className="case-heading"><h3>Case updates</h3><button className="mb-refresh" disabled={refreshing} onClick={refresh}>↻ Refresh</button></div><CaseTimeline updates={data.updates} />
          {!caseClosed(data) ? <form className="case-form" onSubmit={submit}><label>Your response<textarea value={body} onChange={e => setBody(e.target.value)} rows={4} minLength={2} maxLength={10000} required /></label><button className="mb-button" disabled={busy}>{busy ? "Sending…" : "Send response"}</button></form> : <p className="case-help">This case is closed. Its outcome and updates remain available here.</p>}
        </section>
      </> : !id ? <>
        <div className="case-heading"><label className="case-filter">Case status<select value={status} onChange={e => { setStatus(e.target.value); setSkip(0); }}><option value="">All cases</option>{Object.entries(CASE_STATUSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label><button className="mb-refresh" disabled={refreshing} onClick={refresh}>↻ Refresh</button></div>
        {!data?.length && !error ? <section className="mb-empty"><h2>No reports in this view</h2><p>Reports you submit privately or through the forum appear here.</p><Link className="mb-button" to="/reports/new">Report a concern</Link></section> : data?.map(row => <Link className="case-panel case-list-item" key={row.id} to={`/reports/${row.id}`}><div><span className="mb-eyebrow">CASE #{row.id} · {CASE_CATEGORIES[row.category]}</span><h2>{row.title}</h2><p>{row.property_title || "General concern"} · Updated {caseTime(row.updated_at)}</p>{row.resolution && <p className="case-outcome-preview">{row.resolution}</p>}</div><span className={`case-badge ${row.status}`}>{CASE_STATUSES[row.status]}</span></Link>)}
        <div className="case-pagination"><button className="mb-button secondary" disabled={!skip} onClick={() => setSkip(p => Math.max(0, p - 20))}>Previous</button><button className="mb-button secondary" disabled={data?.length !== 20} onClick={() => setSkip(p => p + 20)}>Next</button></div>
      </> : null}
    </>}
  </BookingsLayout>;
}
