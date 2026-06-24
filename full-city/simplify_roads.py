"""
Convert roads_light.geojson -> roads_path.json (compact, simplified).

- Douglas-Peucker simplification (~5m tolerance) drops redundant shape points.
- Compact format: [[id, ff, [[lon,lat],...]], ...]  (no GeoJSON wrapper overhead)
Cuts file size ~3x and makes the PathLayer far cheaper to render.
"""
import json, os

EPS = 0.00005  # ~5 metres in degrees

def perp_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

def rdp(points, eps):
    if len(points) < 3:
        return points
    dmax, idx = 0, 0
    for i in range(1, len(points) - 1):
        d = perp_dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        left = rdp(points[:idx + 1], eps)
        right = rdp(points[idx:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]

print("Loading roads_light.geojson…", flush=True)
with open("roads_light.geojson") as f:
    data = json.load(f)

out = []
pts_before = pts_after = 0
for feat in data["features"]:
    coords = feat["geometry"]["coordinates"]
    pts_before += len(coords)
    simplified = rdp(coords, EPS) if len(coords) > 2 else coords
    # round to 5 decimals (~1m)
    simplified = [[round(x, 5), round(y, 5)] for x, y in simplified]
    pts_after += len(simplified)
    out.append([feat["properties"]["id"], feat["properties"]["ff"], simplified])

with open("roads_path.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))

before_mb = os.path.getsize("roads_light.geojson") // 1024 // 1024
after_mb = os.path.getsize("roads_path.json") // 1024 // 1024
print(f"  roads: {len(out):,}", flush=True)
print(f"  vertices: {pts_before:,} -> {pts_after:,} ({100*pts_after//pts_before}%)", flush=True)
print(f"  size: {before_mb} MB -> {after_mb} MB", flush=True)
print("Done.")
