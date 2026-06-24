import json
import sys

SUMO_HOME = "/opt/homebrew/opt/sumo/share/sumo"
sys.path.insert(0, f"{SUMO_HOME}/tools")

import sumolib
from sumolib.xml import parse

print("Loading network...", flush=True)
net = sumolib.net.readNet("bengaluru.net.xml")
print("Network loaded. Parsing edge data...", flush=True)

features = []

for interval in parse("edgedata.out.xml", "interval"):
    if interval.edge is None:
        continue
    for e in interval.edge:
        if not net.hasEdge(e.id):
            continue
        edge = net.getEdge(e.id)
        free_flow = edge.getSpeed()
        mean_speed = float(e.speed) if e.speed else 0.0
        rel = mean_speed / free_flow if free_flow > 0 else 0.0
        coords = [list(net.convertXY2LonLat(x, y)) for x, y in edge.getShape()]
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "edge_id": e.id,
                "interval_begin": float(interval.begin),
                "mean_speed_ms": round(mean_speed, 2),
                "mean_speed_kmh": round(mean_speed * 3.6, 1),
                "relative_speed": round(rel, 3),
                "density": float(e.density) if e.density else None,
                "vehicle_count": int(float(e.departed)) if e.departed else 0,
            },
        })
    if len(features) % 50000 == 0 and len(features) > 0:
        print(f"  {len(features):,} features so far...", flush=True)

print(f"Writing {len(features):,} features to congestion.geojson...", flush=True)
with open("congestion.geojson", "w") as f:
    json.dump({"type": "FeatureCollection", "features": features}, f)
print("Done.")
