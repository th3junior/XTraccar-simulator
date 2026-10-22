const DEFAULT_CENTER = [-22.7487, -48.5837];
const waypoints = [];
let violationsCatalog = [];

let map;
let routeLayer;
let waypointLayer;
let trailLayer;
let vehicleMarker;
let routeOutlineLayer;
let followVehicle = false;
let routeCalculated = false;
let routeSource = null;
let mapTileLayers = {};
let activeMapTile = null;
let suppressDigitalEvents = false;
let markerAnimFrame = null;
let lastVehiclePos = null;
let suppressToggleEvents = false;
let lastLogTick = 0;
let lastGaugeState = null;

const tt = (key, params) => window.i18n.t(key, params);

function refreshVehicleTooltip() {
  if (vehicleMarker) vehicleMarker.setTooltipContent(tt("map.vehicleTooltip"));
}

function violationLabel(id) {
  const loc = tt(`violations.${id}.label`);
  return loc === `violations.${id}.label` ? id : loc;
}

function violationDesc(id) {
  const loc = tt(`violations.${id}.desc`);
  return loc === `violations.${id}.desc` ? "" : loc;
}

const VEHICLE_SVG = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M12 2L19 20H14.5L13.5 17H10.5L9.5 20H5L12 2Z" fill="#34d399" stroke="#064e3b" stroke-width="1.2"/>
  <circle cx="12" cy="12" r="2.2" fill="#ecfdf5"/>
