"""
Build the MQTT message log from REAL OSM areas + REAL OSM signals.

  Areas   = 95 real OSM suburbs (place=suburb)               -> traffic/{city}/{area}/...
  Signals = 1,377 real OSM traffic_signals nodes             -> .../{signal_id}/...
  Data    = each signal matched to nearby SUMO roads; that road's simulated
            speed/density per 5-min interval becomes the signal's detections.

Topics:
  traffic/{city}/{area}/{signal_id}/data        detection payloads
  traffic/{city}/{area}/{signal_id}/heartbeat   liveness pings
  traffic/{city}/{area}/{signal_id}/alert       congestion / incident (high priority)
  traffic/{city}/{area}/{signal_id}/frames      evidentiary frame references
  management/{city}/{area}/{signal_id}/status   node -> server status (retained)

Outputs in mqtt_logs/: mqtt_log.jsonl, by_type/*.jsonl, signals.json,
areas.json, summary.json
"""
import sys, os, json, math, hashlib, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from xml.etree.ElementTree import iterparse

sys.path.insert(0, "/opt/homebrew/opt/sumo/share/sumo/tools")
import sumolib

CITY            = "bengaluru"
SIM_START_CLOCK = "00:00:00"
SIM_DATE        = "2026-06-15"
IST             = timezone(timedelta(hours=5, minutes=30))
INTERVAL_SECS   = 300
JAM_REL         = 0.25
HEAVY_REL       = 0.40
MATCH_RADIUS    = 45.0     # metres: road counts as an approach if it ends this close
CELL            = 50.0     # spatial-grid cell size (metres)

OUTDIR = "mqtt_logs"
os.makedirs(f"{OUTDIR}/by_type", exist_ok=True)

def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s or "area"

def bearing_label(p0, p1):
    dx, dy = p1[0]-p0[0], p1[1]-p0[1]
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return ["N","NE","E","SE","S","SW","W","NW"][round(ang/45) % 8]

def congestion_level(rel):
    if rel >= 0.70: return "free"
    if rel >= HEAVY_REL: return "moderate"
    if rel >= JAM_REL: return "heavy"
    return "jam"

def iso(sim_t):
    base = datetime.fromisoformat(f"{SIM_DATE}T{SIM_START_CLOCK}").replace(tzinfo=IST)
    return (base + timedelta(seconds=sim_t)).isoformat()

def utc_z(sim_t):
    base = datetime.fromisoformat(f"{SIM_DATE}T{SIM_START_CLOCK}").replace(tzinfo=IST)
    return (base + timedelta(seconds=sim_t)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def pt_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx-ax, by-ay
    if dx == 0 and dy == 0:
        return math.hypot(px-ax, py-ay)
    t = ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))
    return math.hypot(px-(ax+t*dx), py-(ay+t*dy))

# ── Load real OSM areas (suburbs) ──────────────────────────────────────────
print("Loading OSM suburbs…", flush=True)
suburbs = []
seen_slugs = {}
for f in json.load(open("osm_suburbs.geojson"))["features"]:
    name = f["properties"].get("name")
    if not name:
        continue
    lon, lat = f["geometry"]["coordinates"]
    slug = slugify(name)
    if slug in seen_slugs:
        seen_slugs[slug] += 1
        slug = f"{slug}_{seen_slugs[slug]}"
    else:
        seen_slugs[slug] = 1
    suburbs.append({"name": name, "slug": slug, "lon": lon, "lat": lat})
print(f"  {len(suburbs)} suburbs", flush=True)

def nearest_area(lon, lat):
    best, bd = None, 1e18
    for s in suburbs:
        d = (lon-s["lon"])**2 + (lat-s["lat"])**2
        if d < bd:
            best, bd = s, d
    return best["slug"]

# ── Load network + build spatial grid index over all edges ─────────────────
print("Loading network…", flush=True)
net = sumolib.net.readNet("bengaluru.net.xml")

