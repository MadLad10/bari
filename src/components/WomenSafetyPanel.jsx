import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { decideWomenSafety, downloadPrivateDocument, fetchWomenSafety, fetchWomenSafetyQueue, submitWomenSafety } from "../api";
import { useAuth } from "../auth/AuthContext";
import useBookingResource from "../lib/useBookingResource";
import { photoUrl } from "./OwnerPhotos";
import "./WomenSafetyPanel.css";

export const safetyLabel = {
  not_submitted: "Safety request needed", pending: "Awaiting safety review", approved: "Safety review approved",
  changes_requested: "Safety changes requested", rejected: "Safety approval declined",
};
const ownerChecks = [
  ["women_only_policy", "Women-only occupancy rules are clearly communicated and enforced."],
  ["secure_access", "Entrance locks and access controls are working."],
  ["common_area_lighting", "Entrances and common areas have working lighting."],
  ["privacy", "Sleeping and bathroom areas provide privacy, without surveillance in private spaces."],
  ["emergency_contact", "Residents have an emergency contact and a way to report problems."],
];
const adminChecks = [
  ["identity_and_documents", "Owner identity and ownership/tenancy checks reviewed."],
  ["access_and_lighting", "Evidence of entrance security and common-area lighting reviewed."],
  ["occupancy_and_privacy", "Women-only occupancy policy and private-space arrangements reviewed."],
  ["emergency_arrangements", "Emergency contact and complaint arrangements checked."],
  ["evidence_reviewed", "Evidence and review method are recorded in the decision notes."],
];

export default function WomenSafetyPanel({ propertyId, admin = false, onChanged }) {
  const { user } = useAuth();
  const fetcher = useCallback(() => fetchWomenSafety(propertyId), [propertyId]);
  const { data, loading, error, refresh } = useBookingResource(fetcher, user?.id);
  const [checks, setChecks] = useState({});
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    setChecks(admin ? {} : data?.submission?.checklist || {});
    setNotes(admin ? "" : data?.submission?.notes || "");
  }, [propertyId, data?.version, admin]);
  const checklist = admin ? adminChecks : ownerChecks;
  const complete = checklist.every(([key]) => checks[key]);
  const canSubmit = data?.is_female_only && !["pending", "approved"].includes(data?.status);
  const canReview = ["pending", "approved"].includes(data?.status);
  const approvalReady = data?.status === "pending" && ["passed", "reviewed"].includes(data?.document_check_status) && !data?.moderation_reason && data?.owner_id !== user?.id;

  async function act(verdict) {
    setBusy(true); setFailure(""); setNotice("");
    try {
      const payload = { expected_version: data.version, checklist: checks, notes };
      if (admin) await decideWomenSafety(propertyId, { ...payload, verdict });
      else await submitWomenSafety(propertyId, payload);
      await refresh();
      await onChanged?.();
      setNotice(admin ? "Safety decision saved." : "Safety request submitted. An admin will review it separately from document checks.");
    } catch (e) { setFailure(e.message); await refresh(); }
    finally { setBusy(false); }
  }
  if (loading) return <p role="status">Loading safety review…</p>;
  return <section className="ws-panel" aria-label="Women-only safety review">
    <header><div><small>WOMEN-ONLY ACCOMMODATION</small><h2>{admin ? data?.title : "Independent safety review"}</h2></div>
      {data && <span className={`ws-status ${data.status}`}>{safetyLabel[data.status]}</span>}</header>
    <p>Ownership checks and safety approval are separate. Women-only listings appear publicly only after both pass. Approval records the evidence reviewed; it is not a guarantee of safety.</p>
    {(error || failure) && <p className="ws-error" role="alert">{failure || error.message}<button type="button" onClick={refresh}>Refresh review</button></p>}
    {notice && <p className="ws-feedback" role="status">{notice}</p>}
    {data && <>
      <p><strong>Ownership checks:</strong> {data.document_check_status.replaceAll("_", " ")} · <strong>Listing:</strong> {data.listing_status === "active" ? "Published" : "Hidden"}</p>
      {data.feedback && <div className="ws-feedback"><strong>Latest feedback</strong><p>{data.feedback}</p></div>}
      {!data.is_female_only && <p>Select women-only accommodation in your listing details to request a review.</p>}
      {admin && <div className="ws-evidence"><h3>Owner submission and evidence</h3><p>{data.owner_name} · {data.address}, {data.area}</p><p>{data.description}</p>
        <Link to={`/property/${propertyId}`} target="_blank" rel="noreferrer">Preview full listing ↗</Link>
        <div className="ws-photos">{data.photos.map((url, i) => <a key={url} href={photoUrl(url)} target="_blank" rel="noreferrer"><img src={photoUrl(url)} alt={`Listing evidence ${i + 1}`} /></a>)}</div>
        <div className="ws-actions">{data.documents.map(doc => <button type="button" key={doc.id} disabled={busy} onClick={async () => { try { await downloadPrivateDocument(doc.url, doc.name); } catch (e) { setFailure(e.message); } }}>Download {doc.name}</button>)}</div>
        <p className="ws-pre">{data.submission?.notes || "Owner has not submitted a safety request."}</p>
        {ownerChecks.map(([key, text]) => <p key={key}>{data.submission?.checklist?.[key] ? "✓" : "—"} {text}</p>)}
      </div>}
      {((!admin && canSubmit) || (admin && canReview)) && <form onSubmit={e => { e.preventDefault(); act(admin ? "approved" : undefined); }}>
        <h3>{admin ? "Admin safety checks" : "Confirm the safety requirements"}</h3>
        {checklist.map(([key, text]) => <label className="ws-check" key={key}><input type="checkbox" checked={!!checks[key]} disabled={busy} onChange={e => setChecks(old => ({ ...old, [key]: e.target.checked }))} /><span>{text}</span></label>)}
        <label className="ws-notes">{admin ? "Decision notes and evidence reviewed (shared with owner)" : "Describe the arrangements and evidence for review"}
          <textarea required minLength={20} maxLength={5000} rows={5} value={notes} disabled={busy} onChange={e => setNotes(e.target.value)} placeholder={admin ? "Record what you checked, evidence sources, contact or inspection method, and findings." : "Explain access controls, lighting, privacy, occupancy rules and emergency arrangements. Describe evidence the admin can check."} /></label>
        <p>Do not include identity numbers, access codes, or residents’ private information.</p>
        {admin && !approvalReady && <p>Approval requires a pending request, completed ownership checks, no moderation hold, and an independent admin. Open investigations must also be resolved.</p>}
        <div className="ws-actions"><button className="primary" type="submit" disabled={busy || !complete || (admin && !approvalReady)}>{busy ? "Saving…" : admin ? "Approve safety review" : "Request safety review"}</button>
          {admin && <><button type="button" disabled={busy || notes.trim().length < 20} onClick={() => act("changes_requested")}>Request changes / revoke approval</button><button type="button" disabled={busy || notes.trim().length < 20} onClick={() => act("rejected")}>Decline approval</button></>}
        </div>
      </form>}
      {!admin && data.status === "pending" && <p>Your request is in the admin safety queue. You can still edit your listing; changing reviewed details will require a fresh request.</p>}
      {data.history.length > 0 && <details><summary>Safety decision history ({data.history.length})</summary>{data.history.map(row => <article className="ws-history" key={row.id}><strong>{safetyLabel[row.verdict]} · {row.reviewer}</strong><small>{new Date(row.created_at).toLocaleString("en-BD")}</small><p className="ws-pre">{row.notes}</p></article>)}</details>}
    </>}
  </section>;
}