</svg>`;

function log(msg, level = "info") {
  const el = document.getElementById("log");
  const line = document.createElement("div");
  const prefix = level === "err" ? "!" : level === "ok" ? "✓" : "·";
  line.textContent = `[${new Date().toLocaleTimeString()}] ${prefix} ${msg}`;
  if (level === "err") line.className = "log-err";
  else if (level === "ok") line.className = "log-ok";
  el.prepend(line);
  while (el.children.length > 35) el.removeChild(el.lastChild);
}

function formatApiError(data, fallback) {
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return fallback;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(formatApiError(data, res.statusText));
  return data;
}

function setPill(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  const base = el.classList.contains("badge") ? "badge" : "pill";
  el.className = cls ? `${base} ${cls}` : base;
}

function clearRouteLine() {
  if (!map) return;
  if (routeLayer) map.removeLayer(routeLayer);
  if (routeOutlineLayer) map.removeLayer(routeOutlineLayer);
  routeLayer = null;
  routeOutlineLayer = null;
  routeCalculated = false;
}

function updateRouteUI() {
  const n = waypoints.length;
  const status = document.getElementById("routeStatus");
  const list = document.getElementById("wpList");
  const btnOsrm = document.getElementById("btnLoadOsrm");
  const btnUndo = document.getElementById("btnUndoWp");

  if (btnUndo) btnUndo.disabled = n === 0;
  if (btnOsrm) btnOsrm.disabled = n < 2;

  if (status) {
    if (n === 0) status.innerHTML = tt("route.status0");
    else if (n === 1) status.innerHTML = tt("route.status1");
    else if (!routeCalculated) status.innerHTML = tt("route.statusN", { n });
    else status.innerHTML = tt("route.statusDone");
  }

  if (list) {
    list.innerHTML = "";
    waypoints.forEach((wp, i) => {
      const li = document.createElement("li");
      const label =
        i === 0
          ? tt("route.origin")
          : i === waypoints.length - 1 && waypoints.length > 1
            ? tt("route.dest")
            : tt("route.stop", { n: i });
      li.innerHTML = `<span class="wp-num">${i + 1}</span><span class="wp-label">${label}</span><span class="wp-coord">${wp[0].toFixed(5)}, ${wp[1].toFixed(5)}</span>`;
      list.appendChild(li);
    });
  }

  document.querySelectorAll(".route-step").forEach((el) => {
    const step = el.dataset.step;
    el.classList.remove("active", "done");
    if (step === "1") {
      if (n >= 2) el.classList.add("done");
      else el.classList.add("active");
    } else if (step === "2") {
      if (routeCalculated) el.classList.add("done");
      else if (n >= 2) el.classList.add("active");
    } else if (step === "3") {
      if (routeCalculated) el.classList.add("active");
    }
  });
}

function setRouteDrawMode(on) {
  document.body.classList.toggle("route-drawing", on);
  const hint = document.getElementById("routeMapHint");
  if (hint) hint.hidden = !on;
}

function initShellUI() {
  const backdrop = document.getElementById("backdrop");
  const panels = {
    route: document.getElementById("routePanel"),
    settings: document.getElementById("settingsPanel"),
    events: document.getElementById("eventsPanel"),
  };
  let openId = null;

  function closePanels() {
    openId = null;
    setRouteDrawMode(false);
    backdrop.hidden = true;
    document.body.classList.remove("panel-open");
    Object.values(panels).forEach((p) => {
      if (!p) return;
      p.hidden = true;
      p.classList.remove("is-open");
    });
  }

  function openPanel(id) {
    if (openId === id) {
      closePanels();
      return;
    }
    closePanels();
    const panel = panels[id];
    if (!panel) return;
    openId = id;
    panel.hidden = false;
    requestAnimationFrame(() => panel.classList.add("is-open"));
    backdrop.hidden = false;
    document.body.classList.add("panel-open");
    setRouteDrawMode(id === "route");
    if (id === "route") updateRouteUI();
  }

  document.getElementById("btnOpenRoute")?.addEventListener("click", () => openPanel("route"));
  document.getElementById("btnOpenSettings")?.addEventListener("click", () => openPanel("settings"));
  document.getElementById("btnOpenEvents")?.addEventListener("click", () => openPanel("events"));
  backdrop?.addEventListener("click", closePanels);
  document.querySelectorAll("[data-close]").forEach((btn) => {
    btn.addEventListener("click", closePanels);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanels();
  });

  document.querySelectorAll(".stab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      document.querySelectorAll(".stab").forEach((t) => t.classList.toggle("active", t === tab));
      document.querySelectorAll(".stab-panel").forEach((p) => {
        const on = p.dataset.tabPanel === name;
        p.classList.toggle("active", on);
        p.hidden = !on;
      });
    });
  });
}

function updateTripButtons(state) {
  const tripActive = !!(state.trip_active ?? state.running) || !!state.replay_active;
  const paused = !!state.paused;
  const routeLoaded = !!state.route_loaded;

  const btnStart = document.getElementById("btnStart");
  const btnPause = document.getElementById("btnPause");
  const btnStop = document.getElementById("btnStop");
  const startText = document.getElementById("btnStartText");
  const pauseText = document.getElementById("btnPauseText");
  if (!btnStart || !btnPause || !btnStop) return;

  const moving = tripActive && !paused;

  if (tripActive && paused) {
    btnStart.disabled = false;
    btnPause.disabled = true;
    btnStop.disabled = false;
    btnStart.title = tt("trip.titleResume");
    btnPause.title = tt("trip.titlePaused");
    btnStop.title = tt("trip.titleStop");
    if (startText) startText.textContent = tt("trip.resume");
    if (pauseText) pauseText.textContent = tt("trip.pause");
    btnStart.classList.add("trip-resume");
    btnPause.classList.remove("trip-resume");
  } else if (moving) {
    btnStart.disabled = true;
    btnPause.disabled = false;
    btnStop.disabled = false;
    btnStart.title = tt("trip.titleRunning");
    btnPause.title = tt("trip.titlePause");
    btnStop.title = tt("trip.titleStop");
    if (startText) startText.textContent = tt("trip.start");
    if (pauseText) pauseText.textContent = tt("trip.pause");
    btnStart.classList.remove("trip-resume");
    btnPause.classList.remove("trip-resume");
  } else {
    btnStart.disabled = !routeLoaded;
    btnPause.disabled = true;
    btnStop.disabled = true;
    btnStart.title = routeLoaded ? tt("trip.titleStart") : tt("trip.titleNeedRoute");
    btnPause.title = tt("trip.titlePauseIdle");
    btnStop.title = tt("trip.titleStopIdle");
    if (startText) startText.textContent = tt("trip.start");
    if (pauseText) pauseText.textContent = tt("trip.pause");
    btnStart.classList.remove("trip-resume");
    btnPause.classList.remove("trip-resume");
  }
}

function updateGauges(state) {
  const speed = state.speed_kmh ?? 0;
  document.getElementById("gSpeed").textContent = Math.round(speed);
  document.getElementById("barSpeed").style.width = `${Math.min(100, (speed / 120) * 100)}%`;

  const batt = state.batt ?? 0;
  document.getElementById("gBatt").textContent = batt;
  document.getElementById("barBatt").style.width = `${batt}%`;

  document.getElementById("gPower").textContent =
    state.power != null ? Number(state.power).toFixed(2) : "—";
  document.getElementById("gExt").textContent = state.external_power_connected
    ? tt("gauge.extOn")
    : tt("gauge.extOff");
  document.getElementById("gCharge").textContent = state.charge ? tt("gauge.chargeYes") : tt("gauge.chargeNo");

  document.getElementById("gSat").textContent = state.sat ?? "—";
  document.getElementById("gHdop").textContent = tt("gauge.hdop", { v: state.hdop ?? "—" });

  const mcc = state.mcc ?? "—";
  const mnc = state.mnc ?? "—";
  const lac = state.lac ?? "—";
  const cid = state.cid ?? "—";
  document.getElementById("gNet").textContent = `${mcc} · ${mnc} · ${lac} · ${cid}`;
  const rssi = state.rssi ?? -100;
  if (state.wifi_mac) {
    document.getElementById("gRssi").textContent = tt("gauge.wifiRssi", {
      mac: state.wifi_mac,
      rssi,
    });
  } else {
    const radio = state.radio ? `${state.radio} · ` : "";
    document.getElementById("gRssi").textContent = `${radio}${rssi} dBm`;
  }
  const sigPct = Math.max(0, Math.min(100, ((rssi + 110) / 60) * 100));
  const barSignal = document.getElementById("barSignal");
  if (barSignal) barSignal.style.width = `${sigPct}%`;

  const odoKm = state.odometer_km ?? 0;
  const odoFmt = Number(odoKm).toLocaleString(window.i18n.localeTag(), {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  document.getElementById("gOdo").textContent = odoFmt;
  const odoLive = document.getElementById("odometerLive");
  if (odoLive) odoLive.textContent = odoFmt;

  const prog = state.progress_pct ?? 0;
  document.getElementById("gProgress").textContent = `${prog}%`;
  document.getElementById("barProgress").style.width = `${prog}%`;

  const rep = state.report_interval_s ?? (state.ignition ? 5 : 60);
  let traccarHud = tt("pills.traccarDash");
  if (state.last_traccar_at) {
    const timeStr = new Date(state.last_traccar_at).toLocaleTimeString(window.i18n.localeTag());
    traccarHud =
      state.traccar_ok === true
        ? tt("hud.traccarOk", { time: timeStr, code: state.traccar_status })
        : state.traccar_ok === false
          ? tt("hud.traccarFail", { time: timeStr })
          : tt("hud.traccarAt", { time: timeStr });
  }
  document.getElementById("mapHud").textContent =
    `${speed.toFixed(0)} km/h · ${odoFmt} km · ${state.ignition ? tt("hud.ignOn") : tt("hud.ignOff")} · ` +
    `${traccarHud} · ${state.sat ?? 0} sat`;

  document.getElementById("gRpm").textContent = state.rpm ?? 0;
  document.getElementById("gFuel").textContent =
    state.fuel_percent != null ? Number(state.fuel_percent).toFixed(1) : "—";

  routeSource = state.route_source ?? routeSource;
  const btnReplay = document.getElementById("btnReplayGpx");
  if (btnReplay) {
    btnReplay.disabled = !state.route_loaded || routeSource !== "gpx";
  }

  suppressDigitalEvents = true;
  const digIds = { door: "toggleDoor", in1: "toggleIn1", in2: "toggleIn2", in3: "toggleIn3", in4: "toggleIn4" };
  Object.entries(digIds).forEach(([k, id]) => {
    const el = document.getElementById(id);
    if (el) el.checked = !!state[k];
  });
  suppressDigitalEvents = false;

  suppressToggleEvents = true;
  document.getElementById("toggleIgnition").checked = !!state.ignition;
  document.getElementById("toggleBlocked").checked = !!state.blocked;
  document.getElementById("toggleExternal").checked = Boolean(state.external_power_connected);
  suppressToggleEvents = false;

  setPill(
    "pillIgnition",
    state.ignition ? tt("dock.ignOn") : tt("dock.ignOff"),
    state.ignition ? "on" : "off"
  );
  setPill(
    "pillBlocked",
    state.blocked ? tt("dock.blocked") : tt("dock.free"),
    state.blocked ? "warn" : "on"
  );

  let tripLabel = tt("pills.stopped");
  let tripCls = "off";
  if (state.trip_active ?? state.running) {
    tripLabel = state.paused ? tt("pills.paused") : tt("pills.enRoute");
    tripCls = state.paused ? "warn" : "active";
  }
  setPill("pillTrip", tripLabel, tripCls);

  setPill(
    "pillStream",
    state.streaming ? tt("pills.online") : tt("pills.offline"),
    state.streaming ? "on" : "off"
  );

  if (state.traccar_ok === true) {
    setPill("pillTraccar", `Traccar ${state.traccar_status}`, "on");
  } else if (state.traccar_ok === false) {
    setPill("pillTraccar", state.traccar_error || tt("pills.traccarErr"), "off");
  } else {
    setPill("pillTraccar", tt("pills.traccarDash"), "");
  }

  if (state.lat != null && vehicleMarker) {
    updateVehicleOnMap(state.lat, state.lon, state.bearing ?? 0, state.speed_kmh ?? 0);
  }

  if (state.trail?.length) drawTrail(state.trail);

  updateTripButtons(state);
  lastGaugeState = state;
}

function drawTrail(trail) {
  if (!map) return;
  if (!trailLayer) {
    trailLayer = L.polyline([], {
      color: "#22d3ee",
      weight: 5,
      opacity: 0.55,
      lineCap: "round",
      lineJoin: "round",
    }).addTo(map);
  }
  trailLayer.setLatLngs(trail.map(([lat, lon]) => [lat, lon]));
  trailLayer.bringToBack();
}

function drawRoute(geojson) {
  if (!map) return;
  clearRouteLine();
  if (!geojson) {
    updateRouteUI();
    return;
  }
  routeCalculated = true;

  routeOutlineLayer = L.geoJSON(geojson, {
    style: { color: "#1e3a8a", weight: 10, opacity: 0.85, lineCap: "round", lineJoin: "round" },
  }).addTo(map);

  routeLayer = L.geoJSON(geojson, {
    style: { color: "#60a5fa", weight: 6, opacity: 0.95, lineCap: "round", lineJoin: "round" },
  }).addTo(map);

  routeLayer.bringToFront();
  if (trailLayer) trailLayer.bringToFront();
  if (vehicleMarker) vehicleMarker.setZIndexOffset(2000);

  map.fitBounds(routeLayer.getBounds(), { padding: [56, 56], maxZoom: 15 });
  updateRouteUI();
}

function redrawWaypoints() {
  if (!map) return;
  if (waypointLayer) map.removeLayer(waypointLayer);
  waypointLayer = L.layerGroup(
    waypoints.map((wp, i) => {
      const num = i + 1;
      const tip =
        i === 0
          ? tt("route.origin")
          : i === waypoints.length - 1 && waypoints.length > 1
            ? tt("route.dest")
            : tt("route.stop", { n: i });
      return L.marker(wp, {
        icon: L.divIcon({
          className: "waypoint-marker",
          html: `<div class="waypoint-pin"><span>${num}</span></div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        }),
        zIndexOffset: 400 + i,
      }).bindTooltip(`${num}. ${tip}`, { direction: "top", offset: [0, -12] });
    })
  ).addTo(map);
  updateRouteUI();
}

