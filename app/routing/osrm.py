from __future__ import annotations

import re
from typing import Any

import httpx

from app.routing.polyline import PolylineRoute


def _parse_maxspeed(value: str | int | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if not s or s == "none":
        return None
    m = re.match(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    speed = float(m.group(1))
    if "mph" in s:
        speed *= 1.60934
    return speed


def _heuristic_speed_kmh(step: dict[str, Any]) -> float:
    ref = (step.get("ref") or "").lower()
    if any(x in ref for x in ("sp-", "br-", "rod")):
        return 100.0
    dist = float(step.get("distance") or 0)
    dur = float(step.get("duration") or 0)
    if dur > 0 and dist > 0:
        kmh = (dist / dur) * 3.6
        if 15 <= kmh <= 130:
            return kmh
    if dist > 5000:
        return 90.0
    return 50.0


def _annotation_speeds_kmh(legs: list[dict[str, Any]]) -> list[float]:
    """Velocidades por segmento a partir das anotações OSRM (m/s → km/h)."""
    speeds_kmh: list[float] = []
    for leg in legs:
        ann = leg.get("annotation") or {}
        for mps in ann.get("speed") or []:
            try:
                v = float(mps) * 3.6
            except (TypeError, ValueError):
                v = 50.0
            speeds_kmh.append(max(15.0, min(130.0, v)))
    return speeds_kmh


async def fetch_osrm_route(
    waypoints: list[tuple[float, float]],
    *,
    base_url: str,
    client: httpx.AsyncClient | None = None,
) -> PolylineRoute:
    """waypoints: list of (lat, lon)."""
    if len(waypoints) < 2:
        raise ValueError("OSRM requer pelo menos 2 waypoints")

    coords = ";".join(f"{lon},{lat}" for lat, lon in waypoints)
    url = (
        f"{base_url.rstrip('/')}/route/v1/driving/{coords}"
        "?overview=full&geometries=geojson&steps=true&annotations=speed,distance,duration"
    )

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=60.0)

    try:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                break
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                last_error = e
                if attempt == 2:
                    raise RuntimeError(f"Falha ao consultar OSRM: {e}") from e
        else:
            raise RuntimeError(f"Falha ao consultar OSRM: {last_error}")

        if data.get("code") != "Ok" or not data.get("routes"):
            raise RuntimeError(data.get("message", "OSRM não retornou rota"))

        route = data["routes"][0]
        geom = route["geometry"]["coordinates"]
        points = [(lat, lon) for lon, lat in geom]

        legs = route.get("legs") or []
        segment_speeds = _annotation_speeds_kmh(legs)

        stop_distances: list[float] = []
        cumulative = 0.0
        for leg in legs:
            for step in leg.get("steps") or []:
                step_dist = float(step.get("distance") or 0)
                step_end = cumulative + step_dist
                ms = _parse_maxspeed(step.get("maxspeed"))
                maneuver = step.get("maneuver") or {}
                if maneuver.get("type") in (
                    "turn",
                    "roundabout",
                    "rotary",
                    "fork",
                    "merge",
                    "end of road",
                ):
                    stop_distances.append(step_end)
                elif len(step.get("intersections") or []) > 1:
                    stop_distances.append(step_end)
                if ms and ms < 40:
                    stop_distances.append(step_end)
                cumulative = step_end

        n_seg = max(1, len(points) - 1)
        if len(segment_speeds) < n_seg:
            fallback = segment_speeds[-1] if segment_speeds else 60.0
            segment_speeds.extend([fallback] * (n_seg - len(segment_speeds)))
        segment_speeds = segment_speeds[:n_seg]

        for i, step_speed in enumerate(segment_speeds):
            if step_speed < 25:
                dist_approx = (i / max(1, n_seg - 1)) * cumulative
                stop_distances.append(dist_approx)

        stop_distances = sorted(set(round(d, 1) for d in stop_distances))

        return PolylineRoute.from_points(
            points,
            segment_speeds=segment_speeds,
            stop_distances=stop_distances,
            source="osrm",
            min_point_spacing_m=3.0,
        )
    finally:
        if own_client and client:
            await client.aclose()
