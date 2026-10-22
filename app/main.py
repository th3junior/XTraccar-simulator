from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import Settings, TrafficProfile, load_settings, save_settings_yaml
from app.gpx_export import trail_to_gpx
from app.routing.gpx_loader import load_gpx
from app.routing.osrm import fetch_osrm_route
from app.simulation.engine import SimulationEngine
from app.simulation.violations import list_violations

STATIC_DIR = Path(__file__).resolve().parent / "static"

settings: Settings = load_settings()
engine = SimulationEngine(settings=settings)
ws_clients: set[WebSocket] = set()


async def _on_engine_event(payload: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for ws in list(ws_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine.subscribe(_on_engine_event)
    await engine.start_streaming()
    yield
    await engine.shutdown()
    await engine._osmand.close()


app = FastAPI(title="XTraccar Simulator", lifespan=lifespan)


class SettingsUpdate(BaseModel):
    traccar_url: str | None = None
    device_id: str | None = None
    interval_seconds: float | None = Field(default=None, ge=1, le=3600)
    interval_ignition_on: float | None = Field(default=None, ge=1, le=3600)
    interval_ignition_off: float | None = Field(default=None, ge=1, le=3600)
    osrm_base_url: str | None = None
    traffic_profile: TrafficProfile | None = None
    send_while_paused: bool | None = None
    odometer_base_km: float | None = Field(default=None, ge=0)
    cell_mcc: int | None = Field(default=None, ge=1, le=999)
    cell_mnc: int | None = Field(default=None, ge=0, le=999)
    cell_lac: int | None = Field(default=None, ge=0)
    cell_cid: int | None = Field(default=None, ge=0)
    cell_wifi_mac: str | None = None
    driver_unique_id: str | None = None
    map_style: str | None = None
    persist: bool | None = None


class OsrmRouteRequest(BaseModel):
    waypoints: list[list[float]] = Field(
        ...,
        min_length=2,
        description="Lista [lat, lon]",
    )


class IgnitionRequest(BaseModel):
    on: bool


class BlockedRequest(BaseModel):
    on: bool


class ExternalPowerRequest(BaseModel):
    connected: bool


class ViolationRequest(BaseModel):
    id: str


class OdometerRequest(BaseModel):
    km: float = Field(..., ge=0, description="Odômetro total exibido (km)")


class DigitalInputsRequest(BaseModel):
    door: bool | None = None
    in1: bool | None = None
    in2: bool | None = None
    in3: bool | None = None
    in4: bool | None = None


def _state_dict() -> dict[str, Any]:
    st = engine.get_state()
    route_geo = engine.route.to_geojson() if engine.route else None
    return {
        "lat": st.lat,
        "lon": st.lon,
        "bearing": st.bearing,
        "speed_kmh": st.speed_kmh,
        "ignition": st.ignition,
        "motion": st.motion,
        "power": st.power,
        "batt": st.batt,
        "sat": st.sat,
        "accuracy": st.accuracy,
        "altitude": st.altitude,
        "distance_m": st.distance_m,
        "progress_pct": st.progress_pct,
        "waiting_traffic": st.waiting_traffic,
        "paused": st.paused,
        "running": st.trip_active,
        "trip_active": st.trip_active,
        "streaming": st.streaming,
        "route_loaded": st.route_loaded,
        "blocked": st.blocked,
        "rssi": st.rssi,
        "hdop": st.hdop,
        "network": st.network,
        "mcc": st.mcc,
        "mnc": st.mnc,
        "lac": st.lac,
        "cid": st.cid,
        "wifi_mac": st.wifi_mac,
        "radio": engine.telemetry.radio_label,
        "charge": st.charge,
        "external_power_connected": st.external_power_connected,
        "odometer_km": st.odometer_km,
        "odometer_m": st.odometer_m,
        "active_alarm": st.active_alarm,
        "report_interval_s": engine.report_interval_seconds(),
        "trail": engine._trail[-120:],
        "traccar_ok": st.last_traccar.ok if st.last_traccar else None,
        "traccar_status": st.last_traccar.status_code if st.last_traccar else None,
        "traccar_error": st.last_traccar.error if st.last_traccar else None,
        "last_traccar_at": st.last_traccar_at,
        "rpm": st.rpm,
        "fuel_percent": st.fuel_percent,
        "door": st.door,
        "in1": st.in1,
        "in2": st.in2,
        "in3": st.in3,
        "in4": st.in4,
        "replay_active": st.replay_active,
        "route_source": engine.route.source if engine.route else None,
        "route": route_geo,
        "settings": {
            "traccar_url": settings.traccar_url,
            "device_id": settings.device_id,
            "interval_seconds": settings.interval_seconds,
            "interval_ignition_on": settings.interval_ignition_on,
            "interval_ignition_off": settings.interval_ignition_off,
            "osrm_base_url": settings.osrm_base_url,
            "traffic_profile": settings.traffic_profile.value
            if isinstance(settings.traffic_profile, TrafficProfile)
            else settings.traffic_profile,
            "send_while_paused": settings.send_while_paused,
            "default_lat": settings.default_lat,
            "default_lon": settings.default_lon,
            "odometer_base_km": settings.odometer_base_km,
            "cell_mcc": settings.cell_mcc,
            "cell_mnc": settings.cell_mnc,
            "cell_lac": settings.cell_lac,
            "cell_cid": settings.cell_cid,
            "cell_wifi_mac": settings.cell_wifi_mac,
            "driver_unique_id": settings.driver_unique_id,
            "map_style": settings.map_style,
        },
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
async def api_status():
    return _state_dict()


@app.get("/api/health")
async def api_health():
    return {"ok": True, "service": "xtraccar-simulator", "version": "2.1"}


@app.put("/api/settings")
async def api_settings(body: SettingsUpdate):
    data = body.model_dump(exclude_none=True)
    persist = data.pop("persist", True)
    for key, value in data.items():
        setattr(settings, key, value)
    if "interval_ignition_on" in data:
        settings.interval_seconds = settings.interval_ignition_on
    if settings.map_style not in ("osm", "hot"):
        settings.map_style = "osm"
    engine.settings = settings
    engine.telemetry.sync_cell_from_settings(settings)
    engine.reset_report_schedule()
    saved_path = None
    if persist:
        saved_path = str(save_settings_yaml(settings))
    return {"ok": True, "saved_config": saved_path, "settings": _state_dict()["settings"]}


@app.post("/api/route/osrm")
async def api_route_osrm(body: OsrmRouteRequest):
    waypoints: list[tuple[float, float]] = []
    for wp in body.waypoints:
        if len(wp) != 2:
            raise HTTPException(400, "Cada waypoint deve ser [lat, lon]")
        waypoints.append((float(wp[0]), float(wp[1])))

    try:
        route = await fetch_osrm_route(waypoints, base_url=settings.osrm_base_url)
    except Exception as e:
        raise HTTPException(502, str(e)) from e

    await engine.stop_trip()
    engine.set_route(route)
    return {"ok": True, "route": route.to_geojson(), "length_m": route.total_length_m}


@app.post("/api/route/gpx")
async def api_route_gpx(file: UploadFile = File(...)):
    data = await file.read()
    try:
        route = load_gpx(data)
    except Exception as e:
        raise HTTPException(400, str(e)) from e

    await engine.stop_trip()
    engine.set_route(route)
    return {"ok": True, "route": route.to_geojson(), "length_m": route.total_length_m}


@app.post("/api/simulation/start")
async def api_simulation_start():
    try:
        await engine.start()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "state": _state_dict()}


@app.post("/api/simulation/stop")
async def api_simulation_stop():
    await engine.stop_trip()
    return {"ok": True, "state": _state_dict()}


@app.post("/api/simulation/pause")
async def api_simulation_pause():
    if not engine.trip_active:
        raise HTTPException(400, "Viagem na rota não está ativa")
    if engine.paused:
        engine.resume()
    else:
        engine.pause()
    return {"ok": True, "paused": engine.paused, "state": _state_dict()}


@app.post("/api/vehicle/ignition")
async def api_ignition(body: IgnitionRequest):
    await engine.set_ignition(body.on)
    return {"ok": True, "ignition": engine.ignition, "state": _state_dict()}


@app.post("/api/vehicle/blocked")
async def api_blocked(body: BlockedRequest):
    await engine.set_blocked(body.on)
    return {"ok": True, "blocked": engine.blocked, "state": _state_dict()}


@app.post("/api/vehicle/odometer")
async def api_odometer(body: OdometerRequest):
    engine.set_odometer_km(body.km)
    settings.odometer_base_km = engine.settings.odometer_base_km
    await engine.push_to_traccar(reason="odometer")
    return {"ok": True, "odometer_km": engine.get_state().odometer_km, "state": _state_dict()}


@app.post("/api/vehicle/digital")
async def api_vehicle_digital(body: DigitalInputsRequest):
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "Informe ao menos uma entrada")
    engine.set_digital(**fields)
    await engine.push_to_traccar(reason="digital")
    return {"ok": True, "state": _state_dict()}


@app.get("/api/trail/export.gpx")
async def api_trail_export_gpx():
    trail = engine._trail
    if len(trail) < 2:
        raise HTTPException(400, "Trilha vazia — mova o veículo antes de exportar")
    gpx = trail_to_gpx(trail)
    return Response(
        content=gpx,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": 'attachment; filename="simulator-trail.gpx"'},
    )


@app.post("/api/replay/start")
async def api_replay_start():
    try:
        await engine.start_replay()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "state": _state_dict()}


