// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
vi.mock("../api", () => ({ fetchNearby: vi.fn(), fetchRoute: vi.fn() }));
vi.mock("../components/GeoMap", () => ({ default: ({ geometry }) => <div data-testid="route-geometry">{geometry?.type}</div> }));
import * as api from "../api";
import PropertyLocation from "../components/PropertyLocation";
const prop = { id: 1, latitude: 23.75, longitude: 90.4, title: "Apartment", nearby_university: "BRAC University", university_distance_km: 1 };
const place = { id: "node/11", name: "Mapped Hospital", distance_m: 500, latitude: 23.751, longitude: 90.4, osm_url: "https://www.openstreetmap.org/node/11" };
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("distinguishes straight-line place distances from real driving routes", async () => {
  api.fetchNearby.mockResolvedValue({ categories: { hospital: [place], bus_stop: [], market: [] } });
  api.fetchRoute.mockResolvedValue({ destination: place, distance_m: 1200, duration_s: 360, geometry: { type: "LineString", coordinates: [] } });
  render(<PropertyLocation property={prop} />);
  expect(api.fetchNearby).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Find nearby places" }));
  expect(await screen.findByText("500 m straight line")).toBeTruthy();
  expect(screen.getAllByText("None mapped within 3 km")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Road route to hospital" }));
  expect(await screen.findByText("1.20 km by road · about 6 min")).toBeTruthy();
  expect(screen.getByTestId("route-geometry").textContent).toBe("LineString");
  expect(api.fetchRoute).toHaveBeenCalledWith(1, "node/11");
});

it("never invents distances when a property has no coordinates", () => {
  render(<PropertyLocation property={{ ...prop, latitude: null, longitude: null }} />);
  expect(screen.getByText(/This listing has no map pin yet/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Find nearby places" }).disabled).toBe(true);
  expect(api.fetchNearby).not.toHaveBeenCalled();
});

it("shows a retry path for a failed nearby lookup", async () => {
  api.fetchNearby.mockRejectedValue(new Error("Provider unavailable"));
  render(<PropertyLocation property={prop} />);
  fireEvent.click(screen.getByRole("button", { name: "Find nearby places" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Find nearby places" }).disabled).toBe(false);
});
