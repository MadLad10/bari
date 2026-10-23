import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API_ROOT, fetchMyBookings } from "../api";
import { useAuth } from "../auth/AuthContext";
import BookingsLayout from "../components/BookingsLayout";
import useBookingResource from "../lib/useBookingResource";
import { BOOKING_LABELS, bookingDate, bookingMoney, bookingState, canCancelBooking, cancellationDescription } from "../lib/bookings";

const FILTERS = [["all", "All bookings"], ["upcoming", "Upcoming & current"], ["pending", "Awaiting owner"], ["past", "Past stays"], ["cancelled", "Cancelled & rejected"]];

export default function MyBookings() {
  const { user, ready, openAuth } = useAuth();
  const { data, loading, refreshing, error, refresh } = useBookingResource(fetchMyBookings, user?.id);
  const [params, setParams] = useSearchParams();
  const filter = FILTERS.some(([key]) => key === params.get("filter")) ? params.get("filter") : "all";
  const [query, setQuery] = useState("");
  const rows = data || [];
  const upcoming = rows.filter(b => b.status === "confirmed" && new Date(b.check_out) > new Date());
  const pending = rows.filter(b => bookingState(b) === "pending");
  const filtered = useMemo(() => rows.filter(b => {
    const state = bookingState(b);
    const matches = filter === "all" || (filter === "upcoming" && state === "confirmed") ||
      (filter === "pending" && state === "pending") || (filter === "past" && ["completed", "expired"].includes(state)) ||
      (filter === "cancelled" && ["cancelled", "rejected"].includes(state));
    return matches && `${b.id} ${b.property?.title || ""} ${b.property?.area || ""}`.toLowerCase().includes(query.toLowerCase());
  }), [rows, filter, query]);

  return <BookingsLayout>
    <div className="mb-heading"><div><span className="mb-eyebrow">YOUR RENTAL JOURNEY</span><h1>My bookings</h1><p>Your requests, upcoming stays and booking history, all in one place.</p></div><Link to="/browse" className="mb-button">Find a place ↗</Link></div>
    {!ready ? <div className="mb-empty" role="status">Loading your account…</div> : !user ? <section className="mb-empty"><h2>Your next stay starts here.</h2><p>Log in to see your booking history and manage your requests.</p><button className="mb-button" onClick={() => openAuth({ reason: "Log in to view your private booking history." })}>Log in to view bookings</button></section> : <>
      <div className="mb-summary"><div><strong>{rows.length}</strong><span>Total bookings</span></div><div><strong>{upcoming.length}</strong><span>Upcoming & current stays</span></div><div><strong>{pending.length}</strong><span>Awaiting owner</span></div></div>
      <div className="mb-tools"><div className="mb-filters" aria-label="Filter bookings">{FILTERS.map(([key, label]) => <button key={key} aria-pressed={filter === key} className={filter === key ? "active" : ""} onClick={() => setParams(key === "all" ? {} : { filter: key })}>{label}</button>)}</div>
        <div className="mb-search-row"><input type="search" aria-label="Search bookings" placeholder="Search property, area or booking number" value={query} onChange={e => setQuery(e.target.value)} /><button className="mb-refresh" onClick={refresh} disabled={refreshing}>{refreshing ? "Updating…" : "↻ Refresh"}</button></div>
      </div>
      {error && <div className="mb-error" role="alert">{error.message}<button onClick={refresh}>Try again</button></div>}
      {loading ? <div className="mb-empty" role="status">Loading your bookings…</div> : !rows.length && !error ? <section className="mb-empty"><span className="mb-empty-symbol">⌂</span><h2>Make yourself at home.</h2><p>You haven’t made a booking yet. Find a place you like and send the owner a request.</p><Link className="mb-button" to="/browse">Explore properties</Link></section> : !filtered.length && !error ? <section className="mb-empty"><h2>No bookings in this view</h2><p>Try a different filter or search.</p><button className="mb-button secondary" onClick={() => { setQuery(""); setParams({}); }}>Show all bookings</button></section> : <div className="mb-booking-list">{filtered.map(b => {
        const state = bookingState(b);
        const property = b.property;
        const photo = property?.photos?.[0];
        return <article key={b.id} className="mb-card" aria-label={`Booking ${b.id}`}>
          <div className="mb-card-photo">{photo ? <img src={photo.startsWith("/") ? `${API_ROOT}${photo}` : photo} alt="" loading="lazy" /> : <span aria-hidden="true">⌂</span>}</div>
          <div className="mb-card-body"><div className="mb-card-top"><span className="mb-eyebrow">BOOKING #{b.id} · {b.rental_type} rental</span><span className={`mb-status ${state}`}>{BOOKING_LABELS[state] || state}</span></div>
            <h2><Link to={`/bookings/${b.id}`}>{property?.title || `Property #${b.property_id}`}</Link></h2><p className="mb-location">{property ? `${property.area}, ${property.city}` : "Open your booking for details"}</p>
            <dl className="mb-dates"><div><dt>Check-in</dt><dd>{bookingDate(b.check_in)}</dd></div><div><dt>Check-out</dt><dd>{bookingDate(b.check_out)}</dd></div><div><dt>Booking total</dt><dd>{bookingMoney(b.total_price)}</dd></div></dl>
            {b.status === "cancelled" && <p className="mb-status-note">{cancellationDescription(b)}</p>}
            {state === "pending" && <p className="mb-status-note">The owner hasn’t accepted this request yet. Your selected dates are on hold.</p>}
            <div className="mb-card-actions"><Link className="mb-button secondary" to={`/bookings/${b.id}`}>View booking</Link>{canCancelBooking(b) && <Link className="mb-cancel-link" to={`/bookings/${b.id}/cancel`}>Cancel booking</Link>}</div>
          </div>
        </article>;
      })}</div>}
      <p className="mb-update-note">Statuses update automatically while this page is open.</p>
    </>}
  </BookingsLayout>;
}
