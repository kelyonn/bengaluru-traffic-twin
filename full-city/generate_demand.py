"""
24-hour Bengaluru demand — midnight to midnight.

Insertion rate shape:
  00:00–05:00  (0–18000s)      deep night       period 8.0   →  0.125 veh/s   2,250
  05:00–07:00  (18000–25200s)  morning ramp     period 1.5   →  0.667 veh/s   4,800
  07:00–08:00  (25200–28800s)  AM rush build    period 0.5   →  2.00  veh/s   7,200
  08:00–10:00  (28800–36000s)  AM peak          period 0.3   →  3.33  veh/s  24,000
  10:00–13:00  (36000–46800s)  midday           period 1.0   →  1.00  veh/s  10,800
  13:00–17:00  (46800–61200s)  afternoon        period 1.2   →  0.83  veh/s  12,000
  17:00–19:00  (61200–68400s)  PM peak          period 0.35  →  2.86  veh/s  20,571
  19:00–21:00  (68400–75600s)  PM taper         period 0.8   →  1.25  veh/s   9,000
  21:00–24:00  (75600–86400s)  wind-down        period 2.5   →  0.40  veh/s   4,320

Total ≈ ~95,000 trips.
"""
import subprocess, sys, os
sys.path.insert(0, "/opt/homebrew/opt/sumo/share/sumo/tools")

SUMO_TOOLS = "/opt/homebrew/opt/sumo/share/sumo/tools"
RND_TRIPS  = f"{SUMO_TOOLS}/randomTrips.py"
NET        = "bengaluru.net.xml"
WEIGHTS    = "bengaluru.weights"   # prefix — reads .src.xml and .dst.xml

# (begin, end, period, suffix)
BATCHES = [
    (0,     18000, 8.0,  "a"),   # 00:00–05:00  deep night
    (18000, 25200, 1.5,  "b"),   # 05:00–07:00  morning ramp
    (25200, 28800, 0.5,  "c"),   # 07:00–08:00  AM rush build
    (28800, 36000, 0.3,  "d"),   # 08:00–10:00  AM peak
    (36000, 46800, 1.0,  "e"),   # 10:00–13:00  midday
    (46800, 61200, 1.2,  "f"),   # 13:00–17:00  afternoon
    (61200, 68400, 0.35, "g"),   # 17:00–19:00  PM peak
    (68400, 75600, 0.8,  "h"),   # 19:00–21:00  PM taper
    (75600, 86400, 2.5,  "i"),   # 21:00–24:00  wind-down
]

trip_files = []
for begin, end, period, suffix in BATCHES:
    out_trips = f"trips_{suffix}.xml"
    print(f"Batch {suffix}: t={begin}-{end}, period={period} ({(end-begin)/period:.0f} insertions)…", flush=True)
    cmd = [
        "python3", RND_TRIPS,
        "-n", NET,
        "-o", out_trips,
        "--begin", str(begin),
        "--end",   str(end),
        "--period", str(period),
        "--fringe-factor", "3",
        "--weights-prefix", WEIGHTS,
        "--seed", str(42 + ord(suffix)),
        "--trip-attributes", 'departLane="best" departSpeed="max"',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[-300:]}", flush=True)
        sys.exit(1)
    print(f"  → {out_trips}", flush=True)
    trip_files.append(out_trips)

# Merge all trip batches into one file
print("Merging trip files…", flush=True)
import xml.etree.ElementTree as ET

root = ET.Element("trips")
total = 0
for tf in trip_files:
    tree = ET.parse(tf)
    for trip in tree.getroot().iter("trip"):
        trip.set("id", str(total))   # renumber globally to avoid id clashes
        root.append(trip)
        total += 1

tree = ET.ElementTree(root)
ET.indent(tree, space="  ")
tree.write("bengaluru.trips.xml", xml_declaration=True, encoding="unicode")
print(f"  Merged {total:,} trips → bengaluru.trips.xml", flush=True)

# Cleanup batch files
for tf in trip_files:
    os.remove(tf)

print("Done. Now run duarouter to build routes.")
