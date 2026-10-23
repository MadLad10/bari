import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { cancelBooking, fetchBooking } from "../api";
import { useAuth } from "../auth/AuthContext";
import BookingsLayout from "../components/BookingsLayout";
import useBookingResource from "../lib/useBookingResource";
import { BOOKING_LABELS, bookingDate, bookingMoney, bookingState, canCancelBooking, cancellationDescription } from "../lib/bookings";

export default function BookingDetail({ cancel = false }) {
  const { id } = useParams();
  const { user, ready, openAuth } = useAuth();
  const fetcher = useCallback(() => fetchBooking(id), [id]);
  const { data: booking, loading, error, refresh } = useBookingResource(fetcher, user?.id);
  const [busy, setBusy] = useState(false);
  const [cancelError, setCancelError] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();
  const account = useRef(user?.id);
  account.current = user?.id;
  useEffect(() => { setCancelError(null); setBusy(false); }, [id, user?.id]);
  async function confirmCancellation() {
    if (busy) return;
    const forAccount = user.id;
    setBusy(true); setCancelError(null);
    try {
      await cancelBooking(booking.id);
      if (account.current !== forAccount) return;
      await refresh();
      navigate(`/bookings/${booking.id}`, { replace: true, state: { cancelled: true } });
    } catch (e) {
      if (account.current === forAccount) { setCancelError(e.message); await refresh(); }
    } finally { if (account.current === forAccount) setBusy(false); }
  }
  const state = booking && bookingState(booking);
  const allowedToCancel = booking && canCancelBooking(booking);
  return <BookingsLayout>
    <Link className="mb-back" to="/my-bookings">← My bookings</Link>
    {!ready || (user && loading) ? <div className="mb-empty" role="status">Loading booking…</div> : !user ? <section className="mb-empty"><h1>Your booking is private.</h1><p>Log in to view or cancel your booking.</p><button className="mb-button" onClick={() => openAuth({ reason: "Log in to manage this booking." })}>Log in</button></section> : !booking ? <section className="mb-empty"><h1>{error?.status === 403 ? "This booking belongs to another account." : "Booking unavailable"}</h1><p role="alert">{error?.message || "This booking could not be found."}</p><button className="mb-button secondary" onClick={refresh}>Try again</button></section> : <>
      <div className="mb-heading"><div><span className="mb-eyebrow">BOOKING #{booking.id}</span><h1>{cancel && allowedToCancel ? "Cancel this booking?" : "Your booking"}</h1><p>{booking.property?.title || `Property #${booking.property_id}`}</p></div><span className={`mb-status ${state}`}>{BOOKING_LABELS[state] || state}</span></div>
      {location.state?.cancelled && booking.status === "cancelled" && <div role="status" className="mb-notice">Booking cancelled. Your reserved dates have been released.</div>}
      {error && <div role="alert" className="mb-error">Could not refresh this booking: {error.message}<button onClick={refresh}>Try again</button></div>}
      <div className="mb-detail-grid"><section className="mb-detail-panel"><span className="mb-eyebrow">STAY DETAILS</span><h2>{booking.property?.title || `Property #${booking.property_id}`}</h2>
        {booking.property && <p className="mb-location">{booking.property.address}, {booking.property.city}</p>}
        <dl className="mb-detail-facts"><div><dt>Check-in</dt><dd>{bookingDate(booking.check_in)}</dd></div><div><dt>Check-out</dt><dd>{bookingDate(booking.check_out)}</dd></div><div><dt>Rental period</dt><dd className="mb-capitalize">{booking.rental_type}</dd></div><div><dt>Booking total</dt><dd>{bookingMoney(booking.total_price)}</dd></div><div><dt>Requested on</dt><dd>{bookingDate(booking.created_at)}</dd></div></dl>
        <h3>Renter details</h3><p>{booking.renter_name}</p><p>{booking.renter_phone}</p>{booking.renter_email && <p>{booking.renter_email}</p>}
        {booking.note && <div className="mb-booking-note"><h3>Your note</h3><p>{booking.note}</p></div>}
        {booking.property?.status === "active" ? <Link className="mb-text-link" to={`/property/${booking.property_id}`}>View property & chat with owner ↗</Link> : <p className="mb-status-note">This property is currently hidden from public browsing. Your booking record remains available here.</p>}
      </section><section className={`mb-detail-panel mb-decision-panel${cancel && allowedToCancel ? " cancelling" : ""}`}>
        {cancel && allowedToCancel ? <><span className="mb-eyebrow">CANCELLATION</span><h2>Release these dates?</h2><p>You’re cancelling booking #{booking.id} for {booking.property?.title || "this property"}.</p><p>This releases your reserved dates. You’ll need to make a new request if you change your mind.</p>
          {cancelError && <p role="alert" className="mb-error">{cancelError}</p>}
          <button className="mb-button danger" disabled={busy} onClick={confirmCancellation}>{busy ? "Cancelling…" : "Yes, cancel booking"}</button><Link className={`mb-button secondary${busy ? " disabled" : ""}`} aria-disabled={busy} onClick={e => { if (busy) e.preventDefault(); }} to={`/bookings/${booking.id}`}>Keep booking</Link>
        </> : <><h2>{BOOKING_LABELS[state]}</h2>
          {state === "pending" && <p>Your request is waiting for the owner’s response. The dates are on hold until accepted, rejected or cancelled.</p>}
          {state === "confirmed" && <p>The owner accepted your request. Your stay is confirmed for the dates shown.</p>}
          {state === "completed" && <p>This stay has ended. It’s saved in your booking history and can no longer be cancelled.</p>}
          {state === "expired" && <p>The requested stay ended without owner confirmation. It’s saved in your booking history.</p>}
          {booking.status === "cancelled" && <><p>{cancellationDescription(booking)}</p>{booking.cancelled_at && <p className="mb-status-note">Updated {bookingDate(booking.cancelled_at)}</p>}</>}
          {cancel && !allowedToCancel && <p role="status" className="mb-status-note">This booking cannot be cancelled.</p>}
          {allowedToCancel && <Link className="mb-button secondary" to={`/bookings/${booking.id}/cancel`}>Cancel booking</Link>}
          <Link className="mb-text-link" to={`/reports/new?booking_id=${booking.id}`}>Report a booking issue →</Link>
          <Link className="mb-text-link" to="/my-bookings">View all bookings →</Link>
        </>}
      </section></div>
    </>}
  </BookingsLayout>;
}
