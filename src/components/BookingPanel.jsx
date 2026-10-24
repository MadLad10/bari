import { useState, useEffect } from "react";
import { getAvailability, createBooking, quoteBooking } from "../api";
import { useAuth } from "../auth/AuthContext";
import "./BookingPanel.css";

const PAD = (n) => String(n).padStart(2, "0");

function toLocalInput(date) {
  return `${date.getFullYear()}-${PAD(date.getMonth() + 1)}-${PAD(date.getDate())}T${PAD(date.getHours())}:${PAD(date.getMinutes())}`;
}

export default function BookingPanel({ property }) {
  const { id, price, rental_type, listing_type } = property;
  const { user, openAuth } = useAuth();

  const now = new Date(Date.now() + 60 * 60 * 1000);
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const [checkIn, setCheckIn] = useState(toLocalInput(now));
  const [checkOut, setCheckOut] = useState(toLocalInput(tomorrow));
  const [form, setForm] = useState({ renter_name: "", renter_phone: "", renter_email: "", note: "" });
  const [busy, setBusy] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [booking, setBooking] = useState(null);
  const [error, setError] = useState(null);
  const [quote, setQuote] = useState(null);
  const [quoteError, setQuoteError] = useState(null);

  const rentalType = rental_type || "daily";

  useEffect(() => {
    if (user) setForm((p) => ({ ...p, renter_name: p.renter_name || user.name, renter_phone: p.renter_phone || user.phone || "" }));
  }, [user]);

  useEffect(() => {
    if (listing_type === "sale") return;
    getAvailability(id).then(setBusy).catch(() => {});
  }, [id, listing_type]);

  useEffect(() => {
    if (listing_type === "sale") return;
    let current = true;
    setQuote(null);
    setQuoteError(null);
    if (!checkIn || !checkOut || new Date(checkOut) <= new Date(checkIn)) {
      setQuoteError("Choose a check-out time after check-in.");
      return;
    }
    const timer = setTimeout(() => {
      quoteBooking({ property_id: id, check_in: new Date(checkIn).toISOString(),
        check_out: new Date(checkOut).toISOString(), rental_type: rentalType })
        .then(data => { if (current) setQuote(data); })
        .catch(err => { if (current) setQuoteError(err.message); });
    }, 250);
    return () => { current = false; clearTimeout(timer); };
  }, [id, listing_type, rentalType, checkIn, checkOut, price]);

  if (listing_type === "sale") {
    return (
      <div className="bp-card bp-sale">
        <p className="bp-sale-label">This property is listed for sale.</p>
        <p className="bp-sale-hint">Contact the owner directly to enquire about purchase.</p>
      </div>
    );
  }

  const total = quote?.total_price ?? null;

  async function handleBook(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await createBooking({
        property_id: id,
        ...form,
        check_in: new Date(checkIn).toISOString(),
        check_out: new Date(checkOut).toISOString(),
        rental_type: rentalType,
      });
      setBooking(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (booking) {
    return (
      <div className="bp-card bp-confirmed">
        <div className="bp-confirmed-icon">✓</div>
        <h3>{booking.status === "confirmed" ? "Booking confirmed" : booking.status === "pending" ? "Booking request received" : "Booking updated"}</h3>
        <p>Booking #{booking.id} is <strong>{booking.status}</strong>.</p>
        {booking.status === "pending" && <p>Your request is pending confirmation.</p>}
        <div className="bp-confirmed-rows">
          <div><span>Check-in</span><span>{new Date(booking.check_in).toLocaleString("en-BD")}</span></div>
          <div><span>Check-out</span><span>{new Date(booking.check_out).toLocaleString("en-BD")}</span></div>
          <div><span>Total</span><span>৳{booking.total_price.toLocaleString()}</span></div>
        </div>
        <button className="bp-reset" onClick={() => setBooking(null)}>Make another booking</button>
        <a href={`/bookings/${booking.id}`} className="bp-manage">View or cancel this booking →</a>
      </div>
    );
  }

  return (
    <div className="bp-card">
      <div className="bp-price-header">
        <span className="bp-price">৳{Number(price).toLocaleString()}</span>
        <span className="bp-per">/{rentalType === "monthly" ? "mo" : rentalType === "daily" ? "day" : "hr"}</span>
      </div>

      {busy.length > 0 && (
        <div className="bp-busy">
          <p className="bp-busy-label">Already booked:</p>
          {busy.map((b, i) => (
            <div key={i} className="bp-busy-row">
              {new Date(b.check_in).toLocaleDateString("en-BD")} → {new Date(b.check_out).toLocaleDateString("en-BD")}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleBook} className="bp-form">
        <div className="bp-field">
          <label>Check-in</label>
          <input aria-label="Check-in" type="datetime-local" min={toLocalInput(new Date())} value={checkIn} onChange={(e) => setCheckIn(e.target.value)} required />
        </div>
        <div className="bp-field">
          <label>Check-out</label>
          <input aria-label="Check-out" type="datetime-local" value={checkOut} min={checkIn} onChange={(e) => setCheckOut(e.target.value)} required />
        </div>

        {total !== null ? (
          <div className="bp-total">
            <span>Estimated total</span>
            <span>৳{total.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
          </div>
        ) : !quoteError && <p role="status">Calculating total…</p>}
        {quoteError && <div className="bp-error" role="alert">{quoteError}</div>}
        <p className="bp-hint">{rentalType === "daily" ? "Daily rates apply to each started 24-hour period."
          : rentalType === "monthly" ? "Monthly rates apply to each started 30-day period."
          : "Hourly rates use the length of your stay, with a one-hour minimum."}</p>

        <div className="bp-field">
          <label>Your name *</label>
          <input value={form.renter_name} onChange={(e) => setForm(p => ({ ...p, renter_name: e.target.value }))} required placeholder="Full name" />
        </div>
        <div className="bp-field">
          <label>Phone *</label>
          <input value={form.renter_phone} onChange={(e) => setForm(p => ({ ...p, renter_phone: e.target.value }))} required placeholder="01XXXXXXXXX" />
        </div>
        <div className="bp-field">
          <label>Email</label>
          <input type="email" value={form.renter_email} onChange={(e) => setForm(p => ({ ...p, renter_email: e.target.value }))} placeholder="Optional" />
        </div>
        <div className="bp-field">
          <label>Note</label>
          <textarea value={form.note} onChange={(e) => setForm(p => ({ ...p, note: e.target.value }))} rows={2} placeholder="Any special requests…" />
        </div>

        {error && <div className="bp-error">{error}</div>}

        {user ? (
          <button type="submit" className="bp-submit" disabled={submitting || !quote}>
            {submitting ? "Sending request…" : "Request booking"}
          </button>
        ) : (
          <button type="button" className="bp-submit" onClick={() => openAuth({ reason: "Log in to book this place." })}>
            Log in to book
          </button>
        )}
        <p className="bp-hint">No payment collected yet — bKash payment coming soon.</p>
      </form>
    </div>
  );
}
