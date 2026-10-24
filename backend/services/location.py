"""Cached OpenStreetMap places and OSRM driving routes; never invent locations or distances."""
import math
import threading
import time
from datetime import datetime, timezone

import httpx

from config import settings
from services.errors import BadRequest, ServiceError

ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
HEADERS = {"User-Agent": "bari-local-map/1.0 (+https://github.com/RafiALMahmud/bari.com)"}
_cache = {}
_lock = threading.Lock()
_last_request = 0.0
_cooldown = 0.0


class LocationUnavailable(ServiceError):
    status_code = 503


def coordinates(prop):
    if prop.latitude is None or prop.longitude is None:
        raise BadRequest("This listing has no map pin. Its owner must add coordinates before nearby distances can be calculated.")
    return float(prop.latitude), float(prop.longitude)


def distance_m(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlng = lat2 - lat1, math.radians(b[1] - a[1])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(value)))


def _request_json(key, ttl, method, url, **kwargs):
    global _last_request, _cooldown
    entry = _cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    # One external lookup at a time, bounded cache, no retry storms against community services.
    if not _lock.acquire(blocking=False):
        raise LocationUnavailable("The map service is busy. Please try again shortly.")
    try:
        entry = _cache.get(key)
        if entry and entry[0] > time.monotonic():
            return entry[1]
        if time.monotonic() < _cooldown:
            raise LocationUnavailable("The map provider is temporarily unavailable. Try again in a minute.")
        time.sleep(max(0, 1.1 - (time.monotonic() - _last_request)))
        _last_request = time.monotonic()
        try:
            with httpx.Client(timeout=20, headers=HEADERS) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict) or data.get("remark"):
                raise ValueError("Incomplete provider result")
        except (httpx.HTTPError, ValueError):
            _cooldown = time.monotonic() + 60
            raise LocationUnavailable("Nearby places or routes could not be loaded from the map provider. Try again later.") from None
        if len(_cache) >= 256:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (time.monotonic() + ttl, data)
        return data
    finally:
        _lock.release()


def nearby(prop):
    lat, lng = coordinates(prop)
    query = (f'[out:json][timeout:15];(nwr(around:3000,{lat:.6f},{lng:.6f})[amenity=hospital];'
             f'nwr(around:3000,{lat:.6f},{lng:.6f})[highway=bus_stop];'
             f'nwr(around:3000,{lat:.6f},{lng:.6f})[public_transport=platform][bus=yes];'
             f'nwr(around:3000,{lat:.6f},{lng:.6f})[amenity=marketplace];'
             f'nwr(around:3000,{lat:.6f},{lng:.6f})[shop=supermarket];);out center tags;')
    data = (_photon_places(lat, lng) if settings.places_provider == "photon" else
            _request_json(("nearby", lat, lng, settings.places_api_url), 86400, "POST", settings.places_api_url, data={"data": query}))
    categories = {"hospital": [], "bus_stop": [], "market": []}
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        center = element.get("center", element)
        if center.get("lat") is None or center.get("lon") is None:
            continue
        point = (float(center["lat"]), float(center["lon"]))
        distance = distance_m((lat, lng), point)
        if distance > 3000:
            continue
        kind = "hospital" if tags.get("amenity") == "hospital" else "bus_stop" if (
            tags.get("highway") == "bus_stop" or tags.get("public_transport") == "platform" and tags.get("bus") == "yes") else "market"
        name = tags.get("name") or tags.get("name:en") or tags.get("name:bn") or {"hospital": "Unnamed hospital", "bus_stop": "Unnamed bus stop", "market": "Unnamed market / supermarket"}[kind]
        categories[kind].append({"id": f"{element['type']}/{element['id']}", "name": name,
                                 "latitude": point[0], "longitude": point[1], "distance_m": round(distance),
                                 "osm_url": f"https://www.openstreetmap.org/{element['type']}/{element['id']}"})
    for key in categories:
        categories[key] = sorted(categories[key], key=lambda item: (item["distance_m"], item["id"]))[:5]
    return {"property_id": prop.id, "origin": {"latitude": lat, "longitude": lng}, "radius_m": 3000,
            "distance_type": "straight_line", "categories": categories, "source": ATTRIBUTION,
            "retrieved_at": datetime.now(timezone.utc).isoformat()}


def _photon_places(lat, lng):
    # Filter by actual OSM categories and a bounding box, rather than searching English names.
    dlat = 3000 / 111000
    dlng = min(180, dlat / max(.01, abs(math.cos(math.radians(lat)))))
    bbox = f"{max(-180, lng-dlng)},{max(-90, lat-dlat)},{min(180, lng+dlng)},{min(90, lat+dlat)}"
    groups = (("amenity.hospital",), ("highway.bus_stop",), ("amenity.marketplace", "shop.supermarket"))
    elements = {}
    for group in groups:
        params = [("include", ",".join("osm." + category for category in group))]
        params += [("lat", lat), ("lon", lng), ("bbox", bbox), ("limit", 15), ("location_bias_scale", 0)]
        data = _request_json(("photon", lat, lng, group, settings.photon_api_url), 86400, "GET", settings.photon_api_url, params=params)
        if not isinstance(data.get("features"), list):
            raise LocationUnavailable("The places provider returned an incomplete result")
        for feature in data["features"]:
            tags, geometry = feature.get("properties", {}), feature.get("geometry", {})
            kind = {"N": "node", "W": "way", "R": "relation"}.get(tags.get("osm_type"))
            point = geometry.get("coordinates", [])
            if not kind or not tags.get("osm_id") or geometry.get("type") != "Point" or len(point) < 2:
                continue
            key, value = tags.get("osm_key"), tags.get("osm_value")
            if f"{key}.{value}" not in group:
                continue
            identifier = (kind, tags["osm_id"])
            elements[identifier] = {"type": kind, "id": tags["osm_id"], "lon": point[0], "lat": point[1],
                                    "tags": {key: value, "name": tags.get("name")}}
    return {"elements": list(elements.values())}


def route(prop, destination_id):
    lat, lng = coordinates(prop)
    # Restrict destinations to actual nearby results. Clients cannot turn this into an arbitrary proxy.
    places = nearby(prop)
    place = next((p for group in places["categories"].values() for p in group if p["id"] == destination_id), None)
    if not place:
        raise BadRequest("Choose a destination from this listing's nearby places")
    endlat, endlng = place["latitude"], place["longitude"]
    url = f"{settings.routing_api_url.rstrip('/')}/route/v1/driving/{lng},{lat};{endlng},{endlat}"
    data = _request_json(("route", lat, lng, endlat, endlng, settings.routing_api_url), 3600, "GET", url,
                         params={"overview": "full", "geometries": "geojson", "steps": "false", "alternatives": "false"})
    routes = data.get("routes", [])
    if data.get("code") != "Ok" or not routes:
        raise LocationUnavailable("No driving route was found for this destination. Straight-line distances remain available.")
    result = routes[0]
    geometry = result.get("geometry", {})
    if geometry.get("type") != "LineString" or not geometry.get("coordinates"):
        raise LocationUnavailable("The provider did not return a usable route")
    return {"destination": place, "mode": "driving", "distance_m": round(result["distance"]),
            "duration_s": round(result["duration"]), "geometry": geometry, "source": "OSRM · " + ATTRIBUTION,
            "traffic_included": False}