function undoLastWaypoint() {
  if (!waypoints.length) return;
  waypoints.pop();
  clearRouteLine();
  redrawWaypoints();
  log(tt("log.wpRemoved"));
}

function updateVehicleOnMap(lat, lon, bearing, speedKmh) {
  const moving = speedKmh > 2;
  const el = vehicleMarker.getElement();
  if (el) {
    const wrap = el.querySelector(".vehicle-marker-wrap");
    const arrow = el.querySelector(".vehicle-arrow");
    if (wrap) wrap.classList.toggle("moving", moving);
    if (arrow) arrow.style.transform = `rotate(${bearing}deg)`;
  }

  const from = lastVehiclePos || vehicleMarker.getLatLng();
  const distChanged =
    Math.abs(from.lat - lat) > 1e-7 || Math.abs(from.lng - lon) > 1e-7;

  if (!distChanged) return;

  if (markerAnimFrame) cancelAnimationFrame(markerAnimFrame);
  const start = performance.now();
  const duration = moving ? 480 : 200;
  const lat0 = from.lat;
  const lng0 = from.lng;

  function step(now) {
    const t = Math.min(1, (now - start) / duration);
    const ease = 1 - (1 - t) ** 3;
    const la = lat0 + (lat - lat0) * ease;
    const lo = lng0 + (lon - lng0) * ease;
    vehicleMarker.setLatLng([la, lo]);
    if (followVehicle && t > 0) {
      map.panTo([la, lo], { animate: t > 0.05, duration: 0.35 });
    }
    if (t < 1) markerAnimFrame = requestAnimationFrame(step);
    else lastVehiclePos = L.latLng(lat, lon);
  }
  markerAnimFrame = requestAnimationFrame(step);
}

