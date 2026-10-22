from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

from app.config import TRAFFIC_PROFILE_PARAMS, Settings, TrafficProfile
from app.routing.polyline import PolylineRoute
from app.simulation.dynamics import apply_dynamics, jitter_target_speed
from app.simulation.telemetry import DeviceTelemetry, motion_from_speed
from app.simulation.violations import VIOLATIONS, ViolationDef
from app.traccar.osmand_client import OsmAndClient, SendResult


@dataclass
class VehicleState:
    lat: float
    lon: float
    bearing: float
    speed_kmh: float
    ignition: bool
    motion: bool
    power: float
    batt: int
    sat: int
    accuracy: float
    altitude: float
    distance_m: float
    progress_pct: float
    waiting_traffic: bool
    paused: bool
    trip_active: bool
    streaming: bool
    route_loaded: bool
    blocked: bool
    rssi: int
    hdop: float
    network: str
    mcc: int
    mnc: int
    lac: int
    cid: int
    wifi_mac: str | None
    charge: bool
    external_power_connected: bool
    odometer_km: float
    odometer_m: int
    active_alarm: str | None
    rpm: int
    fuel_percent: float
    door: bool
    in1: bool
    in2: bool
    in3: bool
    in4: bool
    replay_active: bool
    last_traccar_at: str | None
    last_traccar: SendResult | None = None


