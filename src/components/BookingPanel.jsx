import { useState, useEffect } from "react";
import { getAvailability, createBooking } from "../api";
import { useAuth } from "../auth/AuthContext";
import "./BookingPanel.css";

const PAD = (n) => String(n).padStart(2, "0");

function toLocalInput(date) {
  return `${date.getFullYear()}-${PAD(date.getMonth() + 1)}-${PAD(date.getDate())}T${PAD(date.getHours())}:${PAD(date.getMinutes())}`;
}

function computePrice(price, rentalType, checkIn, checkOut) {
  const delta = (new Date(checkOut) - new Date(checkIn)) / 1000;
  if (rentalType === "hourly") return price * Math.max(delta / 3600, 1);
  if (rentalType === "daily") return price * Math.max(Math.ceil(delta / 86400), 1);
  return price * Math.max(Math.round(delta / (86400 * 30)), 1);
}

export default function BookingPanel({ property }) {
  const { id, price, rental_type, listing_type } = property;
  const { user, openAuth } = useAuth();

  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const [checkIn, setCheckIn] = useState(toLocalInput(now));
  const [checkOut, setCheckOut] = useState(toLocalInput(tomorrow));
  const [form, setForm] = useState({ renter_name: "", renter_phone: "", renter_email: "", note: "" });
  const [busy, setBusy] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [booking, setBooking] = useState(null);
  const [error, setError] = useState(null);

  const rentalType = rental_type || "daily";

  useEffect(() => {
    if (user) setForm((p) => ({ ...p, renter_name: p.renter_name || user.name, renter_phone: p.renter_phone || user.phone || "" }));
  }, [user]);

  useEffect(() => {
    if (listing_type === "sale") return;
    getAvailability(id).then(setBusy).catch(() => {});
  }, [id, listing_type]);

  if (listing_type === "sale") {
    return (
      <div className="bp-card bp-sale">
        <p className="bp-sale-label">This property is listed for sale.</p>
        <p className="bp-sale-hint">Contact the owner directly to enquire about purchase.</p>
      </div>
    );
  }

  const total = checkIn && checkOut ? computePrice(price, rentalType, checkIn, checkOut) : null;

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
        <h3>Booking Confirmed</h3>
        <p>Booking #{booking.id} is <strong>{booking.status}</strong>.</p>
        <div className="bp-confirmed-rows">
          <div><span>Check-in</span><span>{new Date(booking.check_in).toLocaleString("en-BD")}</span></div>
          <div><span>Check-out</span><span>{new Date(booking.check_out).toLocaleString("en-BD")}</span></div>
          <div><span>Total</span><span>৳{booking.total_price.toLocaleString()}</span></div>
        </div>
        <button className="bp-reset" onClick={() => setBooking(null)}>Make another booking</button>
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
          <input type="datetime-local" value={checkIn} onChange={(e) => setCheckIn(e.target.value)} required />
        </div>
        <div className="bp-field">
          <label>Check-out</label>
          <input type="datetime-local" value={checkOut} min={checkIn} onChange={(e) => setCheckOut(e.target.value)} required />
        </div>

        {total !== null && (
          <div className="bp-total">
            <span>Estimated total</span>
            <span>৳{total.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
          </div>
        )}

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
          <button type="submit" className="bp-submit" disabled={submitting}>
            {submitting ? "Booking…" : "Confirm Booking"}
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
