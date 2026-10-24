// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
vi.mock("../api", () => ({ fetchProperties: vi.fn(), countProperties: vi.fn(), fetchPropertyMap: vi.fn() }));
vi.mock("../components/AIAssistant", () => ({ default: () => null }));
vi.mock("../auth/NavAuth", () => ({ default: () => null }));
vi.mock("../components/OwnerPhotos", () => ({ photoUrl: u => u }));
vi.mock("../components/GeoMap", () => ({ default: ({ points }) => <div data-testid="pins">{points.map(p => p.id).join(",")}</div> }));
import * as api from "../api";
import Browse from "../pages/Browse";

const row = id => ({ id, title: `Apartment ${id}`, property_type: "apartment", listing_type: "rent", rental_type: "daily", furnishing: "furnished", area: "Dhanmondi", city: "Dhaka", price: 1000, bedrooms: 1, bathrooms: 1, safety_score: 4, photos: [] });
function History() { const location = useLocation(), navigate = useNavigate(); return <><output data-testid="url">{location.search}</output><button onClick={() => navigate(-1)}>Browser back</button></>; }
const mount = (path = "/browse") => render(<MemoryRouter initialEntries={[path]}><Browse /><History /></MemoryRouter>);
beforeEach(() => { api.fetchProperties.mockImplementation(async params => [row(Number(params.skip) + 1)]); api.countProperties.mockResolvedValue({ count: 45 }); });
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("paginates using the filtered total and restores the previous page with browser back", async () => {
  mount();
  await screen.findByText("1-20 of 45 listings");
  fireEvent.click(screen.getByRole("button", { name: "Next", exact: true }));
  await screen.findByText("21-40 of 45 listings");
  expect(api.fetchProperties).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 20, limit: 20 }));
  fireEvent.click(screen.getByRole("button", { name: "Browser back" }));
  await screen.findByText("1-20 of 45 listings");
  expect(screen.getByTestId("url").textContent).toBe("");
});

it("applies safety, distance and rental period together and resets pagination", async () => {
  mount("/browse?page=2");
  await screen.findByText("21-40 of 45 listings");
  fireEvent.change(screen.getByLabelText("Minimum safety rating"), { target: { value: "4" } });
  fireEvent.change(screen.getByLabelText("Maximum campus distance (km)"), { target: { value: "1.5" } });
  fireEvent.change(screen.getByLabelText("Rental period"), { target: { value: "daily" } });
  fireEvent.click(screen.getByRole("button", { name: "Apply", exact: true }));
  await vi.waitFor(() => expect(api.fetchProperties).toHaveBeenLastCalledWith(expect.objectContaining({ min_safety_score: "4", max_university_distance_km: "1.5", rental_type: "daily", skip: 0 })));
  expect(screen.getByTestId("url").textContent).not.toContain("page=");
  fireEvent.click(screen.getByRole("button", { name: "Reset", exact: true }));
  await vi.waitFor(() => expect(api.countProperties).toHaveBeenLastCalledWith(expect.objectContaining({ min_safety_score: "", max_university_distance_km: "", rental_type: "" })));
});

it("shows all matching map pins and reports listings without coordinates", async () => {
  api.fetchPropertyMap.mockResolvedValue({ total: 45, located: 2, missing_coordinates: 43, items: [row(1), row(31)] });
  mount("/browse?view=map&min_safety_score=4");
  expect((await screen.findByTestId("pins")).textContent).toBe("1,31");
  expect(screen.getByText(/43 matching listings have no map pin/)).toBeTruthy();
  expect(api.fetchPropertyMap).toHaveBeenCalledWith(expect.objectContaining({ min_safety_score: "4" }));
});
