import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { acceptBooking, cancelBooking, declineBooking, deleteProperty, fetchMyProperties, fetchOwnerBookings, fetchOwnerInbox, updateProperty } from "../api";
import { useAuth } from "../auth/AuthContext";
import OwnerPropertyEditor from "../components/OwnerPropertyEditor";
import OwnerPhotos, { photoUrl } from "../components/OwnerPhotos";
import OwnerCalendar from "../components/OwnerCalendar";
import Conversation from "../components/Conversation";
import VerificationPanel from "../components/VerificationPanel";
import WomenSafetyPanel, { safetyLabel } from "../components/WomenSafetyPanel";
import "../components/Conversation.css";
import "./OwnerDashboard.css";
import { canCancelBooking } from "../lib/bookings";

const TABS = [
  ["overview", "Overview", "overview"], ["listings", "My properties", "home"], ["bookings", "Booking requests", "booking"],
  ["calendar", "Availability", "calendar"], ["messages", "Messages", "message"], ["documents", "Document checks", "shield"],
  ["women-safety", "Women-only safety", "shield"],
];
const money = value => `৳${Number(value).toLocaleString("en-BD", { maximumFractionDigits: 2 })}`;
const dateTime = value => new Date(value).toLocaleString("en-BD", { dateStyle: "medium", timeStyle: "short" });
const period = { monthly: "/month", daily: "/day", hourly: "/hour" };
const checkLabel = { not_submitted: "Documents needed", checking: "Checking documents", passed: "Checks passed", needs_review: "Admin review", reviewed: "Admin approved", rejected: "Changes needed" };

function Icon({ name, ...props }) {
  const paths = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    home: <><path d="m3 10 9-7 9 7v10H3Z" /><path d="M9 20v-7h6v7" /></>,
    booking: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 3h6v4H9zM9 12h6M9 16h4" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4m10-4v4M3 11h18M7 15h2m4 0h2" /></>,
    message: <path d="M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 1 1 17-5Z" />,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z" /><path d="m8 12 3 3 5-6" /></>,
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name] || paths.home}</svg>;
}

function Empty({ icon = "home", title, children }) {
  return <div className="od-empty"><span><Icon name={icon} width="30" height="30" /></span><h3>{title}</h3><p>{children}</p></div>;
}

