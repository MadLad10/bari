// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("../api", () => ({ getAvailability: vi.fn(async () => []), quoteBooking: vi.fn(), createBooking: vi.fn() }));
vi.mock("../auth/AuthContext", () => {
  const user = { name: "Rafi", phone: "01811000000" };
  return { useAuth: () => ({ user, openAuth: vi.fn() }) };
});
import { createBooking, quoteBooking } from "../api";
import BookingPanel from "../components/BookingPanel";

beforeEach(() => {
  quoteBooking.mockResolvedValue({ total_price: 2350 });
  createBooking.mockResolvedValue({ id: 7, status: "pending", total_price: 2350, check_in: "2027-01-01", check_out: "2027-01-03" });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("BookingPanel authoritative quotes and booking status", () => {
  it("uses the server price and displays a pending request without claiming confirmation", async () => {
    render(<BookingPanel property={{ id: 3, price: 1000, rental_type: "daily", listing_type: "rent" }} />);
    await screen.findByText("৳2,350");
    expect(quoteBooking).toHaveBeenCalledWith(expect.objectContaining({ property_id: 3, rental_type: "daily" }));
    expect(new Date(quoteBooking.mock.calls[0][0].check_in).getTime()).toBeGreaterThan(Date.now());
    fireEvent.click(screen.getByRole("button", { name: "Request booking" }));
    await screen.findByRole("heading", { name: "Booking request received" });
    expect(screen.queryByRole("heading", { name: /booking confirmed/i })).toBeNull();
    expect(screen.getByText("Your request is pending confirmation.")).toBeTruthy();
  });

  it("prevents submission when no valid quote is available", async () => {
    quoteBooking.mockRejectedValue(new Error("Property is already booked for the selected dates"));
    render(<BookingPanel property={{ id: 3, price: 1000, rental_type: "daily", listing_type: "rent" }} />);
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Request booking" }).disabled).toBe(true);
    expect(createBooking).not.toHaveBeenCalled();
  });
});
