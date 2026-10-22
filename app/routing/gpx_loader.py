from __future__ import annotations

import io

import gpxpy
import gpxpy.gpx

from app.routing.polyline import PolylineRoute


def load_gpx(data: bytes, *, default_speed_kmh: float = 60.0) -> PolylineRoute:
    gpx = gpxpy.parse(io.BytesIO(data))
    points: list[tuple[float, float]] = []
    altitudes: list[float] = []

    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append((pt.latitude, pt.longitude))
                altitudes.append(pt.elevation if pt.elevation is not None else 650.0)

    if not points:
        for wp in gpx.waypoints:
            points.append((wp.latitude, wp.longitude))
            altitudes.append(wp.elevation if wp.elevation is not None else 650.0)

    if len(points) < 2:
        raise ValueError("GPX não contém track com pelo menos 2 pontos")

    alt_for_route = altitudes[: len(points) - 1] if len(altitudes) >= len(points) - 1 else None

    return PolylineRoute.from_points(
        points,
        default_speed_kmh=default_speed_kmh,
        altitudes=alt_for_route,
        source="gpx",
        min_point_spacing_m=5.0,
    )