export default function OwnerDashboard() {
  const { user, ready, openAuth, logout } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(t => t[0] === params.get("tab")) ? params.get("tab") : "overview";
  const [properties, setProperties] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [inbox, setInbox] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(null);
  const [editing, setEditing] = useState(null);
  const [mediaId, setMediaId] = useState(null);
  const [documentId, setDocumentId] = useState(null);
  const [conversationKey, setConversationKey] = useState(null);
  const [query, setQuery] = useState("");
  const [listingFilter, setListingFilter] = useState("all");
  const [bookingFilter, setBookingFilter] = useState("pending");
  const [bookingProperty, setBookingProperty] = useState("");
  const allowed = user && ["owner", "admin"].includes(user.role);
  const account = useRef(user?.id);
  account.current = user?.id;

  const refreshProperties = useCallback(async () => {
    const rows = await fetchMyProperties();
    if (account.current === user?.id) setProperties(rows);
  }, [user?.id]);
  const load = useCallback(async () => {
    const results = await Promise.allSettled([fetchMyProperties(), fetchOwnerBookings(), fetchOwnerInbox()]);
    if (account.current !== user?.id) return;
    [setProperties, setBookings, setInbox].forEach((setter, i) => { if (results[i].status === "fulfilled") setter(results[i].value); });
    const failure = results.find(r => r.status === "rejected");
    if (failure) throw failure.reason;
  }, [user?.id]);
  useEffect(() => {
    setProperties([]); setBookings([]); setInbox([]); setLoading(true); setError(null);
    setEditing(null); setMediaId(null); setDocumentId(null); setConversationKey(null); setNotice(null);
    if (!allowed) return;
    let active = true;
    load().catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [user?.id, allowed, load]);
  useEffect(() => {
    if (!allowed) return;
    const timer = setInterval(() => load().catch(e => setError(e.message)), 15000);
    return () => clearInterval(timer);
  }, [allowed, load]);

  const navigate = (next, propertyId) => {
    setParams(next === "overview" ? {} : { tab: next });
    if (propertyId) setDocumentId(propertyId);
    setError(null); setNotice(null);
  };
  async function act(key, fn, message) {
    setBusy(key); setError(null); setNotice(null);
    try { await fn(); await load(); setNotice(message); }
    catch (e) { setError(e.message); }
    finally { setBusy(null); }
  }
  const pending = bookings.filter(b => b.status === "pending" && new Date(b.check_out) > new Date());
  const active = properties.filter(p => p.status === "active");
  const attention = properties.filter(p => !["passed", "reviewed"].includes(p.document_check_status) || p.moderation_reason);
  const names = Object.fromEntries(properties.map(p => [p.id, p.title]));
  const selectedDocument = properties.find(p => p.id === documentId) || properties[0];
  const womenProperties = properties.filter(p => p.is_female_only);
  const selectedSafety = womenProperties.find(p => p.id === documentId) || womenProperties[0];
  const safetyAttention = womenProperties.filter(p => p.women_safety_status !== "approved");
  const selectedMedia = properties.find(p => p.id === mediaId);
  const selectedConversation = inbox.find(c => `${c.property_id}:${c.session_token}` === conversationKey) || inbox[0];
  const filteredListings = properties.filter(p => (listingFilter === "all" || (listingFilter === "review" ? attention.includes(p) : p.status === listingFilter)) && `${p.title} ${p.area}`.toLowerCase().includes(query.toLowerCase()));
  const filteredBookings = bookings.filter(b => (bookingFilter === "all" || b.status === bookingFilter) && (!bookingProperty || b.property_id === Number(bookingProperty)));

  function BookingCard({ booking: b, compact = false }) {
    return <article className={`od-booking-card${compact ? " compact" : ""}`}>
      <div className="od-booking-top"><div><span className="od-eyebrow">REQUEST #{b.id}</span><h3>{b.renter_name}</h3><span>{b.property?.archived_at ? (b.property.title + " (archived)") : <Link to={`/property/${b.property_id}`}>{names[b.property_id] || b.property?.title || `Property #${b.property_id}`}</Link>}</span></div>
        <span className={`od-badge ${b.status}`}>{b.status === "cancelled" ? ({ owner_declined: "Rejected", renter_cancelled: "Cancelled by renter", owner_cancelled: "Cancelled by owner", admin_cancelled: "Cancelled by admin" }[b.cancellation_reason] || "Cancelled") : b.status}</span></div>
      <div className="od-booking-dates"><div><span>Check-in</span><strong>{dateTime(b.check_in)}</strong></div><div><span>Check-out</span><strong>{dateTime(b.check_out)}</strong></div><div><span>Booking total</span><strong>{money(b.total_price)}</strong></div></div>
      {!compact && <div className="od-booking-contact"><a href={`tel:${b.renter_phone}`}>{b.renter_phone}</a>{b.renter_email && <a href={`mailto:${b.renter_email}`}>{b.renter_email}</a>}{b.note && <p>Note: {b.note}</p>}</div>}
      <div className="od-actions">
        {b.status === "pending" && <><button className="od-button" disabled={!!busy || new Date(b.check_out) <= new Date()} onClick={() => act(`booking-${b.id}`, () => acceptBooking(b.id), "Booking accepted. The renter can see the confirmed status.")}>Accept request</button>
          <button className="od-button secondary" disabled={!!busy} onClick={() => act(`booking-${b.id}`, () => declineBooking(b.id), "Request rejected. The renter can see the decision in their booking history.")}>Reject request</button></>}
        {b.status === "confirmed" && canCancelBooking(b) && <button className="od-button danger" disabled={!!busy} onClick={() => {
          if (window.confirm(`Cancel ${b.renter_name}'s confirmed booking? This will free the reserved dates.`)) act(`booking-${b.id}`, () => cancelBooking(b.id), "Booking cancelled and dates released.");
        }}>Cancel booking</button>}
      </div>
    </article>;
  }

  return <div className="od-layout">
    <aside className="od-sidebar">
      <Link to="/" className="od-logo">bari<span>.com</span></Link><span className="od-workspace">OWNER WORKSPACE</span>
      <div className="od-side-links" aria-label="Owner dashboard sections">{TABS.map(([key, label, icon]) => <button key={key} onClick={() => navigate(key)} className={tab === key ? "active" : ""} aria-current={tab === key ? "page" : undefined}><Icon name={icon} /><span>{label}</span>{key === "bookings" && pending.length > 0 && <b>{pending.length}</b>}</button>)}</div>
      <div className="od-sidebar-bottom"><Link to="/browse"><Icon name="home" />Browse properties <span>↗</span></Link><Link to="/forum"><Icon name="message" />Community forum</Link>
        <div className="od-side-help"><Icon name="shield" /><p>A little peace of mind.</p><small>Keep your documents current and your listing details accurate.</small></div>
        {user && <div className="od-profile"><span>{user.name.slice(0, 1)}</span><div><strong>{user.name}</strong><small>{user.role === "admin" ? "Admin account" : "Property owner"}</small></div><button onClick={logout}>Log out</button></div>}
      </div>
    </aside>
    <div className="od-main">
      <header className="od-topbar"><span>Your properties. All in one place.</span><div className="od-topbar-actions">{user && <button className="od-mobile-logout" onClick={logout}>Log out</button>}<Link to="/list-property" className="od-button">+ List a property</Link></div></header>
      <main className="od-content">
        {!ready ? <p role="status">Loading your account…</p> : !allowed ? <section className="od-panel od-gate"><Icon name="home" width="40" height="40" /><h1>Your owner workspace</h1><p>{user ? "This dashboard is for property owner accounts." : "Log in as an owner to manage your properties, booking requests and conversations."}</p>
          {!user && <button className="od-button" onClick={() => openAuth({ role: "owner", reason: "Log in to your owner dashboard." })}>Log in as an owner</button>}<Link to="/browse" className="od-text-link">Browse properties →</Link></section>
          : <>
            <div className="od-page-heading"><div><span className="od-eyebrow">{new Date().toLocaleDateString("en-BD", { weekday: "long", month: "long", day: "numeric", year: "numeric" })}</span>
              <h1>{tab === "overview" ? `Welcome back, ${user.name.split(" ")[0]}.` : TABS.find(t => t[0] === tab)[1]}</h1>
              <p>{tab === "overview" ? "A clear view of your properties and what needs your attention." : { listings: "Keep every space up to date, from the first photo to the final detail.", bookings: "Review your renters’ dates and respond to their requests.", calendar: "See confirmed stays and pending holds across your properties.", messages: "Good conversations make finding a home a little easier.", documents: "Manage private documents and follow your listing’s verification status." }[tab]}</p></div>
              <button className="od-refresh" disabled={loading || !!busy} onClick={() => act("refresh", load, "Dashboard updated.")}>↻ Refresh</button>
            </div>
            {error && <div role="alert" className="od-error">{error}<button onClick={() => act("retry", load, "Dashboard updated.")}>Retry</button></div>}
            {notice && <div className="od-notice" role="status">{notice}</div>}
            {loading ? <div className="od-panel od-loading" role="status">Loading your workspace…</div> : <>
              {tab === "overview" && <>
                <div className="od-stats">
                  {[["Total properties", properties.length, `${active.length} published`, "home"], ["Booking requests", pending.length, "Awaiting your response", "booking"], ["Document attention", attention.length, "Listings to check", "shield"], ["Conversations", inbox.length, "Private renter threads", "message"]].map(([label, value, note, icon]) => <div className="od-stat" key={label}><div><span>{label}</span><Icon name={icon} /></div><strong>{value}</strong><small>{note}</small></div>)}
                </div>
                {attention.length > 0 && <div className="od-attention"><Icon name="shield" /><div><strong>{attention.length} {attention.length === 1 ? "property needs" : "properties need"} a document check</strong><p>Review feedback or add documents to move your listings forward.</p></div><button onClick={() => navigate("documents", attention[0].id)}>Review documents →</button></div>}
                {safetyAttention.length > 0 && <div className="od-attention"><Icon name="shield" /><div><strong>{safetyAttention.length} women-only listings need separate safety approval</strong><p>Submit the safety checklist and follow admin feedback before publication.</p></div><button onClick={() => navigate("women-safety", safetyAttention[0].id)}>Safety review →</button></div>}
                <div className="od-overview-grid"><section className="od-panel"><div className="od-panel-heading"><div><span className="od-eyebrow">NEXT ON YOUR LIST</span><h2>Booking requests</h2></div><button className="od-text-link" onClick={() => navigate("bookings")}>View all →</button></div>
                  {!pending.length ? <Empty icon="booking" title="You’re all caught up">New requests will appear here when renters book your properties.</Empty> : pending.slice(0, 3).map(b => <BookingCard key={b.id} booking={b} compact />)}
                </section><div className="od-overview-side"><section className="od-panel"><div className="od-panel-heading"><h2>Your properties</h2><button className="od-text-link" onClick={() => navigate("listings")}>View all →</button></div>
                  {!properties.length ? <Empty title="Your first listing starts here"><Link to="/list-property">Add a property to get started →</Link></Empty> : properties.slice(0, 3).map(p => <button className="od-mini-property" key={p.id} onClick={() => { navigate("listings"); setQuery(p.title); }}><span className="od-mini-photo">{p.photos[0] ? <img src={photoUrl(p.photos[0])} alt="" /> : <Icon name="home" />}</span><span><strong>{p.title}</strong><small>{p.area} · {money(p.price)}{p.listing_type === "sale" ? "" : period[p.rental_type]}</small></span><span className={`od-status-dot ${p.status}`} /></button>)}
                </section><section className="od-panel"><div className="od-panel-heading"><h2>Latest conversations</h2><button className="od-text-link" onClick={() => navigate("messages")}>Inbox →</button></div>
                  {!inbox.length ? <p className="od-muted">Renter questions will appear here.</p> : inbox.slice(0, 2).map(c => <button className="od-mini-message" key={`${c.property_id}:${c.session_token}`} onClick={() => { setConversationKey(`${c.property_id}:${c.session_token}`); navigate("messages"); }}><strong>{c.renter_name}</strong><p>{c.last_message}</p></button>)}
                </section></div></div>
              </>}

              {tab === "listings" && <>
                <div className="od-filter-bar"><label className="od-search"><Icon name="home" /><input aria-label="Search your properties" placeholder="Search by name or neighborhood" value={query} onChange={e => setQuery(e.target.value)} /></label>
                  <select aria-label="Filter listing status" value={listingFilter} onChange={e => setListingFilter(e.target.value)}><option value="all">All properties ({properties.length})</option><option value="active">Published</option><option value="pending">Pending</option><option value="inactive">Paused</option><option value="review">Needs attention</option></select></div>
                {!filteredListings.length ? <section className="od-panel"><Empty title={properties.length ? "No matching properties" : "Make room for your first listing"}>{properties.length ? "Try a different search or status filter." : <Link to="/list-property">List a property to get started →</Link>}</Empty></section> : <div className="od-listing-grid">{filteredListings.map(p => <article className="od-property-card" key={p.id}>
                  <div className="od-property-cover">{p.photos[0] ? <img src={photoUrl(p.photos[0])} alt={p.title} loading="lazy" /> : <div className="od-property-placeholder"><Icon name="home" width="50" height="50" /><span>Add a photo of your space</span></div>}<span className={`od-badge ${p.status}`}>{p.status === "active" ? "Published" : p.status === "inactive" ? "Paused" : "Pending"}</span></div>
                  <div className="od-property-body"><div className="od-property-meta">{p.property_type} · {p.listing_type} {p.is_female_only && "· Women only"}</div><h2><Link to={`/property/${p.id}`}>{p.title}</Link></h2><p className="od-muted">{p.area}, {p.city} · {p.bedrooms} bed · {p.furnishing.replaceAll("_", " ")}</p><div className="od-property-price">{money(p.price)}<small>{p.listing_type === "sale" ? " sale price" : period[p.rental_type] || "/period"}</small></div>
                    <button className="od-check-link" onClick={() => navigate("documents", p.id)}><Icon name="shield" />{checkLabel[p.document_check_status] || "Documents needed"} →</button>
                    {p.is_female_only && <button className="od-check-link" onClick={() => navigate("women-safety", p.id)}><Icon name="shield" />{safetyLabel[p.women_safety_status] || "Safety request needed"} →</button>}
                    {p.moderation_reason && <p className="od-moderation-note">{p.moderation_reason}</p>}
                    <div className="od-property-actions"><button className="od-button secondary" onClick={() => setEditing(p)}>Edit details</button><button className="od-button secondary" onClick={() => setMediaId(mediaId === p.id ? null : p.id)}>Photos</button>
                      <button className="od-button secondary" disabled={!!busy || (p.status !== "active" && (!["passed", "reviewed"].includes(p.document_check_status) || !!p.moderation_reason || (p.is_female_only && p.women_safety_status !== "approved")))} onClick={() => act(`listing-${p.id}`, () => updateProperty(p.id, { status: p.status === "active" ? "inactive" : "active" }), p.status === "active" ? "Listing paused. Existing bookings remain in your calendar." : "Listing published.")}>{p.status === "active" ? "Pause" : "Publish"}</button>
                    </div><div className="od-property-footer"><Link to={`/property/${p.id}`}>Preview listing ↗</Link><button disabled={!!busy} onClick={() => { if (window.confirm(`Archive “${p.title}”? It will be removed from your listings and public browsing. Existing booking history will be retained.`)) act(`delete-${p.id}`, () => deleteProperty(p.id), "Listing archived. Booking history has been preserved."); }}>Archive</button></div>
                  </div></article>)}</div>}
                {selectedMedia && <section className="od-panel" id="owner-photos"><div className="od-panel-heading"><h2>{selectedMedia.title}</h2><button className="od-icon-button" onClick={() => setMediaId(null)} aria-label="Close photo manager">×</button></div><OwnerPhotos key={selectedMedia.id} property={selectedMedia} onChanged={refreshProperties} /></section>}
              </>}

              {tab === "bookings" && <>
                <div className="od-filter-bar"><div className="od-filter-tabs" aria-label="Booking status">{[["pending", "Pending"], ["confirmed", "Confirmed"], ["cancelled", "Rejected / cancelled"], ["all", "All"]].map(([key, label]) => <button key={key} className={bookingFilter === key ? "active" : ""} onClick={() => setBookingFilter(key)} aria-pressed={bookingFilter === key}>{label}{key === "pending" && ` (${bookings.filter(b => b.status === "pending").length})`}</button>)}</div>
                  <select aria-label="Filter booking property" value={bookingProperty} onChange={e => setBookingProperty(e.target.value)}><option value="">All properties</option>{properties.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></div>
                {!filteredBookings.length ? <section className="od-panel"><Empty icon="booking" title="No requests in this view">Requests and their current status will appear here.</Empty></section> : <div className="od-booking-list">{filteredBookings.map(b => <BookingCard key={b.id} booking={b} />)}</div>}
              </>}
              {tab === "calendar" && <OwnerCalendar bookings={bookings} properties={properties} />}
              {tab === "women-safety" && <section className="od-panel">{!selectedSafety ? <Empty icon="shield" title="No women-only listings">Select women-only accommodation when creating or editing a property, then request a separate safety review here.</Empty> : <>
                <label className="od-field od-property-select"><span>Select a women-only property</span><select aria-label="Select a women-only property" value={selectedSafety.id} onChange={e => setDocumentId(Number(e.target.value))}>{womenProperties.map(p => <option key={p.id} value={p.id}>{p.title} — {safetyLabel[p.women_safety_status] || "Safety request needed"}</option>)}</select></label>
                <WomenSafetyPanel key={selectedSafety.id} propertyId={selectedSafety.id} onChanged={refreshProperties} />
              </>}</section>}
              {tab === "messages" && <section className="od-panel od-inbox-panel">{!inbox.length ? <Empty icon="message" title="Your inbox is ready">When a renter messages you from a listing, the private conversation appears here.</Empty> : <div className="od-inbox"><div className="od-thread-list">{inbox.map(c => <button key={`${c.property_id}:${c.session_token}`} className={c === selectedConversation ? "active" : ""} onClick={() => setConversationKey(`${c.property_id}:${c.session_token}`)}><strong>{c.renter_name}</strong><small>{c.property_title}</small><p>{c.last_sender === "owner" ? "You: " : ""}{c.last_message}</p><time>{new Date(c.updated_at).toLocaleDateString("en-BD", { month: "short", day: "numeric" })}</time></button>)}</div>
                <div className="od-thread"><div className="od-thread-heading"><h2>{selectedConversation.renter_name}</h2><Link to={`/property/${selectedConversation.property_id}`}>{selectedConversation.property_title} ↗</Link></div><Conversation key={`${selectedConversation.property_id}:${selectedConversation.session_token}`} propertyId={selectedConversation.property_id} sessionToken={selectedConversation.session_token} owner /></div></div>}</section>}
              {tab === "documents" && <section className="od-panel">{!properties.length ? <Empty icon="shield" title="Add your first property"><Link to="/list-property">Save a listing, then upload its ownership documents →</Link></Empty> : <>
                <label className="od-field od-property-select"><span>Select a property</span><select aria-label="Select a property" value={selectedDocument.id} onChange={e => setDocumentId(Number(e.target.value))}>{properties.map(p => <option key={p.id} value={p.id}>{p.title} — {checkLabel[p.document_check_status]}</option>)}</select></label>
                {selectedDocument.moderation_reason && <p className="od-moderation-note">Admin feedback: {selectedDocument.moderation_reason}</p>}
                <VerificationPanel key={selectedDocument.id} propertyId={selectedDocument.id} onStatusChange={refreshProperties} /></>}</section>}
            </>}
            <footer className="od-footer"><Link to="/">bari.com</Link><span>A better place to call home.</span><Link to="/forum">Visit the community ↗</Link></footer>
          </>}
      </main>
    </div>
    {editing && <OwnerPropertyEditor key={editing.id} property={editing} onClose={() => setEditing(null)} onSaved={async () => { await load(); setNotice("Property details saved."); }} />}
  </div>;
}
