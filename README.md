# XTraccar Simulator

**English** · [Español](README.es.md) · [Português](README.pt.md)

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G7B227FYIH)

Vehicle simulator for testing and demos on [Traccar](https://www.traccar.org/) via the HTTP **OsmAnd** protocol (port **5055**). The vehicle follows **real roads** (OpenStreetMap + **OSRM**) or a **GPX** file, with speed dynamics, realistic telemetry, and a live web dashboard.

> Available for anyone who needs Traccar/OsmAnd integration tests. Not a public open-source contribution project — distribute and use according to your organization’s policy.

**Web UI languages:** **English**, **Spanish**, and **Portuguese** (flag menu in the top bar; choice saved in the browser).

![Web dashboard with Leaflet map](docs/screenshot.png)

---

## Index

1. [Getting everything running](#getting-everything-running)
2. [Stop and restart](#stop-and-restart)
3. [Features](#features)
4. [Configuration](#configuration-configyaml--dashboard)
5. [Using the dashboard](#using-the-dashboard)
6. [Telemetry](#telemetry)
7. [REST API](#rest-api)
8. [Troubleshooting](#troubleshooting)
9. [Project layout](#project-layout)
10. [Distribution](#distribution)

---

## Getting everything running

You need **two services**: **Traccar** (receives positions) and this **simulator** (dashboard + OsmAnd sends).

### 1. Traccar

1. Install and start Traccar ([traccar.org](https://www.traccar.org/)).
2. Confirm **OsmAnd** listens on port **5055**.
3. Create a **device** and note its **unique id**.
4. Use the same value as `device_id` in the simulator (`config.yaml` or `config.example.yaml`).
5. Open firewall **TCP 5055** between simulator PC and Traccar.

**Typical OsmAnd URL:** `http://TRACCAR_IP:5055/`

### 2. First-time install (Windows)

```powershell
cd "C:\Users\...\XTraccar Simulator"
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy config.example.yaml config.yaml
notepad config.yaml
```

Edit at least `traccar_url` and `device_id`. **`config.yaml` is gitignored** (local only).

**Default values** (`config.example.yaml`):

| Field | Default |
|-------|---------|
| `default_lat` / `default_lon` | **-22.7487**, **-48.5837** |
| `cell_mcc` / `cell_mnc` / `cell_lac` / `cell_cid` | **724** / **5** / **43714** / **45086** |
| Send intervals (ign ON / OFF) | **5 s** / **60 s** |
| Dashboard | **http://127.0.0.1:8081** |

### 3. Start the simulator

- **Windows:** double-click **`iniciar.bat`** (frees port **8081**, starts uvicorn).
- **Manual:** `.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8081`

Dashboard **8081** · Traccar OsmAnd **5055**.

### 4. Verify

- http://127.0.0.1:8081  
- http://127.0.0.1:8081/api/health → `"version": "2.1"`

### 5. First Traccar test

1. Dashboard → **Settings** → URL + Device ID → **Save** → **Test connection**.
2. Check device **Last update** in Traccar.

### 6. Linux / macOS

```bash
cd "XTraccar Simulator"
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
uvicorn app.main:app --host 127.0.0.1 --port 8081
```

---

## Stop and restart

| Action | How |
|--------|-----|
| Stop simulator | **Ctrl+C** in uvicorn window |
| Restart (Windows) | Run **`iniciar.bat`** again |
| Port 8081 busy | `iniciar.bat` or kill the old process |
| After code/config change | Restart uvicorn; **Ctrl+F5** in browser |

Start **Traccar first**, then the simulator.

---

## Features

| Area | Capabilities |
|------|----------------|
| **Map** | Leaflet, OSM/HOT, waypoints, OSRM, GPX, Follow (min zoom 16), HUD |
| **Trip** | Start, pause/resume (**Space**), stop; traffic profiles |
| **Traccar** | Heartbeat, ign ON/OFF intervals, HTTP test, event log |
| **Vehicle** | Ignition, 12V, immobilizer, odometer |
| **Telemetry** | RPM, fuel, cell, Wi‑Fi, alarms, digital inputs |
| **GPX** | Export trail; point-by-point replay |
| **UI** | EN/ES/PT, light/dark theme |
| **Automation** | REST + WebSocket `/ws/live` |

---

## Configuration (`config.yaml` / dashboard)

Loaded from **`config.yaml`** at startup (else code defaults).

| Key | Description |
|-----|-------------|
| `traccar_url` | OsmAnd base URL |
| `device_id` | Traccar unique id |
| `interval_ignition_on` / `off` | Send interval (seconds) |
| `osrm_base_url` | OSRM API |
| `traffic_profile` | `low` \| `normal` \| `heavy` |
| `default_lat` / `default_lon` | Map center |
| `odometer_base_km` | Initial odometer (km) |
| `cell_*` | Simulated tower (MCC/MNC/LAC/CID) |
| `driver_unique_id` | Optional OsmAnd driver |
| `map_style` | `osm` or `hot` |

Env prefix: **`TRACCAR_SIM_`**.

---

## Using the dashboard

1. **Settings** → Traccar URL + Device ID → **Save** → **Test connection**.
2. **Route** → map clicks (2+ points) → **Calculate route (OSRM)** or **GPX**.
3. Optional odometer → **OK**.
4. **Start** — watch Traccar and the HUD.

---

## Telemetry

- **Odometer:** sent as **`odometer`** in **meters**.
- **RPM:** 0 when off; idle when stopped; scales with speed when moving.
- **Cell default:** `724,5,43714,45086` (OsmAnd `cell=` parameter).

---

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/status` | Full state + settings |
| GET | `/api/health` | Service version |
| PUT | `/api/settings` | Update settings |
| POST | `/api/route/osrm` | Waypoints → route |
| POST | `/api/route/gpx` | GPX upload |
| POST | `/api/simulation/start` \| `stop` \| `pause` | Trip control |
| POST | `/api/vehicle/*` | Ignition, block, power, odometer, digital |
| GET | `/api/trail/export.gpx` | Export trail |
| POST | `/api/replay/start` \| `stop` | GPX replay |
| POST | `/api/traccar/test` | Test send |
| WS | `/ws/live` | Live ticks |

---

## Troubleshooting

| Issue | Check |
|-------|--------|
| Dashboard 404 | Uvicorn on **8081**? `/api/health` |
| Traccar silent | Same `device_id`, URL `:5055`, firewall |
| OSRM errors | Public OSRM rate limits — use your own server |
| Old UI | **Ctrl+F5** |

---

## Project layout

```
app/static/     # Dashboard (i18n.js, locales.js, app.js)
app/simulation/ # Engine & telemetry
app/routing/    # OSRM & GPX
app/traccar/    # OsmAnd HTTP client
config.example.yaml
iniciar.bat     # Windows launcher (8081)
```

---

## Distribution

You may **install and share** this package for Traccar testing. Maintenance of forks/copies is up to the distributor.

**Quick checklist:** Python 3.11+ → `pip install -e .` → `config.yaml` → Traccar :5055 → `iniciar.bat` → http://127.0.0.1:8081
