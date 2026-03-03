# 🌊 Sierra Streamflow Monitor

> *"We're gonna need a bigger dataset."*

**[→ Launch the Dashboard](https://bdgroves.github.io/sierra-streamflow)**

The Sierra Nevada snowpack is a frozen reservoir sitting at 8,000 feet. Every spring, it melts. Millions of acre-feet of water surge down granite canyons, through reservoirs, past farms, and into the Central Valley — feeding cities, crops, and ecosystems all the way to the San Francisco Bay.

This dashboard puts you inside that pulse. Eight USGS stream gages. Three major watersheds. Twenty years of history. Updated every Monday.

---

## 🏔 What You're Looking At

When a storm rolls into the Sierra, the rivers don't respond immediately. Water has to fall as snow at elevation, accumulate over weeks or months, then melt when temperatures rise — or in a big atmospheric river event, it falls as rain directly onto the snowpack, triggering a rapid, powerful pulse of runoff called a **rain-on-snow event**. These are the dangerous ones.

The dashboard has two views, stacked intentionally:

**Top — 20-Year Historical Context.** Each mini chart is a spaghetti plot: every grey line is a full water year since 2005. The bold teal line is this year, right now. When it climbs above the spaghetti, something unusual is happening.

**Bottom — Past 7 Days, Storm Pulse Detail.** The same stations, zoomed into 15-minute intervals. This is where you see the actual shape of a storm moving through — the sharp rise, the peak, the recession. Real flood forecaster territory.

### How Water Moves Through the Sierra

```
SIERRA NEVADA CREST (8,000–13,000 ft)
         │
         │  ❄️ Snow accumulates Oct–Mar
         │  🌧 Rain-on-snow events possible Nov–Apr
         │  ☀️ Snowmelt dominates Apr–Jul
         ▼
    Headwater Gages  ←── First to respond (hours)
    (Hetch Hetchy, Happy Isles, Pohono Bridge)
         │
         │  Water travels through granite canyons
         │  Reservoirs buffer some of the pulse
         ▼
    Mid-watershed Gages  ←── Lag: 6–24 hours
    (Grand Canyon of the Tuolumne, LaGrange Dam)
         │
         │  Rivers braid into the foothills
         │  Irrigation diversions begin here
         ▼
    Valley Gages  ←── Lag: 1–3 days
    (Modesto, Ripon)
         │
         ▼
    San Joaquin River → San Francisco Bay
```

Watch a big storm event unfold in slow motion: a spike at Hetch Hetchy on Monday becomes a spike at Modesto by Thursday.

---

## 📡 The Eight Gages

| Station | River | Elevation | What It Tells You |
|---|---|---|---|
| **Hetch Hetchy** · `11276500` | Tuolumne | 3,860 ft | First read on Tuolumne headwaters; downstream from O'Shaughnessy Dam |
| **Grand Canyon** · `11274790` | Tuolumne | 2,200 ft | Wild canyon reach below Hetch Hetchy, before any major valley influence |
| **LaGrange Dam** · `11289650` | Tuolumne | 430 ft | Below the last major Tuolumne dam; what actually enters the valley |
| **Modesto** · `11290000` | Tuolumne | 90 ft | Main stem at the valley floor — the bottom line for Central Valley water |
| **Pohono Bridge** · `11266500` | Merced | 3,960 ft | The classic Yosemite Valley gage; spectacular in flood years |
| **Happy Isles** · `11264500` | Merced | 4,000 ft | Above Pohono, catches the raw Yosemite backcountry signal |
| **Ripon** · `11303000` | Stanislaus | 60 ft | Stanislaus River at valley floor, below New Melones Reservoir |
| **Big Creek** · `11284400` | Big Creek | 2,100 ft | Small unregulated tributary — a pure snowmelt signal, no dams |

**Why Big Creek matters:** Most Sierra gages sit downstream of major reservoirs, which smooth out the natural flood pulse. Big Creek has no dams. It responds directly and honestly to whatever the Sierra Nevada is doing. It's the canary in the watershed.

---

## 📊 Reading the Charts

### Spaghetti Plots (top section — 20-year context)

- 🩶 **Grey lines** — each one is a complete water year (2005–2024). The spread shows natural variability.
- 🟤 **Dashed brown line** — the median across all years. A typical year.
- 🟢 **Bold teal line** — this water year (Oct 2025 → now). How does this year stack up?

When the teal line rides above the spaghetti mass, this year is historically wet. When it disappears into the bottom of the bundle, drought. When it punches straight up off the top — something exceptional is happening.

### 7-Day Sparklines (bottom section — storm pulse detail)

15-minute interval data straight from the USGS sensor network. This is where you see the actual shape of a storm event — the sharp rise as rain hits the watershed, the peak, and the gradual recession as the pulse works its way downstream. Hover any point for an exact timestamp and flow reading.

**Flow status thresholds:**

| Status | Discharge | What it means |
|---|---|---|
| 🟢 NORMAL | < 200 cfs | Base flow; typical low-water conditions |
| 🟡 ELEVATED | 200–1,000 cfs | Active snowmelt or moderate storm response |
| 🟠 HIGH | 1,000–5,000 cfs | Significant flood potential; monitor closely |
| 🔴 FLOOD | > 5,000 cfs | Major flood event; infrastructure at risk |

> One cubic foot per second (cfs) = 448 gallons per minute. The Tuolumne at Modesto during a major flood can exceed 50,000 cfs — enough to fill an Olympic swimming pool every four seconds.

---

## ⚙️ How It Works

The whole thing runs on free infrastructure — no servers, no cloud bills, no subscriptions.

```
Every Monday, 6:00 AM PT
         │
         ▼
  GitHub Actions runner spins up
         │
         ▼
  scripts/fetch.py calls USGS NWIS API
  ├── Instantaneous Values (7-day, 15-min intervals)
  │     → current flow, Δ1h, Δ24h, 7-day sparklines
  ├── Daily Values (Oct 1 → yesterday)
  │     → current water year spaghetti line
  └── Daily Values × 20 water years (2005–2024)
        → historical grey spaghetti + median
         │
         ▼
  Writes data/processed/streamflow.json (~2.3 MB)
         │
         ▼
  Git commits & pushes (only if data changed)
         │
         ▼
  GitHub Pages serves index.html + JSON
         │
         ▼
  Your browser renders everything client-side with Chart.js
```

**No API keys. No paid services. No database.** Just Python's standard library hitting a public government API, and a static HTML file doing all the visualization.

### Run It Yourself

```bash
git clone https://github.com/bdgroves/sierra-streamflow.git
cd sierra-streamflow

# Fetch all data (takes ~10–15 min: 20 years × 8 stations = 160+ API calls)
python scripts/fetch.py

# Serve locally
python -m http.server 8000
# open http://localhost:8000
```

Python 3.9+ required. Zero external dependencies — pure stdlib.

---

## 🛠 Stack

| Layer | Technology |
|---|---|
| Data fetching | Python 3.12 · `urllib` · `zoneinfo` (stdlib only) |
| Data source | [USGS NWIS](https://waterservices.usgs.gov/) — public, free, no key required |
| Visualization | [Chart.js 4.4](https://www.chartjs.org/) — spaghetti plots + 7-day sparklines |
| Map | [Leaflet](https://leafletjs.com/) + [OpenStreetMap](https://www.openstreetmap.org/) tiles |
| Automation | GitHub Actions — weekly cron, no pip installs needed |
| Hosting | GitHub Pages — free, static, globally cached |
| Design | NPS-aesthetic · Playfair Display · Source Serif 4 · earthy bark-and-parchment palette |

---

## 🗺 What's Next

- [ ] **SNOTEL integration** — overlay Sierra snowpack (SWE) from NRCS; the upstream leading indicator before the pulse arrives
- [ ] **Flood stage lines** — USGS official flood stage thresholds drawn directly on each chart
- [ ] **Atmospheric river alerts** — auto-post to Bluesky when a major flow event is detected (porting from existing n8n workflow)
- [ ] **Percentile bands** — shade the 10th/90th percentile envelope around the spaghetti for drought/flood framing
- [ ] **Flow travel time** — visualize how a pulse moves from Hetch Hetchy to Modesto over 1–3 days

---

## 📄 Data & License

Stream discharge data from the **[USGS National Water Information System](https://waterservices.usgs.gov/)** — a federal public dataset, updated continuously by sensors maintained by the U.S. Geological Survey since the early 1900s.

Code: MIT — fork it, build on it, make it yours.

---

*Built to understand the water that falls on granite and ends up in a glass.*
