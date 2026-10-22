from __future__ import annotations

from datetime import datetime, timezone


def trail_to_gpx(trail: list[tuple[float, float]], *, name: str = "XTraccar Simulator") -> str:
    """Gera GPX 1.1 a partir de trilha (lat, lon)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="xtraccar-simulator" '
        'xmlns="http://www.topografix.com/GPX/1/1">',
        f"  <metadata><name>{name}</name><time>{now}</time></metadata>",
        "  <trk>",
        f"    <name>{name}</name>",
        "    <trkseg>",
    ]
    for lat, lon in trail:
        lines.append(f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}"></trkpt>')
    lines.extend(["    </trkseg>", "  </trk>", "</gpx>"])
    return "\n".join(lines)
