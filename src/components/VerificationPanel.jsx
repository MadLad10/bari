import { useCallback, useEffect, useState } from "react";
import { downloadPrivateDocument, getVerification, removeDocument, uploadDocument } from "../api";
import "./VerificationPanel.css";

const LABELS = {
  not_submitted: "Documents needed", checking: "Checking documents…", passed: "Document checks passed",
  needs_review: "Admin review needed", reviewed: "Documents reviewed by admin", rejected: "Changes needed",
};

export default function VerificationPanel({ propertyId, onStatusChange }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => getVerification(propertyId).then(setData).catch(e => setError(e.message)), [propertyId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (data && onStatusChange) onStatusChange().catch(e => setError(e.message));
  }, [data?.status, data?.listing_status, onStatusChange]);
  useEffect(() => {
    if (data?.status !== "checking") return;
    const timer = setInterval(load, 2000);
    return () => clearInterval(timer);
  }, [data?.status, load]);

  async function upload(e) {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    setBusy(true);
    setError(null);
    try {
      for (const file of files) {
        if (file.size > 10 * 1024 * 1024) throw new Error(`${file.name} exceeds the 10 MB limit.`);
        await uploadDocument(propertyId, file);
      }
    } catch (err) { setError(err.message); }
    finally { await load(); setBusy(false); }
  }

  async function act(fn) {
    setBusy(true);
    setError(null);
    try { await fn(); await load(); } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <section className="verification-panel" aria-label="Document checks">
      <h2>Ownership documents</h2>
      <p>Upload an ownership or tenancy document showing your account name and this property's full address.
        PDF, JPEG, PNG, or WebP; up to five files, 10 MB each, and five pages per PDF.</p>
      <p>Documents are private to you and admins. Automated checks compare readable text, names, addresses, and document reuse.
        They do not establish legal ownership.</p>
      {data && <>
        <strong className={`verification-state ${data.status}`} role="status">{LABELS[data.status] || data.status}</strong>
        <p>Listing: {data.listing_status === "active" ? "Published" : "Hidden from public browsing"}</p>
        <ul>{data.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
        <ul className="verification-files">
          {data.documents.map(doc => <li key={doc.id}>
            <button type="button" disabled={busy} onClick={() => act(() => downloadPrivateDocument(doc.url, doc.name))}>{doc.name}</button>
            {typeof doc.id === "number" && <button type="button" disabled={busy} onClick={() => act(() => removeDocument(propertyId, doc.id))}>Remove</button>}
          </li>)}
        </ul>
      </>}
      <label className="verification-upload">{busy ? "Uploading…" : "Add or replace documents"}
        <input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" multiple onChange={upload} disabled={busy} />
      </label>
      <p>Matching documents can pass automatically. Unclear submissions go to admin review. Women-only accommodation also needs a separate admin safety approval before publication.</p>
      {error && <p role="alert" className="verification-error">{error}</p>}
    </section>
  );
}
