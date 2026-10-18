import { useState } from "react";
import { useAuth } from "./AuthContext";
import "./Auth.css";

export default function AuthModal({ mode: initialMode = "login", role: initialRole = "renter", reason, onClose }) {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState(initialMode);
  const [form, setForm] = useState({ email: "", password: "", name: "", phone: "", role: initialRole });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (e) => setForm((p) => ({ ...p, [e.target.name]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") await login(form.email, form.password);
      else await signup({ ...form, phone: form.phone || null });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-overlay" onClick={onClose}>
      <div className="auth-box" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <button className="auth-close" onClick={onClose} aria-label="Close">✕</button>
        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Log in</button>
          <button className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")}>Sign up</button>
        </div>
        {reason && <p className="auth-reason">{reason}</p>}
        <form onSubmit={handleSubmit} className="auth-form">
          {mode === "signup" && (
            <>
              <div className="auth-roles">
                {[["renter", "I'm looking for a place"], ["owner", "I'm listing a property"]].map(([r, label]) => (
                  <label key={r} className={form.role === r ? "active" : ""}>
                    <input type="radio" name="role" value={r} checked={form.role === r} onChange={set} />
                    {label}
                  </label>
                ))}
              </div>
              <input name="name" value={form.name} onChange={set} placeholder="Full name" required minLength={2} />
              <input name="phone" value={form.phone} onChange={set} placeholder="Phone (01XXXXXXXXX)" minLength={11} />
            </>
          )}
          <input name="email" type="email" value={form.email} onChange={set} placeholder="Email" required autoFocus />
          <input name="password" type="password" value={form.password} onChange={set}
                 placeholder="Password" required minLength={mode === "signup" ? 8 : 1} />
          {error && <div className="auth-error">{error}</div>}
          <button type="submit" className="auth-submit" disabled={busy}>
            {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
          </button>
        </form>
      </div>
    </div>
  );
}
