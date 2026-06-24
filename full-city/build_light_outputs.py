"""
Plan A — build all lightweight dashboard outputs in one pass.

  roads_light.geojson     — arterials only (ff >= 40 km/h)
  intervals/stats_*.json  — per 5-min interval, active arterial edges only
  trips_light.json        — 1-in-4 vehicles, every 5th second (~12 MB)

Uses iterparse throughout for fast parsing of large XML files.
"""
import json, sys, os
from collections import defaultdict
from xml.etree.ElementTree import iterparse

sys.path.insert(0, "/opt/homebrew/opt/sumo/share/sumo/tools")
import sumolib

ARTERIAL_MIN_KMH = 40.0
VEHICLE_SAMPLE   = 4      # keep 1 in N vehicles
TIME_STEP_SAMPLE = 5      # keep every Nth timestep

# ── 1. Load network ────────────────────────────────────────────────────────
print("Loading network…", flush=True)
net = sumolib.net.readNet("bengaluru.net.xml")

# Pre-build arterial edge lookup: id → (ff_ms, shape)
arterials = {}
for edge in net.getEdges():
    if edge.getSpeed() * 3.6 >= ARTERIAL_MIN_KMH:
        arterials[edge.getID()] = edge
print(f"  {len(arterials):,} arterial edges", flush=True)

# ── 2. Parse edge data with iterparse ─────────────────────────────────────
print("Parsing edge data…", flush=True)
intervals = {}
current_interval_begin = None
current_dict = None

for event, elem in iterparse("edgedata.out.xml", events=("start", "end")):
    if event == "start" and elem.tag == "interval":
        current_interval_begin = int(float(elem.get("begin", 0)))
        current_dict = {}
    elif event == "start" and elem.tag == "edge" and current_dict is not None:
        eid = elem.get("id")
        if eid not in arterials:
            continue
        spd = float(elem.get("speed", 0) or 0)
        den = float(elem.get("density", 0) or 0)
        if spd <= 0 and den <= 0:
            continue
        ff = arterials[eid].getSpeed()
        rel = spd / ff if ff > 0 else 0.0
        current_dict[eid] = {
            "s": round(spd * 3.6, 1),
            "r": round(rel, 3),
            "d": round(den, 2),
        }
    elif event == "end" and elem.tag == "interval":
        intervals[current_interval_begin] = current_dict
        print(f"  interval {current_interval_begin}: {len(current_dict):,} arterial edges", flush=True)
        current_dict = None
        elem.clear()

# ── 3. Build arterial road geometry ───────────────────────────────────────
active_ids = set()
for d in intervals.values():
    active_ids.update(d.keys())
print(f"Unique active arterial edges: {len(active_ids):,}", flush=True)

features = []
for eid in sorted(active_ids):
    if eid not in arterials:
        continue
    edge = arterials[eid]
    shape = edge.getShape()
    coords = [[round(x, 5), round(y, 5)]
              for x, y in (net.convertXY2LonLat(px, py) for px, py in shape)]
    features.append({
        "type": "Feature",
        "id": eid,
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {"id": eid, "ff": round(edge.getSpeed() * 3.6, 1)},
    })

print(f"Writing roads_light.geojson ({len(features):,} edges)…", flush=True)
with open("roads_light.geojson", "w") as f:
    json.dump({"type": "FeatureCollection", "features": features}, f, separators=(',', ':'))
print(f"  → {os.path.getsize('roads_light.geojson')//1024//1024} MB", flush=True)

# ── 4. Write per-interval stats ───────────────────────────────────────────
os.makedirs("intervals", exist_ok=True)
for ib, data in sorted(intervals.items()):
    fname = f"intervals/stats_{ib:05d}.json"
    with open(fname, "w") as f:
        json.dump(data, f, separators=(',', ':'))
    print(f"  {fname}: {len(data):,} edges, {os.path.getsize(fname)//1024} KB", flush=True)

# ── 5. FCD → light trips using iterparse ─────────────────────────────────
print("Parsing FCD (sampled with iterparse)…", flush=True)
trips = defaultdict(lambda: {"path": [], "timestamps": []})
veh_seen = {}
veh_idx  = 0
step_count = 0
current_t = 0.0

for event, elem in iterparse("fcd.out.xml", events=("start", "end")):
    if event == "start" and elem.tag == "timestep":
        current_t = float(elem.get("time", 0))
        step_count += 1
        skip_step = (step_count % TIME_STEP_SAMPLE != 0)
    elif event == "start" and elem.tag == "vehicle" and not skip_step:
        vid = elem.get("id")
        if vid not in veh_seen:
            veh_seen[vid] = veh_idx
            veh_idx += 1
        if veh_seen[vid] % VEHICLE_SAMPLE == 0:
            trips[vid]["path"].append([float(elem.get("x")), float(elem.get("y"))])
            trips[vid]["timestamps"].append(current_t)
    elif event == "end" and elem.tag == "timestep":
        elem.clear()
        if step_count % 500 == 0:
            print(f"  timestep {step_count} (t={current_t:.0f}s)…", flush=True)

out = [{"vehicle": vid, **d} for vid, d in trips.items()]
print(f"Writing trips_light.json ({len(out):,} vehicles)…", flush=True)
with open("trips_light.json", "w") as f:
    json.dump(out, f, separators=(',', ':'))
print(f"  → {os.path.getsize('trips_light.json')//1024//1024} MB", flush=True)

print("All light outputs done.")
