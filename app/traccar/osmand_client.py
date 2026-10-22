from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings


@dataclass
class SendResult:
    ok: bool
    status_code: int | None
    error: str | None = None


class OsmAndClient:
    def __init__(self) -> None:
        self.last_result: SendResult | None = None
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def speed_to_knots(kmh: float) -> float:
        return round(max(0.0, kmh) / 1.852, 2)

    async def send(
        self,
        *,
        settings: Settings,
        lat: float,
        lon: float,
        speed_kmh: float,
        bearing: float,
        altitude: float,
        accuracy: float,
        batt: int,
        ignition: bool,
        motion: bool,
        power: float,
        sat: int,
        blocked: bool = False,
        alarm: str | None = None,
        rssi: int | None = None,
        hdop: float | None = None,
        charge: bool = False,
        cell: str | None = None,
        wifi: str | None = None,
        odometer_m: int | None = None,
        driver_unique_id: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> SendResult:
        base = settings.traccar_url.rstrip("/") + "/"
        params: dict[str, Any] = {
            "id": settings.device_id,
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
            "speed": self.speed_to_knots(speed_kmh),
            "bearing": int(round(bearing)) % 360,
            "altitude": round(altitude, 1),
            "accuracy": accuracy,
            "batt": batt,
            "ignition": str(ignition).lower(),
            "motion": str(motion).lower(),
            "power": power,
            "sat": sat,
            "blocked": str(blocked).lower(),
            "charge": str(charge).lower(),
        }
        if alarm:
            params["alarm"] = alarm
        if rssi is not None:
            params["rssi"] = rssi
        if hdop is not None:
            params["hdop"] = hdop
        if cell:
            params["cell"] = cell
        if wifi:
            params["wifi"] = wifi
        if odometer_m is not None:
            params["odometer"] = int(odometer_m)
        if driver_unique_id:
            params["driverUniqueId"] = driver_unique_id
        if extras:
            for k, v in extras.items():
                if v is not None:
                    params[k] = v

        url = base + "?" + urlencode(params)

        try:
            resp = await self._client.get(
                url,
                headers={"User-Agent": "XTraccar-Simulator/2.1"},
            )
            result = SendResult(ok=resp.is_success, status_code=resp.status_code)
        except Exception as e:
            result = SendResult(ok=False, status_code=None, error=str(e))

        self.last_result = result
        return result
