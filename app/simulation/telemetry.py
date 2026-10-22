from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from app.config import Settings


def motion_from_speed(speed_kmh: float) -> bool:
    return speed_kmh > 2.0


def normalize_wifi_mac(mac: str) -> str | None:
    raw = (mac or "").strip()
    if not raw:
        return None
    parts = re.split(r"[-:]", raw)
    if len(parts) != 6:
        return None
    try:
        octets = [int(p, 16) for p in parts]
    except ValueError:
        return None
    if any(o < 0 or o > 255 for o in octets):
        return None
    return ":".join(f"{o:02X}" for o in octets)


def rssi_to_cell_signal(rssi_dbm: int) -> int:
    """Quinto campo do parâmetro OsmAnd cell (0–100, derivado do RSSI)."""
    return int(max(0, min(100, round((rssi_dbm + 110) * 100 / 60))))


def rpm_target_for_engine(*, ignition: bool, speed_kmh: float) -> float:
    """RPM simulado: 0 com motor desligado; marcha lenta parado; sobe com a velocidade."""
    if not ignition:
        return 0.0
    speed = max(0.0, speed_kmh)
    if speed <= 2.0:
        return random.uniform(740.0, 880.0)
    # Faixas aproximadas de câmbio automático / uso urbano–estrada
    if speed < 25.0:
        base = 950.0 + speed * 42.0
    elif speed < 60.0:
        base = 2000.0 + (speed - 25.0) * 28.0
    elif speed < 100.0:
        base = 2980.0 + (speed - 60.0) * 22.0
    else:
        base = 3860.0 + (speed - 100.0) * 8.0
    jitter = random.uniform(-90.0, 90.0)
    return float(max(720.0, min(4500.0, base + jitter)))


