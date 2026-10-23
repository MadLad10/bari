import { useState } from "react";

export default function OwnerCalendar({ bookings, properties }) {
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [selected, setSelected] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()));
  const [propertyId, setPropertyId] = useState("");
  const visible = bookings.filter(b => b.status !== "cancelled" && (!propertyId || b.property_id === Number(propertyId)));
  const forDay = date => {
    const next = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1);
    return visible.filter(b => new Date(b.check_in) < next && new Date(b.check_out) > date);
  };
  const names = Object.fromEntries(properties.map(p => [p.id, p.title]));
  const count = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const offset = month.getDay();
  const shift = amount => setMonth(new Date(month.getFullYear(), month.getMonth() + amount, 1));
  const today = () => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); setSelected(new Date(d.getFullYear(), d.getMonth(), d.getDate())); };
  const formatTime = value => new Date(value).toLocaleString("en-BD", { dateStyle: "medium", timeStyle: "short" });
  return <section className="od-panel">
    <div className="od-panel-heading od-calendar-heading"><div><h2>Availability calendar</h2><p className="od-muted">Pending requests hold their dates until accepted or declined.</p></div>
      <label className="od-field"><span>Property</span><select aria-label="Property" value={propertyId} onChange={e => setPropertyId(e.target.value)}><option value="">All properties</option>{properties.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label></div>
    <div className="od-calendar-toolbar"><h3>{month.toLocaleDateString("en-BD", { month: "long", year: "numeric" })}</h3><div className="od-actions">
      <button className="od-button secondary" onClick={() => shift(-1)} aria-label="Previous month">←</button><button className="od-button secondary" onClick={today}>Today</button><button className="od-button secondary" onClick={() => shift(1)} aria-label="Next month">→</button></div></div>
    <div className="od-calendar-grid">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(day => <div className="od-weekday" key={day}>{day}</div>)}
      {Array.from({ length: offset }, (_, i) => <div key={`blank-${i}`} className="od-calendar-blank" />)}
      {Array.from({ length: count }, (_, i) => {
        const date = new Date(month.getFullYear(), month.getMonth(), i + 1);
        const rows = forDay(date);
        return <button key={i} className={`od-calendar-day${date.getTime() === selected.getTime() ? " selected" : ""}${rows.length ? " occupied" : ""}`}
          onClick={() => setSelected(date)} aria-pressed={date.getTime() === selected.getTime()}
          aria-label={`${date.toLocaleDateString("en-BD", { dateStyle: "long" })}, ${rows.length ? `${rows.length} reserved` : "no bookings"}`}>
          <span>{i + 1}</span><div className="od-calendar-markers">{rows.slice(0, 3).map(b => <i key={b.id} className={b.status} />)}</div>
          <small>{rows.length ? `${rows.length} reserved` : ""}</small>
        </button>;
      })}</div>
    <div className="od-calendar-legend"><span><i className="confirmed" />Confirmed</span><span><i className="pending" />Pending hold</span></div>
    <div className="od-day-agenda"><h3>{selected.toLocaleDateString("en-BD", { weekday: "long", month: "long", day: "numeric" })}</h3>
      {!forDay(selected).length && <p className="od-muted">No booking holds on this day. Published rental listings can receive requests.</p>}
      {forDay(selected).map(b => <div className="od-agenda-row" key={b.id}><div><strong>{names[b.property_id]}</strong><p>{b.renter_name} · {formatTime(b.check_in)} → {formatTime(b.check_out)}</p></div><span className={`od-badge ${b.status}`}>{b.status}</span></div>)}
    </div>
  </section>;
}