function initMap() {
  map = L.map("map", {
    zoomControl: false,
    attributionControl: true,
  }).setView(DEFAULT_CENTER, 13);
  map.doubleClickZoom.disable();

  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.control.scale({ metric: true, imperial: false, position: "bottomleft" }).addTo(map);

  // Apenas provedores gratuitos, sem API key (CARTO/Stadia exigem chave).
  const osmRuas = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  });

  const osmHot = L.tileLayer("https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", {
    maxZoom: 20,
    subdomains: "abc",
    attribution:
      '&copy; OpenStreetMap · tiles <a href="https://www.openstreetmap.fr/">OSM France</a> (HOT)',
  });

  mapTileLayers = { osm: osmRuas, hot: osmHot };
  activeMapTile = osmRuas;
  osmRuas.addTo(map);

  const icon = L.divIcon({
    className: "vehicle-icon-root",
    html: `<div class="vehicle-marker-wrap">
      <div class="vehicle-pulse"></div>
      <div class="vehicle-arrow">${VEHICLE_SVG}</div>
    </div>`,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  });
  vehicleMarker = L.marker(DEFAULT_CENTER, { icon, zIndexOffset: 2000 })
    .addTo(map)
    .bindTooltip(tt("map.vehicleTooltip"), { direction: "top", offset: [0, -18] });

  lastVehiclePos = L.latLng(DEFAULT_CENTER[0], DEFAULT_CENTER[1]);

  map.on("click", (e) => {
    if (routeCalculated) clearRouteLine();
    waypoints.push([e.latlng.lat, e.latlng.lng]);
    redrawWaypoints();
    log(tt("log.wpAdded", { n: waypoints.length }));
  });

  map.on("dblclick", (e) => {
    L.DomEvent.stopPropagation(e);
    undoLastWaypoint();
  });

  document.getElementById("btnFollow").addEventListener("click", () => {
    followVehicle = !followVehicle;
    document.getElementById("btnFollow").classList.toggle("active", followVehicle);
    if (followVehicle && lastVehiclePos) {
      map.flyTo(lastVehiclePos, Math.max(map.getZoom(), 16), { duration: 0.6 });
    }
  });

  document.getElementById("btnCenterVehicle").addEventListener("click", () => {
    const ll = vehicleMarker.getLatLng();
    map.flyTo(ll, Math.max(map.getZoom(), 15), { duration: 0.55 });
  });
}