print("Building spatial grid index…", flush=True)
grid = defaultdict(set)
def gcell(x, y): return (int(x // CELL), int(y // CELL))
for edge in net.getEdges():
    shp = edge.getShape()
    eid = edge.getID()
    pts = []
    for i in range(len(shp)-1):
        ax, ay = shp[i]; bx, by = shp[i+1]
        pts.append((ax, ay))
        d = math.hypot(bx-ax, by-ay)
        if d > CELL:
            n = int(d // CELL)
            for k in range(1, n+1):
                t = k/(n+1)
                pts.append((ax+(bx-ax)*t, ay+(by-ay)*t))
    pts.append(shp[-1])
    for p in pts:
        grid[gcell(*p)].add(eid)
print(f"  index cells: {len(grid):,}", flush=True)

# ── Load real OSM signals, match each to approaches + area ─────────────────
print("Loading OSM traffic signals + matching to roads…", flush=True)
osm_signals = json.load(open("osm_signals.geojson"))["features"]

signals = {}            # "area/signal_id" -> meta
edge_to_signals = set() # edges used as approaches (streaming filter)
area_counters = defaultdict(int)
unmatched = 0

for f in osm_signals:
    osm_id = f.get("id") or f["properties"].get("@id") or "unknown"
    lon, lat = f["geometry"]["coordinates"]
    x, y = net.convertLonLat2XY(lon, lat)

    # candidate edges from this + neighbouring cells
    cx, cy = gcell(x, y)
    cand = set()
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cand |= grid.get((cx+dx, cy+dy), set())

    # keep edges whose END vertex is within radius (they flow INTO the signal)
    approaches = []
    for eid in cand:
        e = net.getEdge(eid)
        shp = e.getShape()
        ex, ey = shp[-1]
        if math.hypot(x-ex, y-ey) <= MATCH_RADIUS:
            head = bearing_label(shp[-2], shp[-1]) if len(shp) >= 2 else "?"
            approaches.append({
                "approach_id": head, "edge": eid, "heading": head,
                "lanes": e.getLaneNumber(), "length_m": round(e.getLength(), 1),
                "freeflow_kmh": round(e.getSpeed()*3.6, 1),
            })
            edge_to_signals.add(eid)

    area = nearest_area(lon, lat)
    area_counters[area] += 1
    signal_id = f"signal_{area_counters[area]:03d}"
    if not approaches:
        unmatched += 1

    signals[f"{area}/{signal_id}"] = {
        "osm_node_id": str(osm_id),
        "city": CITY, "area": area, "signal_id": signal_id,
        "lat": round(lat, 6), "lon": round(lon, 6),
        "n_approaches": len(approaches),
        "approaches": approaches,
        "fw_version": "twin-1.0.0",
    }

print(f"  {len(signals)} signals across {len(area_counters)} areas "
      f"({unmatched} with no nearby road)", flush=True)

# ── Message writers ────────────────────────────────────────────────────────
log_main = open(f"{OUTDIR}/mqtt_log.jsonl", "w")
log_by_type = {tp: open(f"{OUTDIR}/by_type/{tp}.jsonl", "w")
               for tp in ["data","heartbeat","alert","frames","status"]}
counts = {tp: 0 for tp in log_by_type}

def emit(topic, payload, qos, retain, msg_type, sim_t):
    rec = {"ts": iso(sim_t), "sim_t": sim_t, "topic": topic,
           "qos": qos, "retain": retain, "payload": payload}
    line = json.dumps(rec, separators=(",", ":"))
    log_main.write(line + "\n")
    log_by_type[msg_type].write(line + "\n")
    counts[msg_type] += 1

# retained status (node identity) at boot
for key, m in signals.items():
    emit(f"management/{CITY}/{m['area']}/{m['signal_id']}/status", {
        "signal_id": m["signal_id"], "area": m["area"], "city": CITY,
        "osm_node_id": m["osm_node_id"], "lat": m["lat"], "lon": m["lon"],
        "n_approaches": m["n_approaches"], "fw_version": m["fw_version"],
        "health": "online", "detector_mode": "auto",
        "config_version": 1, "boot_ts": iso(0),
    }, qos=1, retain=True, msg_type="status", sim_t=0)

# ── Stream edge data, emit per-signal payloads per interval ────────────────
print("Streaming edge data into per-signal payloads…", flush=True)
alert_seq = 0
edge_stats = {}

def flush_interval(begin):
    global alert_seq
    for key, m in signals.items():
        if not m["approaches"]:
            continue
        area, sid = m["area"], m["signal_id"]
        # aggregate this signal's approaches into one junction reading
        present = 0.0      # vehicles currently at the junction (density x length)
        queue = 0.0        # vehicles slowed/stopped (congested fraction of present)
        spd_sum = spd_w = 0.0
        occ_sum = occ_n = 0
        worst_rel, worst_app = 1.0, None
        for app in m["approaches"]:
            st = edge_stats.get(app["edge"])
            if not st:
                continue
            spd, rel, dens, occ = st
            veh = dens * app["length_m"] / 1000.0
            present += veh
            queue += veh * max(0.0, 1.0 - rel)
            spd_sum += spd * veh; spd_w += veh
            occ_sum += occ; occ_n += 1
            if rel < worst_rel:
                worst_rel, worst_app = rel, app
        if occ_n == 0:
            continue  # no simulated data at this signal this interval

        avg_speed = round(spd_sum / spd_w, 1) if spd_w > 0 else round(
            sum(edge_stats[a["edge"]][0] for a in m["approaches"]
                if a["edge"] in edge_stats) / occ_n, 1)

        emit(f"traffic/{CITY}/{area}/{sid}/data", {
            "timestamp": utc_z(begin),
            "vehicle_count": int(round(present)),
            "avg_speed": avg_speed,
            "queue_length": int(round(queue)),
            "occupancy": round(occ_sum / occ_n, 1),
            "pedestrian_count": None,    # filled by real devices later
            "weather": None,             # filled by weather feed later
        }, qos=1, retain=False, msg_type="data", sim_t=begin)

        emit(f"traffic/{CITY}/{area}/{sid}/heartbeat", {
            "signal_id": sid, "status": "online", "uptime_s": begin,
            "fw_version": m["fw_version"], "detectors_ok": occ_n,
            "detectors_total": m["n_approaches"],
        }, qos=0, retain=False, msg_type="heartbeat", sim_t=begin)

        if worst_rel < JAM_REL and worst_app is not None:
            alert_seq += 1
            aid = f"alt_{alert_seq:06d}"
            emit(f"traffic/{CITY}/{area}/{sid}/alert", {
                "alert_id": aid, "signal_id": sid, "area": area,
                "type": "congestion", "severity": "high",
                "approach": worst_app["approach_id"], "heading": worst_app["heading"],
                "measured_speed_kmh": edge_stats[worst_app["edge"]][0],
                "relative_speed": round(worst_rel, 3), "threshold_rel": JAM_REL,
                "ts": iso(begin),
            }, qos=2, retain=False, msg_type="alert", sim_t=begin)

            fid = hashlib.sha1(f"{sid}{begin}{aid}".encode()).hexdigest()[:16]
            emit(f"traffic/{CITY}/{area}/{sid}/frames", {
                "frame_id": fid, "alert_id": aid, "signal_id": sid, "area": area,
                "uri": f"s3://traffic-evidence/{CITY}/{area}/{sid}/{fid}.jpg",
                "captured_ts": iso(begin), "resolution": "1920x1080", "sha1": fid,
                "note": "reference only — raw bytes transferred out-of-band",
            }, qos=1, retain=False, msg_type="frames", sim_t=begin)

for event, elem in iterparse("edgedata.out.xml", events=("start", "end")):
    if event == "start" and elem.tag == "interval":
        ib = int(float(elem.get("begin", 0))); edge_stats = {}
    elif event == "start" and elem.tag == "edge":
        eid = elem.get("id")
        if eid not in edge_to_signals:
            continue
        spd = float(elem.get("speed", 0) or 0)
        if spd <= 0:
            continue
        e = net.getEdge(eid); ff = e.getSpeed()
        edge_stats[eid] = (round(spd*3.6, 1), spd/ff if ff > 0 else 0.0,
                           round(float(elem.get("density", 0) or 0), 2),
                           round(float(elem.get("occupancy", 0) or 0), 2))
    elif event == "end" and elem.tag == "interval":
        flush_interval(ib)
        print(f"  interval {ib}: data={counts['data']} alert={counts['alert']}", flush=True)
        elem.clear()

# ── Registries + summary ───────────────────────────────────────────────────
with open(f"{OUTDIR}/signals.json", "w") as fh:
    json.dump(signals, fh, indent=2, ensure_ascii=False)
with open(f"{OUTDIR}/areas.json", "w") as fh:
    json.dump({s["slug"]: {"name": s["name"], "lat": round(s["lat"],6),
                           "lon": round(s["lon"],6),
                           "signals": area_counters[s["slug"]]}
               for s in suburbs}, fh, indent=2, ensure_ascii=False)

log_main.close()
for fh in log_by_type.values():
    fh.close()

summary = {
    "city": CITY, "source": "OpenStreetMap (areas + signals)",
    "signals": len(signals), "signals_unmatched": unmatched,
    "areas_total": len(suburbs), "areas_with_signals": len(area_counters),
    "messages_total": sum(counts.values()), "messages_by_type": counts,
    "sim_window": f"{SIM_DATE} {SIM_START_CLOCK} +{INTERVAL_SECS}s intervals",
    "topic_patterns": {
        "data": f"traffic/{CITY}/{{area}}/{{signal_id}}/data",
        "heartbeat": f"traffic/{CITY}/{{area}}/{{signal_id}}/heartbeat",
        "alert": f"traffic/{CITY}/{{area}}/{{signal_id}}/alert",
        "frames": f"traffic/{CITY}/{{area}}/{{signal_id}}/frames",
        "status": f"management/{CITY}/{{area}}/{{signal_id}}/status",
    },
}
with open(f"{OUTDIR}/summary.json", "w") as fh:
    json.dump(summary, fh, indent=2)
print("\n=== DONE ===")
print(json.dumps(summary, indent=2))
