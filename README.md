# Bengaluru Traffic Digital Twin

A whole-city traffic digital twin for Bengaluru, built on **SUMO** mesoscopic simulation and real **OpenStreetMap** infrastructure. Simulates a full **24-hour day** across the entire city road network — ~95,000 vehicle trips flowing through 526,000+ road segments — and renders an interactive analytical dashboard with live animated traffic, congestion overlays, and real-time TomTom reference data.

![Live Map — Morning Rush](full-city/docs/live-map.png)

## What it does

**Live Map** — an animated city-wide traffic visualization built with deck.gl on MapLibre GL JS. Layers include:
- **Congestion overlay** — road segments colored by speed relative to free-flow (red = jammed, green = free)
- **Vehicle trails** — animated vehicle movement using deck.gl TripsLayer
- **Heat map** — density-based hotspot visualization
- **TomTom real traffic** — 30 live corridor readings from TomTom's Traffic Flow API as ground-truth reference

The map interpolates smoothly between 5-minute simulation intervals. Playback controls include play/pause, rewind/fast-forward (5-min steps), speed selector (0.5x to 8x), and a 24-hour timeline scrubber.

![Analytics — 24h Overview](full-city/docs/analytics.png)

**Analytics** — a dedicated analytical dashboard with:
- **KPI summary** — peak active roads, city-wide avg speed, most congested area, jam-level intervals
- **Peak-hour comparison** — morning rush (07:00–10:00) vs evening rush (17:00–21:00) side-by-side
- **Congestion breakdown** — 24h stacked bar chart (free / moderate / heavy / jam) with rush-hour bands highlighted
- **Speed distribution** — histogram of road speeds across the day, color-coded by band
- **Active roads** and **average speed** line charts over 24h
- **Area leaderboard** — top 30 most congested suburbs, ranked with congestion bars
- **Area drill-down** — click any area for a dedicated view with speed profile, congestion timeline, and road activity charts

![Area Drill-down](full-city/docs/drilldown.png)

## Data provenance

Every layer is grounded in real-world data:

| Layer | Source | What's real |
|-------|--------|-------------|
| Road network | OpenStreetMap via Geofabrik | 526,000+ edges, lane counts, speed limits, junction topology |
| Traffic signals | OSM `highway=traffic_signals` | 1,377 real signal nodes across 95 real suburbs |
| Suburb boundaries | OSM `place=suburb` | 95 named suburbs (Koramangala, Whitefield, Indiranagar, ...) |
| Demand shaping | Residential → IT corridor weighting | Source weights on residential zones, destination weights on IT parks |
| Rush-hour curve | 9-window day profile | Night → AM ramp → AM peak → midday → afternoon → PM peak → PM taper → wind-down |
| Traffic physics | SUMO mesoscopic (queue-based flow) | Per-edge speed, density, occupancy every 5 minutes |
| Live reference | TomTom Traffic Flow API | 30 corridors: current speed, free-flow speed, congestion % |

The per-vehicle counts and congestion ratings are **simulated**. The roads, signals, areas, and demand shape are **real**.

## Architecture

```
OSM (Geofabrik)
  └─ osmium clip → bengaluru.osm.pbf
      └─ netconvert → bengaluru.net.xml (526K edges)
          ├─ generate_weights.py → spatial demand weights
          ├─ generate_demand.py → 95K trips (24h day curve)
          ├─ duarouter (CH, 8 threads) → bengaluru.rou.xml
          └─ sumo --mesosim → edgedata.out.xml + fcd.out.xml
              ├─ build_light_outputs.py → roads_path.json + trips_light.json + intervals/
              ├─ simplify_roads.py → Douglas-Peucker geometry reduction
              ├─ build_analytics.py → analytics JSONs (daily, areas, peaks, speed dist)
              └─ fetch_tomtom.py → tomtom_flow.json (30 live corridors)

dashboard.html ← reads all JSON artifacts, renders with deck.gl + MapLibre + ECharts
```

## Tech stack

| Component | Technology |
|-----------|-----------|
| Simulation | SUMO 1.20 (mesoscopic mode) |
| Map data | OpenStreetMap + osmium-tool |
| Routing | Contraction Hierarchies (8-thread parallel) |
| Visualization | deck.gl (PathLayer, TripsLayer, HeatmapLayer, ScatterplotLayer) |
| Basemap | MapLibre GL JS + CartoDB Voyager |
| Charts | Apache ECharts |
| Real traffic | TomTom Traffic Flow API |
| Geometry | Douglas-Peucker simplification |

