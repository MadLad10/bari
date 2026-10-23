// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../api", () => ({ API_ROOT: "", fetchMyProperties: vi.fn(), fetchOwnerBookings: vi.fn(), fetchOwnerInbox: vi.fn(), acceptBooking: vi.fn(), declineBooking: vi.fn(), cancelBooking: vi.fn(), updateProperty: vi.fn(), deleteProperty: vi.fn() }));
vi.mock("../auth/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../components/VerificationPanel", () => ({ default: ({ propertyId }) => <div>Private documents for {propertyId}</div> }));
vi.mock("../components/OwnerPhotos", () => ({ default: () => <div>Photo manager</div>, photoUrl: u => u }));
vi.mock("../components/Conversation", () => ({ default: ({ propertyId, sessionToken }) => <div data-testid="active-conversation">{propertyId}:{sessionToken}</div> }));
import * as api from "../api";
import { useAuth } from "../auth/AuthContext";
import OwnerDashboard from "../pages/OwnerDashboard";
import OwnerPropertyEditor from "../components/OwnerPropertyEditor";
import OwnerCalendar from "../components/OwnerCalendar";

const property = { id: 4, title: "Furnished room in Gulshan", description: "A comfortable apartment close to campus with plenty of natural light.", area: "Gulshan", address: "House 12, Road 3, Gulshan", city: "Dhaka", property_type: "room", listing_type: "rent", rental_type: "daily", furnishing: "furnished", price: 1500, bedrooms: 1, bathrooms: 1, photos: [], amenities: ["WiFi"], status: "active", document_check_status: "reviewed", owner_name: "Karim", owner_phone: "01711000000", owner_email: "karim@example.com", is_female_only: false, has_furniture_for_sale: false };
const booking = { id: 8, property_id: 4, renter_name: "Rafi", renter_phone: "01811000000", check_in: "2028-01-08T10:00:00Z", check_out: "2028-01-09T10:00:00Z", status: "pending", total_price: 1500 };
const mount = path => render(<MemoryRouter initialEntries={[path]}><OwnerDashboard /></MemoryRouter>);

