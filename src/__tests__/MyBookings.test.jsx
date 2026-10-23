// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../api", () => ({ API_ROOT: "", fetchMyBookings: vi.fn(), fetchBooking: vi.fn(), cancelBooking: vi.fn() }));
vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../auth/NavAuth", () => ({ default: () => <div>Account navigation</div> }));
import * as api from "../api";
import { useAuth } from "../auth/AuthContext";
import MyBookings from "../pages/MyBookings";
import BookingDetail from "../pages/BookingDetail";

const booking = { id: 41, property_id: 3, renter_name: "Rafi", renter_phone: "01811000000", rental_type: "daily", total_price: 3200,
  check_in: "2028-01-08T10:00:00Z", check_out: "2028-01-10T10:00:00Z", created_at: "2026-10-24T10:00:00Z", status: "confirmed",
  property: { id: 3, title: "Quiet room in Gulshan", address: "House 14, Road 2, Gulshan", area: "Gulshan", city: "Dhaka", status: "active", photos: [] } };
const mount = (path = "/my-bookings") => render(<MemoryRouter initialEntries={[path]}><Routes>
  <Route path="/my-bookings" element={<MyBookings />} /><Route path="/bookings/:id" element={<BookingDetail />} /><Route path="/bookings/:id/cancel" element={<BookingDetail cancel />} />
</Routes></MemoryRouter>);

beforeEach(() => {
  useAuth.mockReturnValue({ user: { id: 7, name: "Rafi", role: "renter" }, ready: true, openAuth: vi.fn() });
  api.fetchMyBookings.mockResolvedValue([{ ...booking }]);
  api.fetchBooking.mockResolvedValue({ ...booking });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("shows booking history and separates completed stays and owner rejections", async () => {
  api.fetchMyBookings.mockResolvedValue([
    booking,
    { ...booking, id: 42, status: "pending" },
    { ...booking, id: 43, check_in: "2020-01-01", check_out: "2020-01-03" },
    { ...booking, id: 44, status: "cancelled", cancellation_reason: "owner_declined" },
  ]);
  mount();
  await screen.findByRole("article", { name: "Booking 41" });
  expect(within(screen.getByRole("article", { name: "Booking 43" })).getByText("Completed")).toBeTruthy();
  expect(within(screen.getByRole("article", { name: "Booking 44" })).getByText("Rejected by owner")).toBeTruthy();
  expect(within(screen.getByRole("article", { name: "Booking 43" })).queryByRole("link", { name: "Cancel booking" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Cancelled & rejected" }));
  expect(screen.queryByRole("article", { name: "Booking 41" })).toBeNull();
  expect(screen.getByRole("article", { name: "Booking 44" })).toBeTruthy();
});

it("does not cancel when opening the confirmation screen or keeping the booking", async () => {
  mount("/bookings/41/cancel");
  await screen.findByRole("heading", { name: "Cancel this booking?" });
  expect(api.cancelBooking).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("link", { name: "Keep booking" }));
  await screen.findByRole("heading", { name: "Your booking" });
  expect(api.cancelBooking).not.toHaveBeenCalled();
});

it("cancels only on confirmation and shows the refreshed server status", async () => {
  api.cancelBooking.mockImplementation(async () => {
    const cancelled = { ...booking, status: "cancelled", cancellation_reason: "renter_cancelled", cancelled_at: "2026-10-24T11:00:00Z" };
    api.fetchBooking.mockResolvedValue(cancelled);
    return cancelled;
  });
  mount("/bookings/41/cancel");
  fireEvent.click(await screen.findByRole("button", { name: "Yes, cancel booking" }));
  await screen.findByRole("status", { name: "" });
  await screen.findByText("Booking cancelled. Your reserved dates have been released.");
  expect(api.cancelBooking).toHaveBeenCalledWith(41);
  expect(screen.queryByRole("link", { name: "Cancel booking" })).toBeNull();
});

it("shows an actionable cancellation error and retains the booking", async () => {
  api.cancelBooking.mockRejectedValue(new Error("Could not cancel. Try again."));
  mount("/bookings/41/cancel");
  fireEvent.click(await screen.findByRole("button", { name: "Yes, cancel booking" }));
  await screen.findByRole("alert");
  expect(screen.getByText("Could not cancel. Try again.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Yes, cancel booking" }).disabled).toBe(false);
});

it("requires login before requesting private history", () => {
  useAuth.mockReturnValue({ user: null, ready: true, openAuth: vi.fn() });
  mount();
  expect(screen.getByRole("button", { name: "Log in to view bookings" })).toBeTruthy();
  expect(api.fetchMyBookings).not.toHaveBeenCalled();
});

it("does not offer cancellation for an ended stay", async () => {
  api.fetchBooking.mockResolvedValue({ ...booking, check_in: "2020-01-01", check_out: "2020-01-03" });
  mount("/bookings/41/cancel");
  await screen.findByText("This booking cannot be cancelled.");
  expect(screen.queryByRole("button", { name: "Yes, cancel booking" })).toBeNull();
  expect(api.cancelBooking).not.toHaveBeenCalled();
});

it("reports an empty history with a link to find a property", async () => {
  api.fetchMyBookings.mockResolvedValue([]);
  mount();
  await screen.findByRole("heading", { name: "Make yourself at home." });
  expect(screen.getByRole("link", { name: "Explore properties" }).getAttribute("href")).toBe("/browse");
});
