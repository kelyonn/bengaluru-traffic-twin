"""
B1 — Spatial demand weights from Bengaluru's real geographic zones.

Source weights (trip origins): residential suburbs — people live here.
Dest weights (trip destinations): IT corridors + CBD — people commute here.

Zones are derived from known Bengaluru geography, not random.
"""
import sys
sys.path.insert(0, "/opt/homebrew/opt/sumo/share/sumo/tools")
import sumolib

# ── Bengaluru geographic zones ─────────────────────────────────────────────
# Format: (west, south, east, north, weight_multiplier)

RESIDENTIAL_ZONES = [
    # Name                    W       S       E       N     wt
    # North — Hebbal, Yelahanka, Vidyaranyapura
    (77.55,  13.02,  77.65,  13.14,  3.0),
    # NW — Rajajinagar, Malleswaram, Yeshwanthpur
    (77.53,  12.97,  77.58,  13.03,  2.5),
    # NE — Kalyan Nagar, HBR, Ramamurthy Nagar
    (77.65,  13.00,  77.74,  13.07,  2.0),
    # East residential — Mahadevapura, KR Puram surrounds
    (77.68,  12.97,  77.78,  13.02,  2.0),
    # SE — HSR Layout, Koramangala, BTM
    (77.61,  12.90,  77.65,  12.96,  2.5),
    # South — JP Nagar, Bannerghatta Road, Gottigere
    (77.56,  12.83,  77.64,  12.91,  2.0),
    # SW — Kengeri, Uttarahalli, Padmanabhanagar
    (77.45,  12.87,  77.55,  12.98,  1.5),
    # West — Vijayanagar, Nagarbhavi
    (77.50,  12.95,  77.56,  13.01,  2.0),
]

IT_DESTINATION_ZONES = [
    # Name                    W       S       E       N     wt
    # Outer Ring Road corridor (major IT spine)
    (77.60,  12.91,  77.75,  12.97,  5.0),
    # Whitefield / ITPL
    (77.72,  12.97,  77.78,  13.01,  4.5),
    # Electronic City (Infosys, Wipro HQ)
    (77.64,  12.83,  77.70,  12.88,  4.0),
    # Manyata Tech Park / Hebbal
    (77.60,  13.03,  77.66,  13.07,  3.5),
    # CBD / MG Road / Brigade Road
    (77.59,  12.96,  77.62,  12.99,  3.0),
    # Marathahalli / Bellandur
    (77.70,  12.94,  77.75,  12.97,  3.5),
    # Koramangala (startups/offices)
    (77.61,  12.93,  77.65,  12.97,  2.5),
    # Bannerghatta Road IT corridor
    (77.59,  12.88,  77.65,  12.92,  2.5),
]

def point_weight(lon, lat, zones):
    w = 1.0
    for west, south, east, north, wt in zones:
        if west <= lon <= east and south <= lat <= north:
            w = max(w, wt)
    return w

def write_weights(edges_weights, filename):
    with open(filename, "w") as f:
        f.write('<meandata>\n  <interval begin="0" end="86400">\n')
        for eid, w in edges_weights:
            f.write(f'    <edge id="{eid}" value="{w:.3f}"/>\n')
        f.write('  </interval>\n</meandata>\n')

print("Loading network…", flush=True)
net = sumolib.net.readNet("bengaluru.net.xml")
edges = list(net.getEdges())
print(f"  {len(edges):,} edges", flush=True)

src_weights = []
dst_weights = []
skipped = 0

for edge in edges:
    shape = edge.getShape()
    mid = shape[len(shape) // 2]
    try:
        lon, lat = net.convertXY2LonLat(mid[0], mid[1])
    except Exception:
        skipped += 1
        continue

    sw = point_weight(lon, lat, RESIDENTIAL_ZONES)
    dw = point_weight(lon, lat, IT_DESTINATION_ZONES)
    src_weights.append((edge.getID(), sw))
    dst_weights.append((edge.getID(), dw))

print(f"  {skipped} edges skipped (no projection)", flush=True)

print("Writing bengaluru.weights.src.xml…", flush=True)
write_weights(src_weights, "bengaluru.weights.src.xml")
print("Writing bengaluru.weights.dst.xml…", flush=True)
write_weights(dst_weights, "bengaluru.weights.dst.xml")

# Quick sanity: count edges in each zone type
src_zoned = sum(1 for _, w in src_weights if w > 1.0)
dst_zoned = sum(1 for _, w in dst_weights if w > 1.0)
print(f"  Edges in residential zones: {src_zoned:,}")
print(f"  Edges in IT/destination zones: {dst_zoned:,}")
print("Done.")
