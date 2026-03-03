# 🏔 Sierra Streamflow Monitor

Real-time stream discharge monitoring for the Tuolumne, Merced, and Stanislaus watersheds.

**[View Live Dashboard →](https://bdgroves.github.io/sierra-streamflow)**

Updated automatically every hour via GitHub Actions.

---

## 📡 Monitored Stations

| Station | USGS ID | River | Elevation |
|---|---|---|---|
| Tuolumne R nr Hetch Hetchy | 11276500 | Tuolumne | 3,860 ft |
| Tuolumne R Grand Canyon | 11274790 | Tuolumne | 2,200 ft |
| Tuolumne R bl LaGrange Dam | 11289650 | Tuolumne | 430 ft |
| Tuolumne R at Modesto | 11290000 | Tuolumne | 90 ft |
| Merced R at Pohono Bridge (Yosemite) | 11266500 | Merced | 3,960 ft |
| Merced R at Merced Falls | 11270900 | Merced | 330 ft |
| Stanislaus R at Ripon | 11303000 | Stanislaus | 60 ft |
| Big Creek at Whites Gulch | 11284400 | Big Creek | 2,100 ft |

## 📊 Dashboard Metrics

Each station card displays:
- **Current discharge** (cfs) with trend direction
- **Flow status** — NORMAL / ELEVATED / HIGH / FLOOD
- **Δ 1h / Δ 24h** — change from 1 hour and 24 hours ago
- **7-day range** — min and max over the past week
- **vs Last Year** — % above/below same date last year
- **7-day sparkline** — discharge time series chart

## 🚀 Run It Yourself

```bash
git clone https://github.com/bdgroves/sierra-streamflow.git
cd sierra-streamflow
python scripts/fetch.py   # generates data/processed/streamflow.json
open index.html           # view dashboard locally
```

Python 3.9+ required. No dependencies beyond the standard library.

## ⚙️ Automation

GitHub Actions runs `fetch.py` every hour:
1. Calls USGS Instantaneous Values API (7-day period) for all stations
2. Calls USGS Daily Values API for last-year comparison
3. Writes `data/processed/streamflow.json`
4. Commits only if data changed
5. GitHub Pages serves the dashboard automatically

## 🛠 Tech Stack

```
sierra-streamflow/
├── 🐍 Python 3.12       — USGS API fetching, JSON output (stdlib only)
├── 🌐 HTML/CSS/JS        — NPS-aesthetic dashboard, Chart.js sparklines
├── ⚙️  GitHub Actions    — hourly cron scheduler
└── 🌐 GitHub Pages      — free live hosting
```

## 🗺 Roadmap

- [ ] 30-year historical percentile overlay
- [ ] Flood stage threshold lines on sparklines
- [ ] Interactive Leaflet map of all stations
- [ ] Melt season / snowmelt alert integration with SNOTEL data
- [ ] Bluesky/Twitter auto-post on significant flow events (ported from n8n)

## 📄 License

MIT — use it, fork it, build on it.

Data: [USGS National Water Information System](https://waterservices.usgs.gov/)