beforeEach(() => {
  useAuth.mockReturnValue({ user: { id: 2, name: "Karim Owner", role: "owner" }, ready: true, logout: vi.fn(), openAuth: vi.fn() });
  api.fetchMyProperties.mockResolvedValue([{ ...property }]);
  api.fetchOwnerBookings.mockResolvedValue([{ ...booking }]);
  api.fetchOwnerInbox.mockResolvedValue([]);
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("accepts a pending booking and refreshes its status from the server", async () => {
  api.acceptBooking.mockImplementation(async () => api.fetchOwnerBookings.mockResolvedValue([{ ...booking, status: "confirmed" }]));
  mount("/owner?tab=bookings");
  fireEvent.click(await screen.findByRole("button", { name: "Accept request" }));
  await screen.findByText(/Booking accepted/);
  expect(api.acceptBooking).toHaveBeenCalledWith(8);
  fireEvent.click(screen.getByRole("button", { name: "Confirmed" }));
  expect(await screen.findByRole("button", { name: "Cancel booking" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Accept request" })).toBeNull();
});

it("rejects an incoming request and shows the owner decision in history", async () => {
  api.declineBooking.mockImplementation(async () => api.fetchOwnerBookings.mockResolvedValue([{ ...booking, status: "cancelled", cancellation_reason: "owner_declined" }]));
  mount("/owner?tab=bookings");
  fireEvent.click(await screen.findByRole("button", { name: "Reject request" }));
  await screen.findByText(/Request rejected/);
  expect(api.declineBooking).toHaveBeenCalledWith(8);
  fireEvent.click(screen.getByRole("button", { name: "Rejected / cancelled" }));
  expect(await screen.findByText("Rejected", { exact: true })).toBeTruthy();
});

it("opens separate renter conversations for the same property", async () => {
  api.fetchOwnerInbox.mockResolvedValue([
    { property_id: 4, property_title: property.title, session_token: "user-11", renter_name: "First Renter", last_message: "First private question", last_sender: "renter", updated_at: "2026-10-24T10:00:00Z" },
    { property_id: 4, property_title: property.title, session_token: "user-12", renter_name: "Second Renter", last_message: "Second private question", last_sender: "renter", updated_at: "2026-10-24T11:00:00Z" },
  ]);
  mount("/owner?tab=messages");
  expect((await screen.findByTestId("active-conversation")).textContent).toBe("4:user-11");
  fireEvent.click(screen.getByRole("button", { name: /Second Renter/ }));
  expect(screen.getByTestId("active-conversation").textContent).toBe("4:user-12");
  fireEvent.click(screen.getByRole("button", { name: /First Renter/ }));
  expect(screen.getByTestId("active-conversation").textContent).toBe("4:user-11");
});

it("filters properties and opens the selected property's private document checks", async () => {
  mount("/owner?tab=listings");
  await screen.findByRole("heading", { name: property.title });
  const search = screen.getByRole("textbox", { name: "Search your properties" });
  fireEvent.change(search, { target: { value: "Mirpur" } });
  expect(screen.getByText("No matching properties")).toBeTruthy();
  fireEvent.change(search, { target: { value: "Gulshan" } });
  fireEvent.click(screen.getByRole("button", { name: /Admin approved/ }));
  expect(await screen.findByText("Private documents for 4")).toBeTruthy();
});

it("keeps renter accounts out of the owner data requests", async () => {
  useAuth.mockReturnValue({ user: { id: 9, name: "Renter", role: "renter" }, ready: true });
  mount("/owner");
  expect(screen.getByText("This dashboard is for property owner accounts.")).toBeTruthy();
  expect(api.fetchMyProperties).not.toHaveBeenCalled();
  expect(api.fetchOwnerBookings).not.toHaveBeenCalled();
  expect(api.fetchOwnerInbox).not.toHaveBeenCalled();
});

it("shows an actionable empty state for an owner with no listings", async () => {
  api.fetchMyProperties.mockResolvedValue([]);
  api.fetchOwnerBookings.mockResolvedValue([]);
  mount("/owner?tab=listings");
  expect(await screen.findByText("Make room for your first listing")).toBeTruthy();
  expect(screen.getByRole("link", { name: /List a property to get started/ }).getAttribute("href")).toBe("/list-property");
});

it("sends only changed fields when an owner edits a price", async () => {
  const saved = vi.fn(); const closed = vi.fn();
  api.updateProperty.mockResolvedValue({ ...property, price: 2000 });
  render(<OwnerPropertyEditor property={property} onSaved={saved} onClose={closed} />);
  fireEvent.change(screen.getByLabelText("Price per rental period (BDT)"), { target: { value: "2000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await vi.waitFor(() => expect(closed).toHaveBeenCalled());
  expect(api.updateProperty).toHaveBeenCalledWith(4, { price: 2000 });
  expect(saved).toHaveBeenCalled();
});

it("calendar excludes a checkout at midnight from the following day", () => {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 8);
  const end = new Date(now.getFullYear(), now.getMonth(), 9);
  render(<OwnerCalendar properties={[property]} bookings={[{ ...booking, check_in: start.toISOString(), check_out: end.toISOString() }]} />);
  const buttons = screen.getAllByRole("button");
  const eighth = buttons.find(b => b.getAttribute("aria-label")?.includes("8,") && b.getAttribute("aria-label")?.includes("1 reserved"));
  const ninth = buttons.find(b => b.getAttribute("aria-label")?.includes("9,") && b.getAttribute("aria-label")?.includes("no bookings"));
  expect(eighth).toBeTruthy(); expect(ninth).toBeTruthy();
  fireEvent.click(eighth);
  expect(within(document.querySelector(".od-day-agenda")).getByText(property.title)).toBeTruthy();
  fireEvent.click(ninth);
  expect(screen.getByText(/No booking holds on this day/)).toBeTruthy();
});