async function loadViolations() {
  const data = await api("/api/violations");
  violationsCatalog = data.violations || [];
  const sel = document.getElementById("violationSelect");
  sel.innerHTML = "";
  violationsCatalog.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v.id;
    opt.textContent = violationLabel(v.id);
    sel.appendChild(opt);
  });
  updateViolationHint();
}

function updateViolationHint() {
  const id = document.getElementById("violationSelect").value;
  const v = violationsCatalog.find((x) => x.id === id);
  document.getElementById("violationHint").textContent = v ? violationDesc(v.id) : "";
}

async function loadStatus() {
  const state = await api("/api/status");
  applySettingsForm(state.settings);
  updateGauges(state);
  if (state.route) drawRoute(state.route);
  if (state.trail) drawTrail(state.trail);
}

function applySettingsForm(s) {
  if (!s) return;
  document.getElementById("traccarUrl").value = s.traccar_url || "";
  document.getElementById("deviceId").value = s.device_id || "";
  document.getElementById("intervalOn").value = s.interval_ignition_on ?? s.interval_seconds ?? 5;
  document.getElementById("intervalOff").value = s.interval_ignition_off ?? 60;
  document.getElementById("osrmUrl").value = s.osrm_base_url || "";
  document.getElementById("traffic").value = s.traffic_profile || "normal";
  if (s.cell_mcc != null) document.getElementById("cellMcc").value = s.cell_mcc;
  if (s.cell_mnc != null) document.getElementById("cellMnc").value = s.cell_mnc;
  if (s.cell_lac != null) document.getElementById("cellLac").value = s.cell_lac;
  if (s.cell_cid != null) document.getElementById("cellCid").value = s.cell_cid;
  if (s.cell_wifi_mac != null) document.getElementById("cellWifiMac").value = s.cell_wifi_mac;
  if (s.driver_unique_id != null) document.getElementById("driverUniqueId").value = s.driver_unique_id;
  if (s.map_style) {
    document.getElementById("mapStyle").value = s.map_style;
    setMapStyle(s.map_style);
  }
  if (s.default_lat && s.default_lon && !waypoints.length) {
    map.setView([s.default_lat, s.default_lon], 12);
    vehicleMarker.setLatLng([s.default_lat, s.default_lon]);
  }
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/live`);

  ws.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.type === "ping") return;
    if (data.type === "status") {
      applySettingsForm(data.settings);
      updateGauges(data);
      if (data.route) drawRoute(data.route);
      return;
    }
    if (data.type === "tick") {
      updateGauges(data);
      if (data.sent && data.reason === "ignition") {
        const ok = data.traccar_ok ? `HTTP ${data.traccar_status}` : data.traccar_error;
        const iv = data.report_interval_s ?? "?";
        log(tt("log.ignSend", { iv, ok }), data.traccar_ok ? "ok" : "err");
      } else if (data.sent && data.reason && data.reason !== "tick") {
        const ok = data.traccar_ok ? `HTTP ${data.traccar_status}` : data.traccar_error;
        log(tt("log.sendReason", { reason: data.reason, ok }), data.traccar_ok ? "ok" : "err");
      }
      const now = Date.now();
      if (data.sent && data.reason === "tick" && now - lastLogTick > 20000) {
        lastLogTick = now;
        const ok = data.traccar_ok ? `HTTP ${data.traccar_status}` : data.traccar_error;
        log(tt("log.heartbeat", { ok, speed: data.speed_kmh }));
      }
    }
  };

  ws.onclose = () => {
    log(tt("log.wsDown"), "err");
    setTimeout(connectWs, 2000);
  };
}

document.getElementById("btnSaveSettings").addEventListener("click", async () => {
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        traccar_url: document.getElementById("traccarUrl").value,
        device_id: document.getElementById("deviceId").value,
        interval_ignition_on: Number(document.getElementById("intervalOn").value),
        interval_ignition_off: Number(document.getElementById("intervalOff").value),
        interval_seconds: Number(document.getElementById("intervalOn").value),
        osrm_base_url: document.getElementById("osrmUrl").value,
        traffic_profile: document.getElementById("traffic").value,
        cell_mcc: Number(document.getElementById("cellMcc").value),
        cell_mnc: Number(document.getElementById("cellMnc").value),
        cell_lac: Number(document.getElementById("cellLac").value),
        cell_cid: Number(document.getElementById("cellCid").value),
        cell_wifi_mac: document.getElementById("cellWifiMac").value.trim(),
        driver_unique_id: document.getElementById("driverUniqueId").value.trim(),
        map_style: document.getElementById("mapStyle").value,
        persist: true,
      }),
    });
    log(tt("log.settingsSaved"), "ok");
  } catch (e) {
    log(e.message, "err");
  }
});

document.getElementById("btnTestTraccar").addEventListener("click", () =>
  api("/api/traccar/test", { method: "POST" })
    .then((d) => {
      log(tt("log.traccarTestOk", { code: d.status_code }), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(tt("log.traccarTestFail", { msg: e.message }), "err"))
);

document.getElementById("toggleIgnition").addEventListener("change", (ev) => {
  if (suppressToggleEvents) return;
  api("/api/vehicle/ignition", {
    method: "POST",
    body: JSON.stringify({ on: ev.target.checked }),
  })
    .then((d) => {
      log(ev.target.checked ? tt("log.ignOn") : tt("log.ignOff"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(e.message, "err"));
});

document.getElementById("toggleBlocked").addEventListener("change", (ev) => {
  if (suppressToggleEvents) return;
  api("/api/vehicle/blocked", {
    method: "POST",
    body: JSON.stringify({ on: ev.target.checked }),
  })
    .then((d) => {
      log(ev.target.checked ? tt("log.blocked") : tt("log.unblocked"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(e.message, "err"));
});

document.getElementById("btnSetOdometer").addEventListener("click", async () => {
  const raw = document.getElementById("odometerInput").value;
  const km = Number(raw);
  if (!Number.isFinite(km) || km < 0) {
    log(tt("log.odoInvalid"), "err");
    return;
  }
  try {
    const d = await api("/api/vehicle/odometer", {
      method: "POST",
      body: JSON.stringify({ km }),
    });
    log(tt("log.odoSet", { km }), "ok");
    if (d.state) updateGauges(d.state);
  } catch (e) {
    log(e.message, "err");
  }
});

document.getElementById("toggleExternal").addEventListener("change", (ev) => {
  if (suppressToggleEvents) return;
  api("/api/vehicle/external-power", {
    method: "POST",
    body: JSON.stringify({ connected: ev.target.checked }),
  })
    .then((d) => {
      log(ev.target.checked ? tt("log.extOn") : tt("log.extOff"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(e.message, "err"));
});

document.getElementById("btnStart").addEventListener("click", () =>
  api("/api/simulation/start", { method: "POST" })
    .then((d) => {
      const wasResume = document.getElementById("btnStart")?.classList.contains("trip-resume");
      log(wasResume ? tt("log.tripResumed") : tt("log.tripStarted"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(tt("log.startFail", { msg: e.message }), "err"))
);

document.getElementById("btnStop").addEventListener("click", () =>
  api("/api/simulation/stop", { method: "POST" })
    .then((d) => {
      log(tt("log.tripStopped"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(e.message, "err"))
);

document.getElementById("btnPause").addEventListener("click", () =>
  api("/api/simulation/pause", { method: "POST" })
    .then((d) => {
      log(d.paused ? tt("log.tripPaused") : tt("log.tripUnpaused"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(e.message, "err"))
);

document.getElementById("btnUndoWp")?.addEventListener("click", () => undoLastWaypoint());

document.getElementById("btnClearWaypoints").addEventListener("click", () => {
  waypoints.length = 0;
  clearRouteLine();
  redrawWaypoints();
  log(tt("log.cleared"));
});

async function loadOsrmRoute() {
  if (waypoints.length < 2) {
    log(tt("log.osrmNeed2"), "err");
    return;
  }
  try {
    const data = await api("/api/route/osrm", {
      method: "POST",
      body: JSON.stringify({ waypoints }),
    });
    drawRoute(data.route);
    log(tt("log.osrmOk", { km: (data.length_m / 1000).toFixed(1) }), "ok");
    await loadStatus();
  } catch (e) {
    log(tt("log.osrmFail", { msg: e.message }), "err");
  }
}

document.getElementById("btnLoadOsrm")?.addEventListener("click", () => loadOsrmRoute());

document.getElementById("gpxFile").addEventListener("change", async (ev) => {
  const file = ev.target.files?.[0];
  if (!file) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/route/gpx", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data, res.statusText));
    drawRoute(data.route);
    log(tt("log.gpxOk", { km: (data.length_m / 1000).toFixed(1) }), "ok");
    await loadStatus();
  } catch (e) {
    log(tt("log.gpxFail", { msg: e.message }), "err");
  }
  ev.target.value = "";
});

document.getElementById("violationSelect").addEventListener("change", updateViolationHint);

document.getElementById("btnFireViolation").addEventListener("click", () => {
  const id = document.getElementById("violationSelect").value;
  api("/api/violations/trigger", { method: "POST", body: JSON.stringify({ id }) })
    .then((d) =>
      log(tt("log.violation", { label: violationLabel(d.id || id), alarm: d.alarm }), "ok")
    )
    .catch((e) => log(e.message, "err"));
});

function setMapStyle(style) {
  if (!map || !mapTileLayers.osm) return;
  const next = style === "hot" ? mapTileLayers.hot : mapTileLayers.osm;
  if (activeMapTile === next) return;
  if (activeMapTile) map.removeLayer(activeMapTile);
  next.addTo(map);
  activeMapTile = next;
}

function initTheme() {
  const saved = localStorage.getItem("sim-theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  document.getElementById("btnTheme")?.addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme") || "dark";
    const next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("sim-theme", next);
  });
}

function bindDigitalToggles() {
  const keys = [
    ["toggleDoor", "door"],
    ["toggleIn1", "in1"],
    ["toggleIn2", "in2"],
    ["toggleIn3", "in3"],
    ["toggleIn4", "in4"],
  ];
  keys.forEach(([id, key]) => {
    document.getElementById(id)?.addEventListener("change", (ev) => {
      if (suppressDigitalEvents) return;
      api("/api/vehicle/digital", {
        method: "POST",
        body: JSON.stringify({ [key]: ev.target.checked }),
      })
        .then((d) => {
          log(tt("log.digital", { key, state: ev.target.checked ? "ON" : "OFF" }), "ok");
          if (d.state) updateGauges(d.state);
        })
        .catch((e) => log(e.message, "err"));
    });
  });
}

document.getElementById("mapStyle")?.addEventListener("change", (ev) => {
  setMapStyle(ev.target.value);
});

document.getElementById("btnExportTrail")?.addEventListener("click", () => {
  window.location.href = "/api/trail/export.gpx";
});

document.getElementById("btnReplayGpx")?.addEventListener("click", () =>
  api("/api/replay/start", { method: "POST" })
    .then((d) => {
      log(tt("log.replayStart"), "ok");
      if (d.state) updateGauges(d.state);
    })
    .catch((e) => log(tt("log.replayFail", { msg: e.message }), "err"))
);

document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !/input|textarea|select/i.test(document.activeElement?.tagName)) {
    e.preventDefault();
    document.getElementById("btnPause")?.click();
  }
});

window.i18n.initLangSwitcher();
window.addEventListener("xtraccar:lang", () => {
  if (lastGaugeState) updateGauges(lastGaugeState);
  updateRouteUI();
  loadViolations().catch(() => {});
  refreshVehicleTooltip();
});

initTheme();
initShellUI();
initMap();
bindDigitalToggles();
updateRouteUI();
loadViolations().catch((e) => log(e.message, "err"));
loadStatus().catch((e) => log(e.message, "err"));
connectWs();

fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    const el = document.getElementById("footerVersion");
    if (el && h.version) el.textContent = `v${h.version}`;
  })
  .catch(() => {});