@dataclass
class DeviceTelemetry:
    """
    power  = tensão da alimentação externa do veículo (fio 12V / bateria do carro).
    batt   = bateria interna do rastreador (%).
    charge = true/false no Traccar: alimentação externa (12V) conectada = sim.
    """

    external_voltage: float = 12.80
    internal_batt_percent: float = 92.0
    external_connected: bool = True
    satellites: int = 10
    hdop: float = 0.85
    accuracy_m: float = 5.0
    rssi: int = -78
    charge: bool = True
    jamming: bool = False
    rpm: float = 0.0
    fuel_percent: float = 72.0
    door: bool = False
    in1: bool = False
    in2: bool = False
    in3: bool = False
    in4: bool = False
    mcc: int = 724
    mnc: int = 5
    lac: int = 43714
    cid: int = 45086
    wifi_mac: str | None = None
    _sat_float: float = field(default=10.0, repr=False)
    _rssi_float: float = field(default=-78.0, repr=False)
    _handover_m: float = field(default=0.0, repr=False)

    @property
    def power(self) -> float:
        return self.external_voltage

    @property
    def batt(self) -> int:
        return int(round(self.internal_batt_percent))

    @property
    def radio_label(self) -> str:
        if self.rssi >= -75:
            return "LTE"
        if self.rssi >= -90:
            return "4G"
        return "3G"

    @property
    def network_display(self) -> str:
        return f"{self.mcc}/{self.mnc} · LAC {self.lac} · CID {self.cid}"

    def sync_cell_from_settings(self, settings: Settings) -> None:
        self.mcc = int(settings.cell_mcc)
        self.mnc = int(settings.cell_mnc)
        self.lac = int(settings.cell_lac)
        self.cid = int(settings.cell_cid)
        self.wifi_mac = normalize_wifi_mac(settings.cell_wifi_mac)

    def cell_osmand_param(self) -> str:
        signal = rssi_to_cell_signal(self.rssi)
        return f"{self.mcc},{self.mnc},{self.lac},{self.cid},{signal}"

    def wifi_osmand_param(self) -> str | None:
        if not self.wifi_mac:
            return None
        return f"{self.wifi_mac},{self.rssi}"

    def apply_violation_low_battery(self) -> None:
        self.internal_batt_percent = min(self.internal_batt_percent, random.uniform(8.0, 15.0))

    def apply_violation_jamming(self) -> None:
        self.jamming = True
        self.satellites = max(3, self.satellites - 5)
        self.rssi = min(self.rssi, -95)
        self.accuracy_m = max(self.accuracy_m, 25.0)

    def clear_jamming_after(self) -> None:
        self.jamming = False

    def force_external_off(self) -> None:
        self.external_connected = False
        self.external_voltage = 0.0
        self.charge = False

    def on_external_connected(self) -> None:
        """12V reconectado — tensão sobe de imediato para faixa de bateria do carro."""
        self.external_connected = True
        self.external_voltage = round(random.uniform(12.30, 12.85), 2)
        self.charge = True

    def _target_external_voltage(self, *, ignition: bool, speed_kmh: float) -> float:
        if not self.external_connected:
            return 0.0
        moving = motion_from_speed(speed_kmh)
        if ignition:
            if speed_kmh > 80:
                return random.uniform(13.95, 14.25)
            if moving:
                return random.uniform(13.65, 14.05)
            return random.uniform(13.35, 13.75)
        if moving:
            return random.uniform(12.55, 12.95)
        return random.uniform(12.45, 12.85)

    def _maybe_cell_handover(self, *, speed_kmh: float, distance_m: float, dt: float) -> None:
        if not motion_from_speed(speed_kmh):
            return
        self._handover_m += (speed_kmh / 3.6) * dt
        if self._handover_m < 1800:
            return
        self._handover_m = 0.0
        if random.random() < 0.35:
            self.cid = max(1, self.cid + random.randint(1, 12))

    def tick(
        self,
        dt: float,
        *,
        ignition: bool,
        speed_kmh: float,
        blocked: bool,
        external_connected: bool | None = None,
        distance_m: float = 0.0,
    ) -> None:
        if external_connected is not None:
            self.external_connected = external_connected

        moving = motion_from_speed(speed_kmh)

        if not self.external_connected:
            self.external_voltage = 0.0
            self.charge = False
        else:
            if self.external_voltage < 12.30:
                self.external_voltage = round(random.uniform(12.30, 12.85), 2)
            else:
                target_v = self._target_external_voltage(ignition=ignition, speed_kmh=speed_kmh)
                target_v = max(target_v, 12.30)
                step = 0.45 if ignition else 0.2
                diff = target_v - self.external_voltage
                self.external_voltage += max(-step, min(step, diff)) * min(1.0, dt / 2.5)
                self.external_voltage = round(
                    max(12.30, self.external_voltage + random.uniform(-0.03, 0.03)),
                    2,
                )

        self.charge = self.external_connected

        if self.charge and self.internal_batt_percent < 99.5:
            rate = 0.08 if ignition else 0.05
            self.internal_batt_percent = min(100.0, self.internal_batt_percent + rate * dt)
        else:
            drain = 0.022 if moving else 0.006
            if not self.external_connected:
                drain = 0.045 if moving else 0.018
            if blocked:
                drain *= 1.25
            self.internal_batt_percent = max(3.0, self.internal_batt_percent - drain * dt)

        sky_factor = 1.15 if speed_kmh > 70 else (0.88 if speed_kmh < 25 else 1.0)
        if self.jamming:
            sky_factor *= 0.55

        sat_target = 11.5 * sky_factor
        self._sat_float += (sat_target - self._sat_float) * min(0.35, dt / 8.0)
        self._sat_float += random.uniform(-0.15, 0.15)
        self.satellites = int(max(4, min(15, round(self._sat_float))))

        self.hdop = round(
            max(0.5, min(4.5, 2.8 / (self.satellites * 0.11) + random.uniform(-0.08, 0.08))),
            2,
        )
        self.accuracy_m = round(
            max(2.5, min(35.0, self.hdop * 4.5 + (2.0 if speed_kmh > 60 else 4.0))),
            1,
        )

        rssi_target = -72 if moving else -82
        if self.jamming:
            rssi_target = -98
        self._rssi_float += (rssi_target - self._rssi_float) * min(0.25, dt / 6.0)
        self._rssi_float += random.uniform(-0.8, 0.8)
        self.rssi = int(max(-110, min(-50, round(self._rssi_float))))

        self._maybe_cell_handover(speed_kmh=speed_kmh, distance_m=distance_m, dt=dt)

        rpm_target = rpm_target_for_engine(ignition=ignition, speed_kmh=speed_kmh)
        if not ignition:
            if self.rpm <= 25.0:
                self.rpm = 0.0
            else:
                # Motor desligado: cai rápido para zero (mesmo se o veículo ainda desliza).
                self.rpm += (rpm_target - self.rpm) * min(0.92, dt * 5.0)
        elif rpm_target > self.rpm + 120.0:
            # Aceleração / partida: sobe mais rápido que a queda.
            self.rpm += (rpm_target - self.rpm) * min(0.55, dt * 2.2)
        else:
            self.rpm += (rpm_target - self.rpm) * min(0.4, dt / 1.8)
        self.rpm = max(0.0, self.rpm)

        if ignition and motion_from_speed(speed_kmh):
            self.fuel_percent = max(0.0, self.fuel_percent - 0.004 * dt * (0.8 + speed_kmh / 120.0))
        elif ignition:
            self.fuel_percent = max(0.0, self.fuel_percent - 0.0008 * dt)
