"""
Build analytics JSON files for the dashboard Analytics tab.
Reads per-interval stats and produces:
  - analytics_daily.json: per-5-min totals
  - analytics_areas.json: per-suburb day profile with full timelines
  - analytics_speed_dist.json: speed distribution buckets across all intervals
  - analytics_peaks.json: morning rush vs evening rush comparison
"""
import json, os, glob

INTERVAL = 300
AM_START, AM_END = 25200, 36000   # 07:00–10:00
PM_START, PM_END = 61200, 75600   # 17:00–21:00
SPEED_BINS = list(range(0, 81, 5))  # 0, 5, 10, ..., 80

areas = {}
if os.path.exists("mqtt_logs/areas.json"):
    areas = json.load(open("mqtt_logs/areas.json"))

signal_edges = {}
if os.path.exists("mqtt_logs/signals.json"):
    signals = json.load(open("mqtt_logs/signals.json"))
    for key, sig in signals.items():
        for app in sig.get("approaches", []):
            eid = app.get("edge")
            if eid:
                signal_edges[eid] = sig["area"]

stat_files = sorted(glob.glob("intervals/stats_*.json"))
print(f"Found {len(stat_files)} interval files", flush=True)

daily = []
area_data = {}
speed_dist_all = {b: 0 for b in SPEED_BINS}
am_speeds, am_jams, am_edges = [], 0, 0
pm_speeds, pm_jams, pm_edges = [], 0, 0

for fpath in stat_files:
    fname = os.path.basename(fpath)
    ib = int(fname.replace("stats_", "").replace(".json", ""))
    data = json.load(open(fpath))

    total_edges = len(data)
    speeds = [v["s"] for v in data.values() if v.get("s", 0) > 0]
    rels = [v["r"] for v in data.values()]

    avg_speed = sum(speeds) / len(speeds) if speeds else 0

    free = sum(1 for r in rels if r >= 0.7)
    moderate = sum(1 for r in rels if 0.4 <= r < 0.7)
    heavy = sum(1 for r in rels if 0.25 <= r < 0.4)
    jam = sum(1 for r in rels if r < 0.25)

    daily.append({
        "t": ib,
        "hour": round(ib / 3600, 2),
        "edges": total_edges,
        "avg_speed": round(avg_speed, 1),
        "free": free, "moderate": moderate, "heavy": heavy, "jam": jam,
    })

    for s in speeds:
        bucket = min(int(s // 5) * 5, 80)
        if bucket in speed_dist_all:
            speed_dist_all[bucket] += 1

    if AM_START <= ib < AM_END:
        am_speeds.extend(speeds)
        am_jams += jam
        am_edges = max(am_edges, total_edges)
    elif PM_START <= ib < PM_END:
        pm_speeds.extend(speeds)
        pm_jams += jam
        pm_edges = max(pm_edges, total_edges)

    for eid, vals in data.items():
        area = signal_edges.get(eid, "other")
        if area == "other":
            continue
        if area not in area_data:
            area_data[area] = {}
        if ib not in area_data[area]:
            area_data[area][ib] = {"speeds": [], "rels": [], "dens": []}
        area_data[area][ib]["speeds"].append(vals.get("s", 0))
        area_data[area][ib]["rels"].append(vals.get("r", 1))
        area_data[area][ib]["dens"].append(vals.get("d", 0))

# Area summaries with full timelines
area_summaries = []
for area, intervals in area_data.items():
    timeline = []
    all_speeds, all_rels = [], []
    for t in sorted(intervals.keys()):
        b = intervals[t]
        avg_s = sum(b["speeds"]) / len(b["speeds"]) if b["speeds"] else 0
        avg_r = sum(b["rels"]) / len(b["rels"]) if b["rels"] else 1
        density = sum(b["dens"])
        jam_count = sum(1 for r in b["rels"] if r < 0.25)
        timeline.append({
            "t": t,
            "avg_speed": round(avg_s, 1),
            "avg_rel": round(avg_r, 3),
            "density": round(density, 1),
            "roads": len(b["speeds"]),
            "jams": jam_count,
        })
        all_speeds.extend(s for s in b["speeds"] if s > 0)
        all_rels.extend(b["rels"])

    worst = min(timeline, key=lambda x: x["avg_rel"]) if timeline else None
    name = areas.get(area, {}).get("name", area)
    signals_count = areas.get(area, {}).get("signals", 0)

    area_summaries.append({
        "name": name,
        "slug": area,
        "signals": signals_count,
        "avg_speed": round(sum(all_speeds) / len(all_speeds), 1) if all_speeds else 0,
        "avg_congestion": round((1 - sum(all_rels) / len(all_rels)) * 100, 1) if all_rels else 0,
        "peak_hour": round(worst["t"] / 3600, 1) if worst else 0,
        "peak_congestion": round((1 - worst["avg_rel"]) * 100, 1) if worst else 0,
        "data_points": sum(len(intervals[t]["speeds"]) for t in intervals),
        "timeline": timeline,
    })

area_summaries.sort(key=lambda a: a["avg_congestion"], reverse=True)
top_areas = area_summaries[:30]

# Speed distribution
speed_dist = [{"bin": b, "label": f"{b}-{b+5}", "count": speed_dist_all[b]} for b in SPEED_BINS]

# Peak comparison
peaks = {
    "morning": {
        "label": "Morning Rush (07:00–10:00)",
        "avg_speed": round(sum(am_speeds) / len(am_speeds), 1) if am_speeds else 0,
        "jam_intervals": am_jams,
        "peak_roads": am_edges,
        "readings": len(am_speeds),
    },
    "evening": {
        "label": "Evening Rush (17:00–21:00)",
        "avg_speed": round(sum(pm_speeds) / len(pm_speeds), 1) if pm_speeds else 0,
        "jam_intervals": pm_jams,
        "peak_roads": pm_edges,
        "readings": len(pm_speeds),
    },
}

with open("analytics_daily.json", "w") as f:
    json.dump(daily, f, separators=(",", ":"))
print(f"Wrote analytics_daily.json ({len(daily)} intervals)", flush=True)

with open("analytics_areas.json", "w") as f:
    json.dump(top_areas, f, separators=(",", ":"))
print(f"Wrote analytics_areas.json ({len(top_areas)} areas)", flush=True)

with open("analytics_speed_dist.json", "w") as f:
    json.dump(speed_dist, f, separators=(",", ":"))
print(f"Wrote analytics_speed_dist.json", flush=True)

with open("analytics_peaks.json", "w") as f:
    json.dump(peaks, f, separators=(",", ":"))
print(f"Wrote analytics_peaks.json", flush=True)