export function AdminWomenSafety() {
  const { user } = useAuth();
  const [status, setStatus] = useState("pending");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(null);
  const fetcher = useCallback(() => fetchWomenSafetyQueue({ status, skip: page * 20, limit: 20 }), [status, page]);
  const { data, loading, error, refresh } = useBookingResource(fetcher, user?.id);
  const selectedId = data?.items.find(p => p.property_id === selected)?.property_id || data?.items[0]?.property_id;
  return <div className="ws-admin"><div className="ws-toolbar"><label>Safety review status<select value={status} onChange={e => { setStatus(e.target.value); setPage(0); setSelected(null); }}>{Object.entries(safetyLabel).map(([key, label]) => <option key={key} value={key}>{label}</option>)}<option value="all">All requests</option></select></label><button onClick={refresh}>Refresh queue</button></div>
    {error && <p role="alert" className="ws-error">{error.message}</p>}
    {loading ? <p role="status">Loading safety queue…</p> : !data?.items.length ? <p>No listings in this safety review queue.</p> : <div className="ws-admin-grid"><aside>{data.items.map(p => <button key={p.property_id} className={selectedId === p.property_id ? "selected" : ""} onClick={() => setSelected(p.property_id)}><strong>#{p.property_id} {p.title}</strong><small>{safetyLabel[p.status]}</small></button>)}</aside><WomenSafetyPanel key={selectedId} propertyId={selectedId} admin onChanged={refresh} /></div>}
    <div className="ws-actions"><button disabled={!page} onClick={() => setPage(p => p - 1)}>Previous</button><span>{data?.total || 0} listings</span><button disabled={!data || (page + 1) * 20 >= data.total} onClick={() => setPage(p => p + 1)}>Next</button></div>
  </div>;
}
