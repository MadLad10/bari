import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import App from "./App";
import Browse from "./pages/Browse";
import PropertyDetail from "./pages/PropertyDetail";
import ListProperty from "./pages/ListProperty";
import Forum from "./pages/Forum";
import Admin from "./pages/Admin";
import Scout from "./pages/Scout";
import MyListings from "./pages/MyListings";
import OwnerDashboard from "./pages/OwnerDashboard";
import MyBookings from "./pages/MyBookings";
import BookingDetail from "./pages/BookingDetail";
import Reports from "./pages/Reports";
import { AuthProvider } from "./auth/AuthContext";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/browse" element={<Browse />} />
        <Route path="/property/:id" element={<PropertyDetail />} />
        <Route path="/list-property" element={<ListProperty />} />
        <Route path="/forum" element={<Forum />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/scout" element={<Scout />} />
        <Route path="/my-listings" element={<MyListings />} />
        <Route path="/owner" element={<OwnerDashboard />} />
        <Route path="/owner-dashboard" element={<OwnerDashboard />} />
        <Route path="/my-bookings" element={<MyBookings />} />
        <Route path="/bookings/:id" element={<BookingDetail />} />
        <Route path="/bookings/:id/cancel" element={<BookingDetail cancel />} />
        <Route path="/my-reports" element={<Reports />} />
        <Route path="/reports/new" element={<Reports create />} />
        <Route path="/reports/:id" element={<Reports />} />
      </Routes>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
