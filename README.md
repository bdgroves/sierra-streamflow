# 🌊 Sierra Streamflow Monitor

> *"We're gonna need a bigger dataset."*

**[→ Launch the Dashboard](https://bdgroves.github.io/sierra-streamflow)**

The Sierra Nevada snowpack is a frozen reservoir sitting at 8,000 feet. Every spring, it melts. Millions of acre-feet of water surge down granite canyons, through reservoirs, past farms, and into the Central Valley — feeding cities, crops, and ecosystems all the way to the San Francisco Bay.

This dashboard puts you inside that pulse. Eight USGS stream gages. Three major watersheds. Every day since October 1980. Updated every hour.

> **October 2026:** a new water year started on October 1, and NOAA has an El Niño Advisory out with better than 90% odds of a very strong event this winter. The dashboard now shows what past El Niños did to these rivers. See [What changed](#-what-changed-october-2026).

---

## 🏔 What You're Looking At

When a storm rolls into the Sierra, the rivers don't respond immediately. Water has to fall as snow at elevation, accumulate over weeks or months, then melt when temperatures rise — or in a big atmospheric river event, it falls as rain directly onto the snowpack, triggering a rapid, powerful pulse of runoff called a **rain-on-snow event**. These are the dangerous ones.

The dashboard has two views, stacked intentionally:

**Top — this water year against the record.** Each mini chart shades the 10th–90th and 25th–75th percentile of daily flow for every date since 1981, with the median dashed. The thin brown line is last water year; the red line is this one, starting over each October 1. When the red line climbs out of the shading, something unusual is happening.

**Bottom — Past 7 Days, Storm Pulse Detail.** The same stations, zoomed into 15-minute intervals. This is where you see the actual shape of a storm moving through — the sharp rise, the peak, the recession. Real flood forecaster territory.

### How Water Moves Through the Sierra

```
SIERRA NEVADA CREST (8,000–13,000 ft)
         │
         │  ❄️ Snow accumulates Oct–Mar
         │  🌧 Rain-on-snow events possible Nov–Apr
         │  ☀️ Snowmelt dominates Apr–Jul
         ▼
    Headwater Gages (no dams above)  ←── First to respond (hours)
    (Happy Isles, Pohono Bridge, Grand Canyon of the Tuolumne)
         │
         │  Water travels through granite canyons
         │  Reservoirs catch and hold the pulse
         ▼
    Below the dams  ←── released on a schedule
    (Hetch Hetchy, La Grange Dam)
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

Watch a big storm unfold in slow motion: a spike at Happy Isles shows up at Pohono Bridge a few hours later. On the Tuolumne and Stanislaus the reservoirs catch most of it, and what reaches Modesto and Ripon depends on what the dam operators release.

---

## 📡 The Eight Gages

| Station | River | Elevation | Drainage | Dams above? | What It Tells You |
|---|---|---|---|---|---|
| **Happy Isles** · `11264500` | Merced | 4,020 ft | 181 sq mi | No | Yosemite's high country before it reaches the Valley |
| **Pohono Bridge** · `11266500` | Merced | 3,865 ft | 321 sq mi | No | The bottom of Yosemite Valley; the classic flood gage |
| **Grand Canyon** · `11274790` | Tuolumne | 3,814 ft | 301 sq mi | No | The wild Tuolumne just *above* Hetch Hetchy Reservoir |
| **Hetch Hetchy** · `11276500` | Tuolumne | 3,452 ft | 457 sq mi | Yes | Below O'Shaughnessy Dam: San Francisco's releases |
| **Big Creek** · `11284400` | Big Creek | 2,568 ft | 16 sq mi | No | A small foothill creek above Whites Gulch, near Groveland |
| **La Grange Dam** · `11289650` | Tuolumne | 173 ft | 1,538 sq mi | Yes | Below Don Pedro and La Grange: what enters the valley |
| **Modesto** · `11290000` | Tuolumne | 2 ft | 1,884 sq mi | Yes | The valley floor, near the San Joaquin |
| **Ripon** · `11303000` | Stanislaus | 3 ft | 1,075 sq mi | Yes | Below New Melones, near the San Joaquin |

Elevations, coordinates and drainage areas are USGS's own site metadata. (The first version had Grand Canyon placed below Hetch Hetchy and several miles off, and the valley gages hundreds of feet too high.)

**Why the undammed gages matter:** four of these gages sit below reservoirs, so their flow is a release schedule. Happy Isles, Pohono Bridge, Grand Canyon and Big Creek have nothing above them; they respond directly and honestly to whatever the Sierra is doing. Big Creek, at 2,568 ft, is rain-fed and often dry by fall; it's the canary for foothill storms.

---

## 📊 Reading the Charts

### Percentile bands (top section)

- **Shaded bands** — the 10th–90th and 25th–75th percentile of daily mean flow for that date (±3 days), water years 1981 to last year.
- **Dashed line** — the median.
- **Thin brown line** — last water year.
- **Red line** — this water year (Oct 1 → now). The dot is the latest reading.

### 7-Day Sparklines (bottom section — storm pulse detail)

15-minute interval data straight from the USGS sensor network. This is where you see the actual shape of a storm event — the sharp rise as rain hits the watershed, the peak, and the gradual recession as the pulse works its way downstream. Hover any point for an exact timestamp and flow reading.

**Flow status — compared with the same date in every year since 1981** (the USGS WaterWatch convention):

| Status | Percentile of today's flow |
|---|---|
| Much below normal | < 10th |
| Below normal | 10th–24th |
| Normal | 25th–75th |
| Above normal | 76th–90th |
| Much above normal | > 90th |
| Record low / high | outside every year on record |

The old version used fixed thresholds for every gage (over 200 cfs was "elevated"), which called the Tuolumne at Modesto elevated on an ordinary fall day while saying nothing about a tiny creek in flood.

> One cubic foot per second (cfs) = 448 gallons per minute. The Tuolumne at Modesto during a major flood can exceed 50,000 cfs — enough to fill an Olympic swimming pool every four seconds.

---

## ⚙️ How It Works

```
Every hour (GitHub Actions)
  scripts/fetch.py
  ├── USGS Water Data APIs: last 7 days of 15-minute discharge and stage
  ├── daily means for this water year and last
  ├── each gage's full daily record since Oct 1980, cached in data/history/
  │     (re-fetched weekly, and whenever a water year completes)
  ├── percentile bands, water-year runoff, peak, and half-flow date
  └── NOAA's Oceanic Niño Index → each water year's ENSO phase
         │
         ▼
  data/processed/streamflow.json   (~70 KB, current conditions)
  data/processed/history.json      (~160 KB, bands, water years, ENSO)
         │
         ▼
  GitHub Pages serves index.html; Chart.js and Leaflet draw it in your browser
```

If a gage fails, its last good reading stays up, marked stale, and the footer says so.

**Commits only when something happens.** In quiet weather the job rewrites the data at most every 3 hours (each write is a commit). It writes immediately when a gage changes status or moves more than 10%, when NOAA posts a new ENSO outlook, at the start of each day, and every hour during a storm.

**NOAA's own words.** The El Niño card quotes the alert status and synopsis from NOAA CPC's latest [ENSO Diagnostic Discussion](https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml), read each run, so it changes when NOAA's monthly update does.

**Storm watch.** The first time a gage with no dams above it jumps in a new water year, the workflow opens a GitHub issue ("Storm watch WY2027…") with a short checklist, once per water year.

**USGS is retiring the old API.** The legacy WaterServices (`waterservices.usgs.gov`) are scheduled for decommissioning in the first quarter of 2027. The fetcher now uses the new [USGS Water Data APIs](https://api.waterdata.usgs.gov/) and keeps the legacy service only as a fallback. An optional free API key (`USGS_API_KEY` repository secret) raises the rate limit; it works without one.

### Run It Yourself

```bash
git clone https://github.com/bdgroves/sierra-streamflow.git
cd sierra-streamflow
python scripts/fetch.py          # first run pulls the full record (~1 min); later runs reuse the cache
python scripts/fetch.py --history  # force a fresh pull of the record
python -m http.server 8000       # open http://localhost:8000
```

Python 3.9+ required. Zero external dependencies — pure stdlib.

---

## 🌊 What changed (October 2026)

- **The water year rolled over and the "this year" line vanished.** The record was hard-coded as 2005–2024, so on October 1, 2026 the chart had no current year and two missing years of history. Water years are now computed from the date.
- **Status classes** are percentiles for the date instead of fixed cfs thresholds.
- **The record runs back to 1981**, cached instead of re-downloaded every hour (the old fetcher made 160+ requests per run).
- **Station metadata** corrected from USGS's site service.
- **New sections:** water year in review, El Niño and the record, and snowmelt timing.
- **New USGS API**, ahead of the WaterServices shutdown.

---

## 🛠 Stack

| Layer | Technology |
|---|---|
| Data fetching | Python 3.12 · `urllib` · `zoneinfo` (stdlib only) |
| Data sources | [USGS Water Data APIs](https://api.waterdata.usgs.gov/) (legacy WaterServices as fallback) · [NOAA CPC ONI](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt) |
| Visualization | [Chart.js 4.4](https://www.chartjs.org/) — percentile bands, 7-day pulses, ENSO bars |
| Map | [Leaflet](https://leafletjs.com/) + Esri World Topo tiles |
| Automation | GitHub Actions — hourly, no pip installs needed |
| Hosting | GitHub Pages — free, static, globally cached |
| Design | NPS-aesthetic · Playfair Display · Source Serif 4 · earthy bark-and-parchment palette |

---

## 🗺 What's Next

- [ ] **SNOTEL integration** — overlay Sierra snowpack (SWE) from NRCS; the upstream leading indicator before the pulse arrives
- [ ] **Flood stage lines** — USGS official flood stage thresholds drawn directly on each chart
- [ ] **Atmospheric river alerts** — auto-post to Bluesky when a major flow event is detected (porting from existing n8n workflow)
- [x] **Percentile bands** — 10th–90th and 25th–75th, from every year since 1981
- [ ] **Flow travel time** — visualize how a pulse moves from Hetch Hetchy to Modesto over 1–3 days

---

## 📄 Data & License

Stream discharge data from **[USGS Water Data for the Nation](https://waterdata.usgs.gov/)** — a federal public dataset, updated continuously by sensors maintained by the U.S. Geological Survey since the early 1900s.

Code: MIT — fork it, build on it, make it yours.

---

*Built to understand the water that falls on granite and ends up in a glass.*
