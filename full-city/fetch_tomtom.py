"""
B3 — Fetch real TomTom Traffic Flow data for major Bengaluru corridors.
Saves tomtom_flow.json for the dashboard real-traffic overlay.
"""
import json, urllib.request, urllib.parse, time

KEY = "qwPaKRlVmjKeEXKzS0NtunjKe7LSv76b"
BASE = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"

CORRIDORS = [
    # (name, lat, lon)
    ("Silk Board Junction",        12.9174, 77.6229),
    ("KR Puram Bridge",            13.0012, 77.6924),
    ("Marathahalli Bridge",        12.9558, 77.7006),
    ("Hebbal Flyover",             13.0453, 77.5974),
    ("Electronic City Toll",       12.8455, 77.6603),
    ("Whitefield ITPL",            12.9698, 77.7499),
    ("MG Road",                    12.9758, 77.6093),
    ("Bannerghatta Road",          12.8935, 77.5975),
    ("ORR Sarjapur Junction",      12.9151, 77.6845),
    ("ORR Marathahalli",           12.9490, 77.6960),
    ("ORR Bellandur",              12.9270, 77.6760),
    ("Bellary Road Hebbal",        13.0211, 77.5991),
    ("Hosur Road Bommanahalli",    12.9043, 77.6314),
    ("Old Airport Road",           12.9700, 77.6500),
    ("Tumkur Road",                13.0100, 77.5200),
    ("Manyata Tech Park",          13.0470, 77.6220),
    ("Koramangala 100ft Road",     12.9352, 77.6245),
    ("HSR Layout BDA Complex",     12.9121, 77.6446),
    ("Indiranagar 100ft Road",     12.9784, 77.6408),
    ("JP Nagar",                   12.9082, 77.5858),
    ("Yeshwanthpur Circle",        13.0274, 77.5541),
    ("Nagawara Junction",          13.0455, 77.6290),
    ("Varthur Road",               12.9454, 77.7264),
    ("NICE Road Tumkur end",       13.0600, 77.5050),
    ("Electronic City Phase 2",    12.8390, 77.6760),
    ("Outer Ring Road Kadubeesanahalli", 12.9380, 77.6950),
    ("Devarabeesanahalli",         12.9590, 77.7130),
    ("Hoskote Road KR Puram",      13.0080, 77.7120),
    ("Rajajinagar",                13.0020, 77.5540),
    ("Malleswaram",                13.0030, 77.5710),
]

results = []
print(f"Fetching {len(CORRIDORS)} corridors from TomTom Traffic Flow API…", flush=True)

for name, lat, lon in CORRIDORS:
    url = f"{BASE}?point={lat},{lon}&key={KEY}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        fd = data.get("flowSegmentData", {})
        current  = fd.get("currentSpeed", 0)
        freeflow = fd.get("freeFlowSpeed", 0)
        rel = current / freeflow if freeflow > 0 else 0.0
        results.append({
            "name": name,
            "lat": lat,
            "lon": lon,
            "current_kmh": current,
            "freeflow_kmh": freeflow,
            "relative_speed": round(rel, 3),
            "congestion_pct": round((1 - rel) * 100, 1),
        })
        status = "🟢" if rel > 0.7 else "🟡" if rel > 0.4 else "🔴"
        print(f"  {status} {name}: {current} km/h (ff {freeflow}) — {round((1-rel)*100)}% congested", flush=True)
    except Exception as e:
        print(f"  ⚠️  {name}: {e}", flush=True)
    time.sleep(0.1)  # gentle rate limiting

with open("tomtom_flow.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nWrote tomtom_flow.json — {len(results)} corridors")
