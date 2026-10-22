from __future__ import annotations

import math
from dataclasses import dataclass, field


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


@dataclass
class PolylineRoute:
    """Rota como sequência de pontos com distâncias acumuladas e metadados por segmento."""

    points: list[tuple[float, float]]  # (lat, lon)
    cumulative_dist: list[float] = field(default_factory=list)
    segment_speed_kmh: list[float] = field(default_factory=list)
    stop_distances: list[float] = field(default_factory=list)
    altitudes: list[float] | None = None
    source: str = "unknown"

    @property
    def total_length_m(self) -> float:
        if not self.cumulative_dist:
            return 0.0
        return self.cumulative_dist[-1]

    @classmethod
    def from_points(
        cls,
        points: list[tuple[float, float]],
        *,
        default_speed_kmh: float = 60.0,
        stop_distances: list[float] | None = None,
        segment_speeds: list[float] | None = None,
        altitudes: list[float] | None = None,
        source: str = "points",
        min_point_spacing_m: float = 5.0,
    ) -> PolylineRoute:
        if len(points) < 2:
            raise ValueError("Rota precisa de pelo menos 2 pontos")

        simplified: list[tuple[float, float]] = [points[0]]
        for pt in points[1:]:
            if haversine_m(simplified[-1][0], simplified[-1][1], pt[0], pt[1]) >= min_point_spacing_m:
                simplified.append(pt)
            elif pt != simplified[-1]:
                simplified[-1] = pt

        if len(simplified) < 2:
            simplified = [points[0], points[-1]]

        cum: list[float] = [0.0]
        speeds: list[float] = []
        for i in range(len(simplified) - 1):
            d = haversine_m(
                simplified[i][0],
                simplified[i][1],
                simplified[i + 1][0],
                simplified[i + 1][1],
            )
            cum.append(cum[-1] + d)
            if segment_speeds and i < len(segment_speeds):
                speeds.append(segment_speeds[i])
            else:
                speeds.append(default_speed_kmh)

        return cls(
            points=simplified,
            cumulative_dist=cum,
            segment_speed_kmh=speeds,
            stop_distances=stop_distances or [],
            altitudes=altitudes,
            source=source,
        )

    def sample_at_distance(self, distance_m: float) -> tuple[float, float, float, float, int]:
        """
        Retorna lat, lon, bearing, speed_kmh alvo, índice do segmento.
        distance_m é clamped entre 0 e total_length.
        """
        total = self.total_length_m
        if total <= 0:
            lat, lon = self.points[0]
            return lat, lon, 0.0, self.segment_speed_kmh[0] if self.segment_speed_kmh else 0.0, 0

        d = max(0.0, min(distance_m, total))

        seg = 0
        for i in range(len(self.cumulative_dist) - 1):
            if self.cumulative_dist[i + 1] >= d:
                seg = i
                break
        else:
            seg = len(self.points) - 2

        seg_start = self.cumulative_dist[seg]
        seg_end = self.cumulative_dist[seg + 1]
        lat1, lon1 = self.points[seg]
        lat2, lon2 = self.points[seg + 1]

        if seg_end <= seg_start:
            brg = bearing_deg(lat1, lon1, lat2, lon2) if (lat1, lon1) != (lat2, lon2) else 0.0
            spd = self.segment_speed_kmh[seg] if seg < len(self.segment_speed_kmh) else 60.0
            return lat1, lon1, brg, spd, seg

        t = (d - seg_start) / (seg_end - seg_start)
        lat = lat1 + (lat2 - lat1) * t
        lon = lon1 + (lon2 - lon1) * t
        brg = bearing_deg(lat1, lon1, lat2, lon2)
        spd = self.segment_speed_kmh[seg] if seg < len(self.segment_speed_kmh) else 60.0
        return lat, lon, brg, spd, seg

    def altitude_at_segment(self, seg: int) -> float:
        if self.altitudes and seg < len(self.altitudes):
            return self.altitudes[seg]
        return 650.0

    def to_geojson(self) -> dict:
        return {
            "type": "Feature",
            "properties": {"source": self.source, "length_m": self.total_length_m},
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in self.points],
            },
        }
