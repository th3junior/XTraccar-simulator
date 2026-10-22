from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TrafficProfile(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HEAVY = "heavy"


TRAFFIC_PROFILE_PARAMS: dict[TrafficProfile, dict[str, float]] = {
    TrafficProfile.LOW: {
        "junction_stop_probability": 0.15,
        "speed_factor": 1.05,
        "congestion_stop_probability": 0.02,
    },
    TrafficProfile.NORMAL: {
        "junction_stop_probability": 0.35,
        "speed_factor": 1.0,
        "congestion_stop_probability": 0.05,
    },
    TrafficProfile.HEAVY: {
        "junction_stop_probability": 0.55,
        "speed_factor": 0.75,
        "congestion_stop_probability": 0.12,
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRACCAR_SIM_", extra="ignore")

    traccar_url: str = "http://127.0.0.1:5055/"
    device_id: str = "DEVICE001"
    interval_seconds: float = Field(default=5.0, ge=1.0, le=3600.0)
    interval_ignition_on: float = Field(default=5.0, ge=1.0, le=3600.0)
    interval_ignition_off: float = Field(default=60.0, ge=1.0, le=3600.0)
    osrm_base_url: str = "https://router.project-osrm.org"
    traffic_profile: TrafficProfile = TrafficProfile.NORMAL
    default_lat: float = -22.7487
    default_lon: float = -48.5837
    send_while_paused: bool = False
    odometer_base_km: float = Field(default=0.0, ge=0.0)
    # Torre GSM/LTE (Brasil: MCC 724) — exibido no Traccar como MCC/MNC/LAC/CID
    cell_mcc: int = Field(default=724, ge=1, le=999)
    cell_mnc: int = Field(default=5, ge=0, le=999)
    cell_lac: int = Field(default=43714, ge=0)
    cell_cid: int = Field(default=45086, ge=0)
    # MAC Wi‑Fi opcional (formato AA:BB:CC:DD:EE:FF); vazio = não envia wifi=
    cell_wifi_mac: str = ""
    driver_unique_id: str = ""
    map_style: Literal["osm", "hot"] = "osm"
    config_file: Path | None = None

    @property
    def odometer_base_m(self) -> float:
        return self.odometer_base_km * 1000.0

    def apply_yaml(self, path: Path) -> None:
        if not path.is_file():
            return
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in data.items():
            if hasattr(self, key):
                if key == "traffic_profile" and isinstance(value, str):
                    setattr(self, key, TrafficProfile(value.lower()))
                else:
                    setattr(self, key, value)
        if "interval_seconds" in data and "interval_ignition_on" not in data:
            self.interval_ignition_on = float(data["interval_seconds"])
        if self.interval_ignition_on and not self.interval_seconds:
            self.interval_seconds = self.interval_ignition_on


SETTINGS_YAML_KEYS = (
    "traccar_url",
    "device_id",
    "interval_ignition_on",
    "interval_ignition_off",
    "interval_seconds",
    "osrm_base_url",
    "traffic_profile",
    "default_lat",
    "default_lon",
    "send_while_paused",
    "odometer_base_km",
    "cell_mcc",
    "cell_mnc",
    "cell_lac",
    "cell_cid",
    "cell_wifi_mac",
    "driver_unique_id",
    "map_style",
)


def save_settings_yaml(settings: Settings, path: Path | None = None) -> Path:
    target = path or Path("config.yaml")
    data: dict[str, object] = {}
    for key in SETTINGS_YAML_KEYS:
        val = getattr(settings, key, None)
        if key == "traffic_profile" and hasattr(val, "value"):
            val = val.value
        data[key] = val
    target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target


def load_settings() -> Settings:
    settings = Settings()
    env_file = settings.config_file
    candidates = [
        env_file,
        Path("config.yaml"),
        Path("config.example.yaml"),
    ]
    for path in candidates:
        if path and path.is_file():
            settings.apply_yaml(path)
            break
    return settings