## Running from a fresh clone

### Prerequisites

- **SUMO** (1.20+) with `SUMO_HOME` set
- **osmium-tool** for OSM clipping
- **Python 3.9+**
- A free **TomTom API key** (optional, for the real traffic overlay)

### macOS

```bash
brew install sumo osmium-tool
export SUMO_HOME=/opt/homebrew/opt/sumo/share/sumo
export TOMTOM_API_KEY=your_key    # optional
cd full-city
bash run_24h.sh                   # ~40 min total
```

### Linux (Ubuntu/Debian)

```bash
sudo add-apt-repository -y ppa:sumo/stable
sudo apt-get update && sudo apt-get install -y sumo sumo-tools osmium-tool
export SUMO_HOME=/usr/share/sumo
export TOMTOM_API_KEY=your_key
cd full-city
bash run_24h.sh
```

### Windows

Use WSL2 with Ubuntu and follow the Linux instructions above.

### Pipeline breakdown

| Step | Time | What |
|------|------|------|
| `generate_demand.py` | ~15 min | 9-batch 24h trip generation (~95K trips) |
| `duarouter` | ~5 min | Contraction Hierarchies routing, 8 threads |
| `sumo --mesosim` | ~13 min | 24h mesoscopic simulation |
| `build_light_outputs.py` | ~15 min | Parse FCD + edge data into dashboard JSON |
| `simplify_roads.py` | ~1 min | Douglas-Peucker road geometry |
| `build_analytics.py` | ~1 min | Analytics aggregation |
| **Total** | **~40 min** | |

### Viewing the dashboard

```bash
cd full-city
python3 -m http.server 8888
# open http://localhost:8888/dashboard.html
```

## Project structure

```
full-city/
├── dashboard.html              # Two-tab SPA (Live Map + Analytics)
├── run_24h.sh                  # One-command 24h build pipeline
├── generate_weights.py         # Spatial demand weights (residential → IT corridors)
├── generate_demand.py          # 24h rush-hour trip generation (9 time windows)
├── bengaluru.sumocfg           # SUMO simulation config
├── dump.add.xml                # Edge data collection config
├── build_light_outputs.py      # FCD + edge data → dashboard-ready JSON
├── simplify_roads.py           # Douglas-Peucker geometry reduction
├── build_analytics.py          # Analytics aggregation (daily, areas, peaks, speed dist)
├── fetch_tomtom.py             # TomTom Traffic Flow API fetch
├── osm_suburbs.geojson         # 95 real OSM suburbs (committed)
├── osm_signals.geojson         # 1,377 real OSM traffic signals (committed)
├── tomtom_flow.json            # TomTom corridor snapshot (committed)
└── docs/                       # Screenshots for README
```

## Key numbers

| Metric | Value |
|--------|-------|
| Road segments | 526,819 |
| Traffic signals | 1,377 |
| Suburbs | 95 |
| Vehicle trips (24h) | 94,943 |
| Simulation intervals | 288 (5-min each) |
| TomTom corridors | 30 |
| Dashboard data size | ~35 MB |
| Build time | ~40 min (mesoscopic) |

## Simulation approach

The 24-hour simulation uses SUMO's **mesoscopic** mode — queue-based flow dynamics rather than individual car-following physics. This is the standard approach for network-scale transport studies: it produces accurate per-edge speed, density, and travel time at ~50x the speed of full microsimulation, while maintaining real traffic physics (queue spillback, capacity constraints, signal delays).

The demand curve follows a realistic Bengaluru commute pattern:

| Window | Time | Character |
|--------|------|-----------|
| Deep night | 00:00–05:00 | Near-empty, period 8.0s |
| Morning ramp | 05:00–07:00 | Gradual build-up |
| **AM peak** | **07:00–10:00** | **Residential → IT corridor rush, period 0.3s** |
| Midday | 10:00–13:00 | Steady state |
| Afternoon | 13:00–17:00 | Moderate flow |
| **PM peak** | **17:00–21:00** | **Return commute, period 0.35s** |
| Wind-down | 21:00–24:00 | Tapering off |

Spatial demand weights bias origins toward residential zones and destinations toward IT corridors (Electronic City, Whitefield, Manyata Tech Park, ORR belt) — matching Bengaluru's actual commute geography.

## License

MIT