@dataclass
class SimulationEngine:
    settings: Settings
    route: PolylineRoute | None = None
    distance_m: float = 0.0
    speed_kmh: float = 0.0
    ignition: bool = False
    blocked: bool = False
    external_power_connected: bool = True
    _interval_wake: asyncio.Event | None = field(default=None, repr=False)
    telemetry: DeviceTelemetry = field(default_factory=DeviceTelemetry)
    streaming: bool = False
    trip_active: bool = False
    paused: bool = False
    loop_task: asyncio.Task | None = None
    _pos_lat: float = 0.0
    _pos_lon: float = 0.0
    _pos_bearing: float = 0.0
    _pos_alt: float = 650.0
    _traffic_wait_until: datetime | None = None
    _last_stop_check_m: float = 0.0
    _pending_alarm: str | None = None
    _jamming_until: datetime | None = None
    _speed_impulse_until: datetime | None = None
    _speed_impulse_delta: float = 0.0
    _trail: list[tuple[float, float]] = field(default_factory=list)
    _listeners: list[Callable[[dict[str, Any]], Awaitable[None]]] = field(default_factory=list)
    _osmand: OsmAndClient = field(default_factory=OsmAndClient)
    replay_active: bool = False
    _replay_index: int = 0
    _last_traccar_at: datetime | None = None

    def __post_init__(self) -> None:
        self._pos_lat = self.settings.default_lat
        self._pos_lon = self.settings.default_lon
        self.telemetry.sync_cell_from_settings(self.settings)

    def report_interval_seconds(self) -> float:
        """Intervalo de envio ao Traccar conforme ignição (comportamento de rastreador)."""
        if self.ignition:
            return float(self.settings.interval_ignition_on)
        return float(self.settings.interval_ignition_off)

    @property
    def running(self) -> bool:
        """Compatível com API antiga: viagem na rota."""
        return self.trip_active

    @running.setter
    def running(self, value: bool) -> None:
        self.trip_active = value

    def _refresh_position_from_route(self) -> None:
        if not self.route:
            return
        lat, lon, brg, _, seg = self.route.sample_at_distance(self.distance_m)
        self._pos_lat = lat
        self._pos_lon = lon
        self._pos_bearing = brg
        self._pos_alt = self.route.altitude_at_segment(seg)

    def set_route(self, route: PolylineRoute) -> None:
        self.route = route
        self.distance_m = 0.0
        self.speed_kmh = 0.0
        self._traffic_wait_until = None
        self._last_stop_check_m = 0.0
        self._refresh_position_from_route()
        self._append_trail(self._pos_lat, self._pos_lon)

    def subscribe(self, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._listeners.append(callback)

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        for cb in list(self._listeners):
            try:
                await cb(payload)
            except Exception:
                pass

    def odometer_m(self) -> float:
        """Odômetro total = valor inicial configurado + distância percorrida na rota atual."""
        return self.settings.odometer_base_m + self.distance_m

    def set_odometer_km(self, km: float) -> None:
        km = max(0.0, float(km))
        self.settings.odometer_base_km = max(0.0, km - (self.distance_m / 1000.0))

    def _append_trail(self, lat: float, lon: float) -> None:
        if self._trail and self._trail[-1] == (lat, lon):
            return
        self._trail.append((lat, lon))
        if len(self._trail) > 500:
            self._trail = self._trail[-500:]

    def get_state(self) -> VehicleState:
        route = self.route
        progress = 0.0
        if route and route.total_length_m > 0:
            progress = 100.0 * self.distance_m / route.total_length_m

        waiting = (
            self._traffic_wait_until is not None
            and datetime.now(timezone.utc) < self._traffic_wait_until
        )

        t = self.telemetry
        return VehicleState(
            lat=self._pos_lat,
            lon=self._pos_lon,
            bearing=self._pos_bearing,
            speed_kmh=round(self.speed_kmh, 1),
            ignition=self.ignition,
            motion=motion_from_speed(self.speed_kmh),
            power=t.power,
            batt=t.batt,
            sat=t.satellites,
            accuracy=t.accuracy_m,
            altitude=self._pos_alt,
            distance_m=round(self.distance_m, 1),
            progress_pct=round(min(100.0, progress), 2),
            waiting_traffic=waiting,
            paused=self.paused,
            trip_active=self.trip_active,
            streaming=self.streaming,
            route_loaded=route is not None,
            blocked=self.blocked,
            rssi=t.rssi,
            hdop=t.hdop,
            network=t.network_display,
            mcc=t.mcc,
            mnc=t.mnc,
            lac=t.lac,
            cid=t.cid,
            wifi_mac=t.wifi_mac,
            charge=t.charge,
            external_power_connected=self.external_power_connected,
            odometer_km=round(self.odometer_m() / 1000.0, 3),
            odometer_m=int(round(self.odometer_m())),
            active_alarm=self._pending_alarm,
            rpm=int(round(t.rpm)),
            fuel_percent=round(t.fuel_percent, 1),
            door=t.door,
            in1=t.in1,
            in2=t.in2,
            in3=t.in3,
            in4=t.in4,
            replay_active=self.replay_active,
            last_traccar_at=self._last_traccar_at.isoformat() if self._last_traccar_at else None,
            last_traccar=self._osmand.last_result,
        )

    def _osmand_extras(self) -> dict[str, Any]:
        t = self.telemetry
        return {
            "door": str(t.door).lower(),
            "in1": str(t.in1).lower(),
            "in2": str(t.in2).lower(),
            "in3": str(t.in3).lower(),
            "in4": str(t.in4).lower(),
            "rpm": int(round(t.rpm)),
            "fuel": round(t.fuel_percent, 1),
        }

    def set_digital(self, **kwargs: bool) -> None:
        for key, val in kwargs.items():
            if hasattr(self.telemetry, key):
                setattr(self.telemetry, key, bool(val))

    async def start_replay(self) -> None:
        if not self.route or len(self.route.points) < 2:
            raise ValueError("Carregue uma rota (ideal: GPX) antes do replay")
        if not self.streaming:
            await self.start_streaming()
        self.replay_active = True
        self._replay_index = 0
        self.trip_active = True
        self.paused = False
        self.distance_m = 0.0
        self._apply_replay_point(0)

    def stop_replay(self) -> None:
        self.replay_active = False
        self._replay_index = 0

    def _apply_replay_point(self, idx: int) -> None:
        if not self.route:
            return
        pts = self.route.points
        idx = max(0, min(idx, len(pts) - 1))
        self._pos_lat, self._pos_lon = pts[idx]
        if idx < len(pts) - 1:
            lat1, lon1 = pts[idx]
            lat2, lon2 = pts[idx + 1]
            d_lon = math.radians(lon2 - lon1)
            y = math.sin(d_lon) * math.cos(math.radians(lat2))
            x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - math.sin(
                math.radians(lat1)
            ) * math.cos(math.radians(lat2)) * math.cos(d_lon)
            self._pos_bearing = (math.degrees(math.atan2(y, x)) + 360) % 360
            self.speed_kmh = 45.0
        else:
            self.speed_kmh = 0.0
        self._pos_alt = self.route.altitude_at_segment(min(idx, len(self.route.segment_speeds_kmh) - 1))

    def _ensure_wake_event(self) -> asyncio.Event:
        if self._interval_wake is None:
            self._interval_wake = asyncio.Event()
        return self._interval_wake

    def reset_report_schedule(self) -> None:
        """Reinicia contagem do intervalo (ex.: após mudar ignição ou tempos de envio)."""
        self._ensure_wake_event().set()

    async def start_streaming(self) -> None:
        if self.streaming:
            return
        self.streaming = True
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.create_task(self._loop())
        await self._tick(self.report_interval_seconds(), force_send=True)

    async def shutdown(self) -> None:
        self.streaming = False
        self.trip_active = False
        self.paused = False
        if self.loop_task and not self.loop_task.done():
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass
        self.loop_task = None

    async def stop(self) -> None:
        """Para apenas a viagem na rota (não desliga envio ao Traccar)."""
        await self.stop_trip()

    async def stop_trip(self) -> None:
        self.trip_active = False
        self.paused = False
        self.stop_replay()

    async def start_trip(self) -> None:
        if not self.route:
            raise ValueError("Carregue uma rota antes de iniciar a viagem")
        if not self.streaming:
            await self.start_streaming()
        self.trip_active = True
        self.paused = False

    async def start(self) -> None:
        if self.trip_active and self.paused:
            self.resume()
            return
        await self.start_trip()

    async def send_once(self) -> SendResult:
        return await self._send_position()

    async def push_to_traccar(self, reason: str = "manual") -> SendResult:
        """Envio imediato na última posição (ignição, bloqueio, alarme…)."""
        self.telemetry.tick(
            0.5,
            ignition=self.ignition,
            speed_kmh=self.speed_kmh,
            blocked=self.blocked,
            external_connected=self.external_power_connected,
        )
        result = await self._send_position()
        await self._emit_payload(sent=True, result=result, reason=reason)
        return result

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        if self.trip_active:
            self.paused = False

    async def set_ignition(self, on: bool) -> None:
        self.ignition = on
        if not on:
            self.telemetry.rpm = 0.0
        if not self.streaming:
            await self.start_streaming()
        await self.push_to_traccar(reason="ignition")
        self.reset_report_schedule()

    async def set_blocked(self, on: bool) -> None:
        self.blocked = on
        if not self.streaming:
            await self.start_streaming()
        await self.push_to_traccar(reason="blocked")
        self.reset_report_schedule()

    async def set_external_power(self, connected: bool) -> None:
        if self.external_power_connected == connected:
            return

        self.external_power_connected = connected
        if not connected:
            self.telemetry.force_external_off()
            self.ignition = False
            self._pending_alarm = "powerCut"
        else:
            self.telemetry.on_external_connected()
            self._pending_alarm = "powerRestored"

        if not self.streaming:
            await self.start_streaming()
        await self.push_to_traccar(reason="external_power")
        self.reset_report_schedule()

    async def trigger_violation(self, violation_id: str) -> ViolationDef:
        if violation_id not in VIOLATIONS:
            raise ValueError(f"Violação desconhecida: {violation_id}")
        v = VIOLATIONS[violation_id]
        self._pending_alarm = v.alarm

        if v.speed_delta_kmh:
            self._speed_impulse_delta = v.speed_delta_kmh
            self._speed_impulse_until = datetime.now(timezone.utc) + timedelta(seconds=12)

        if v.force_ignition is not None:
            self.ignition = v.force_ignition

        if v.power_spike is not None:
            self.telemetry.external_voltage = v.power_spike
        if violation_id == "powerCut":
            self.external_power_connected = False
            self.telemetry.force_external_off()
            self.ignition = False

        if violation_id == "lowBattery":
            self.telemetry.apply_violation_low_battery()
        if violation_id == "jamming":
            self.telemetry.apply_violation_jamming()
            self._jamming_until = datetime.now(timezone.utc) + timedelta(seconds=30)

        if violation_id == "hardBraking":
            self.speed_kmh = max(0.0, self.speed_kmh - 30)

        if not self.streaming:
            await self.start_streaming()
        await self.push_to_traccar(reason="alarm")
        return v

    def _traffic_params(self) -> dict[str, float]:
        profile = self.settings.traffic_profile
        if isinstance(profile, str):
            profile = TrafficProfile(profile)
        return TRAFFIC_PROFILE_PARAMS.get(profile, TRAFFIC_PROFILE_PARAMS[TrafficProfile.NORMAL])

    def _maybe_trigger_stop(self) -> None:
        if not self.route or self._traffic_wait_until:
            return
        params = self._traffic_params()
        route = self.route

        for stop_d in route.stop_distances:
            if abs(self.distance_m - stop_d) < 15 and random.random() < params["junction_stop_probability"]:
                self._schedule_traffic_stop()
                return

        interval = 2000.0
        if self.distance_m - self._last_stop_check_m >= interval:
            self._last_stop_check_m = self.distance_m
            if random.random() < params["congestion_stop_probability"]:
                self._schedule_traffic_stop(long=True)

    def _schedule_traffic_stop(self, long: bool = False) -> None:
        seconds = random.uniform(45, 90) if long else random.uniform(15, 45)
        self._traffic_wait_until = datetime.now(timezone.utc) + timedelta(seconds=seconds)
        self.speed_kmh = max(0.0, self.speed_kmh - 15)

    async def _sleep_until_next_report(self) -> None:
        loop = asyncio.get_running_loop()
        wake = self._ensure_wake_event()
        deadline = loop.time() + self.report_interval_seconds()
        while self.streaming:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            wake.clear()
            try:
                await asyncio.wait_for(wake.wait(), timeout=remaining)
                deadline = loop.time() + self.report_interval_seconds()
            except asyncio.TimeoutError:
                return

    async def _loop(self) -> None:
        try:
            while self.streaming:
                interval = self.report_interval_seconds()
                await self._tick(interval)
                await self._sleep_until_next_report()
        except asyncio.CancelledError:
            raise

    async def _send_position(self) -> SendResult:
        st = self.get_state()
        alarm = self._pending_alarm
        self._pending_alarm = None

        power_v = 0.0 if not self.external_power_connected else st.power

        driver = (self.settings.driver_unique_id or "").strip() or None
        result = await self._osmand.send(
            settings=self.settings,
            lat=st.lat,
            lon=st.lon,
            speed_kmh=st.speed_kmh,
            bearing=st.bearing,
            altitude=st.altitude,
            accuracy=st.accuracy,
            batt=st.batt,
            ignition=st.ignition,
            motion=st.motion,
            power=power_v,
            sat=st.sat,
            blocked=self.blocked,
            alarm=alarm,
            rssi=st.rssi,
            hdop=st.hdop,
            charge=st.charge,
            cell=self.telemetry.cell_osmand_param(),
            wifi=self.telemetry.wifi_osmand_param(),
            odometer_m=st.odometer_m,
            driver_unique_id=driver,
            extras=self._osmand_extras(),
        )
        if result.ok:
            self._last_traccar_at = datetime.now(timezone.utc)
        return result

    async def _tick(self, dt: float, *, force_send: bool = False) -> None:
        now = datetime.now(timezone.utc)
        if self._jamming_until and now >= self._jamming_until:
            self._jamming_until = None
            self.telemetry.clear_jamming_after()

        trip_moving = self.route and self.trip_active and not self.paused and not self.replay_active

        if self.replay_active and self.trip_active and not self.paused and self.route:
            self._replay_index = min(self._replay_index + 1, len(self.route.points) - 1)
            self._apply_replay_point(self._replay_index)
            if self._replay_index >= len(self.route.points) - 1:
                self.speed_kmh = 0.0
        elif trip_moving:
            if self._traffic_wait_until and now < self._traffic_wait_until:
                target = 0.0
            else:
                if self._traffic_wait_until and now >= self._traffic_wait_until:
                    self._traffic_wait_until = None
                _, _, _, seg_speed, _ = self.route.sample_at_distance(self.distance_m)
                params = self._traffic_params()
                target = jitter_target_speed(seg_speed, params["speed_factor"])
                self._maybe_trigger_stop()
                if self._traffic_wait_until:
                    target = 0.0

            if not self.ignition and target > self.speed_kmh + 5:
                target = min(target, self.speed_kmh + 2.0)

            if self._speed_impulse_until and now < self._speed_impulse_until:
                target = max(target, self.speed_kmh + self._speed_impulse_delta * 0.3)
            elif self._speed_impulse_until and now >= self._speed_impulse_until:
                self._speed_impulse_until = None
                self._speed_impulse_delta = 0.0

            self.speed_kmh = apply_dynamics(self.speed_kmh, target, dt)

            if motion_from_speed(self.speed_kmh):
                advance = (self.speed_kmh / 3.6) * dt
                self.distance_m += advance
                if self.route.total_length_m > 0 and self.distance_m >= self.route.total_length_m:
                    self.distance_m = self.route.total_length_m
                    self.speed_kmh = 0.0
            self._refresh_position_from_route()
        elif not self.trip_active or self.paused:
            self.speed_kmh = apply_dynamics(self.speed_kmh, 0.0, dt)

        self.telemetry.tick(
            dt,
            ignition=self.ignition,
            speed_kmh=self.speed_kmh,
            blocked=self.blocked,
            external_connected=self.external_power_connected,
            distance_m=self.distance_m,
        )
        self._append_trail(self._pos_lat, self._pos_lon)

        result = self._osmand.last_result
        sent = False
        if self.streaming:
            result = await self._send_position()
            sent = True

        await self._emit_payload(sent=sent, result=result, reason="tick")

    async def _emit_payload(
        self,
        *,
        sent: bool,
        result: SendResult | None,
        reason: str,
    ) -> None:
        st = self.get_state()
        payload = {
            "type": "tick",
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "lat": st.lat,
            "lon": st.lon,
            "speed_kmh": st.speed_kmh,
            "bearing": st.bearing,
            "ignition": st.ignition,
            "motion": st.motion,
            "power": st.power,
            "batt": st.batt,
            "sat": st.sat,
            "rssi": st.rssi,
            "hdop": st.hdop,
            "network": st.network,
            "mcc": st.mcc,
            "mnc": st.mnc,
            "lac": st.lac,
            "cid": st.cid,
            "wifi_mac": st.wifi_mac,
            "radio": self.telemetry.radio_label,
            "charge": st.charge,
            "blocked": st.blocked,
            "external_power_connected": st.external_power_connected,
            "odometer_km": st.odometer_km,
            "odometer_m": st.odometer_m,
            "alarm": st.active_alarm,
            "progress_pct": st.progress_pct,
            "waiting_traffic": st.waiting_traffic,
            "paused": self.paused,
            "running": self.trip_active,
            "trip_active": self.trip_active,
            "streaming": self.streaming,
            "report_interval_s": self.report_interval_seconds(),
            "traccar_ok": result.ok if result else None,
            "traccar_status": result.status_code if result else None,
            "traccar_error": result.error if result else None,
            "last_traccar_at": st.last_traccar_at,
            "rpm": st.rpm,
            "fuel_percent": st.fuel_percent,
            "door": st.door,
            "in1": st.in1,
            "in2": st.in2,
            "in3": st.in3,
            "in4": st.in4,
            "replay_active": st.replay_active,
            "sent": sent,
            "trail": self._trail[-120:],
        }
        await self._broadcast(payload)
