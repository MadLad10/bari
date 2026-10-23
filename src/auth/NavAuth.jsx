import { Link } from "react-router-dom";
import { useAuth } from "./AuthContext";
import "./Auth.css";

export default function NavAuth() {
  const { user, ready, logout, openAuth } = useAuth();
  if (!ready) return null;
  if (!user) {
    return <button className="nav-auth-btn" onClick={() => openAuth()}>Log in</button>;
  }
  return (
    <div className="nav-auth">
      <Link to="/my-bookings" className="nav-auth-link">My bookings</Link>
      <Link to="/my-reports" className="nav-auth-link">My reports</Link>
      <Link to="/scout" className="nav-auth-link">Scout</Link>
      {user.role === "owner" && <Link to="/owner" className="nav-auth-link">Owner dashboard</Link>}
      {user.role === "admin" && <Link to="/admin" className="nav-auth-link">Admin</Link>}
      <span className="nav-auth-name" title={`${user.email} · ${user.role}`}>
        {user.name.split(" ")[0]} <em>{user.role}</em>
      </span>
      <button className="nav-auth-btn" onClick={logout}>Log out</button>
    </div>
  );
}
