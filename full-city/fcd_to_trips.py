import json
import sys
from collections import defaultdict

SUMO_HOME = "/opt/homebrew/opt/sumo/share/sumo"
sys.path.insert(0, f"{SUMO_HOME}/tools")

from sumolib.xml import parse

print("Parsing FCD output...", flush=True)
trips = defaultdict(lambda: {"path": [], "timestamps": []})
count = 0

for ts in parse("fcd.out.xml", "timestep"):
    if ts.vehicle is None:
        continue
    t = float(ts.time)
    for v in ts.vehicle:
        trips[v.id]["path"].append([float(v.x), float(v.y)])
        trips[v.id]["timestamps"].append(t)
    count += 1
    if count % 500 == 0:
        print(f"  Processed timestep {count}...", flush=True)

out = [{"vehicle": vid, **d} for vid, d in trips.items()]
print(f"Writing {len(out):,} vehicle trips to trips.json...", flush=True)
with open("trips.json", "w") as f:
    json.dump(out, f)
print("Done.")
