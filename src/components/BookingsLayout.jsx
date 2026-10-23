import { Link } from "react-router-dom";
import NavAuth from "../auth/NavAuth";
import "../pages/MyBookings.css";

export default function BookingsLayout({ children }) {
  return <div className="mb-layout">
    <header className="mb-header"><Link to="/" className="mb-logo">bari<span>.com</span></Link><NavAuth /></header>
    <main className="mb-main">{children}</main>
    <footer className="mb-footer"><Link to="/">bari.com</Link><span>A better place to call home.</span><Link to="/browse">Find a place ↗</Link></footer>
  </div>;
}