@app.post("/api/replay/stop")
async def api_replay_stop():
    engine.stop_replay()
    await engine.stop_trip()
    return {"ok": True, "state": _state_dict()}


@app.post("/api/vehicle/external-power")
async def api_external_power(body: ExternalPowerRequest):
    await engine.set_external_power(body.connected)
    return {
        "ok": True,
        "external_power_connected": engine.external_power_connected,
        "state": _state_dict(),
    }


@app.get("/api/violations")
async def api_violations_list():
    return {"violations": list_violations()}


@app.post("/api/violations/trigger")
async def api_violations_trigger(body: ViolationRequest):
    try:
        v = await engine.trigger_violation(body.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "alarm": v.alarm, "label": v.label, "state": _state_dict()}


@app.post("/api/traccar/test")
async def api_traccar_test():
    """Envia uma posição imediata ao Traccar (não exige simulação em execução)."""
    if not engine.streaming:
        await engine.start_streaming()
    result = await engine.push_to_traccar(reason="test")
    if not result.ok:
        detail = result.error or f"HTTP {result.status_code}"
        raise HTTPException(502, f"Traccar não respondeu: {detail}")
    return {
        "ok": True,
        "status_code": result.status_code,
        "state": _state_dict(),
    }


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        await websocket.send_json({"type": "status", **_state_dict()})
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    run()
