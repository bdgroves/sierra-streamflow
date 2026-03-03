#!/usr/bin/env python3
"""
Sierra Streamflow Monitor — USGS Data Fetcher
Fetches discharge + stage data for major Tuolumne/Sierra Nevada gages.
Outputs JSON consumed by the dashboard.
"""

import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Station registry ──────────────────────────────────────────────────────────
STATIONS = [
    # Tuolumne watershed (headwaters → valley)
    {"id": "11276500", "name": "Tuolumne R nr Hetch Hetchy",    "river": "Tuolumne",   "elev_ft": 3860},
    {"id": "11274790", "name": "Tuolumne R Grand Canyon",       "river": "Tuolumne",   "elev_ft": 2200},
    {"id": "11289650", "name": "Tuolumne R bl LaGrange Dam",    "river": "Tuolumne",   "elev_ft": 430},
    {"id": "11290000", "name": "Tuolumne R at Modesto",         "river": "Tuolumne",   "elev_ft": 90},
    # Merced watershed
    {"id": "11266500", "name": "Merced R at Pohono Br (Yosemite)", "river": "Merced",  "elev_ft": 3960},
    {"id": "11270900", "name": "Merced R at Merced Falls",      "river": "Merced",     "elev_ft": 330},
    # Stanislaus watershed
    {"id": "11303000", "name": "Stanislaus R at Ripon",         "river": "Stanislaus", "elev_ft": 60},
    # Local — Big Creek (from your n8n workflow)
    {"id": "11284400", "name": "Big Creek at Whites Gulch",     "river": "Big Creek",  "elev_ft": 2100},
]

PT = ZoneInfo("America/Los_Angeles")
BASE_IV  = "https://waterservices.usgs.gov/nwis/iv/"
BASE_DV  = "https://waterservices.usgs.gov/nwis/dv/"
OUT_DIR  = Path(__file__).parent.parent / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_json(url: str, params: dict) -> dict:
    qs  = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"Accept": "application/json",
                 "User-Agent": "sierra-streamflow-monitor/1.0 (github.com/bdgroves)"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def extract_series(time_series_list, param_code):
    """Return sorted list of (epoch_ms, value) for given parameterCd."""
    for ts in time_series_list:
        if ts.get("variable", {}).get("variableCode", [{}])[0].get("value") == param_code:
            pts = []
            for v in ts.get("values", [{}])[0].get("value", []):
                try:
                    val = float(v["value"])
                    t   = int(datetime.fromisoformat(v["dateTime"]).timestamp() * 1000)
                    pts.append({"t": t, "v": val})
                except (ValueError, KeyError):
                    pass
            return sorted(pts, key=lambda x: x["t"])
    return []


def signed(val, decimals=1):
    if val is None:
        return "N/A"
    s = "+" if val >= 0 else ""
    return f"{s}{val:.{decimals}f}"


def process_station(station: dict) -> dict:
    sid  = station["id"]
    now  = datetime.now(tz=timezone.utc)
    pt_now = now.astimezone(PT)

    # ── 1. Live IV (current + 7 day history) ─────────────────────────────────
    iv_raw = fetch_json(BASE_IV, {
        "sites":       sid,
        "parameterCd": "00060,00065",
        "period":      "P7D",
        "format":      "json",
        "siteStatus":  "active",
    })

    ts_list = iv_raw.get("value", {}).get("timeSeries", [])
    flow_pts  = extract_series(ts_list, "00060")   # discharge cfs
    stage_pts = extract_series(ts_list, "00065")   # gage height ft

    if not flow_pts:
        return {**station, "status": "no_data", "error": "No discharge data"}

    # Latest values
    latest_flow  = flow_pts[-1]["v"]
    latest_t     = flow_pts[-1]["t"]
    latest_stage = stage_pts[-1]["v"] if stage_pts else None

    # Deltas (1h, 24h)
    def delta_at(pts, ms_back):
        target = latest_t - ms_back
        for p in reversed(pts):
            if p["t"] <= target:
                return pts[-1]["v"] - p["v"]
        return None

    flow_d1h  = delta_at(flow_pts,  3_600_000)
    flow_d24h = delta_at(flow_pts, 86_400_000)

    # 7-day min/max
    flow_vals = [p["v"] for p in flow_pts]
    flow_7d_min = min(flow_vals)
    flow_7d_max = max(flow_vals)

    # Trend
    if flow_d1h is not None and abs(flow_d1h) >= 0.1:
        trend = "rising" if flow_d1h > 0 else "falling"
        trend_emoji = "📈" if flow_d1h > 0 else "📉"
    else:
        trend = "stable"
        trend_emoji = "➡️"

    # Status
    if latest_flow > 5000:
        status = "FLOOD"
    elif latest_flow > 1000:
        status = "HIGH"
    elif latest_flow > 200:
        status = "ELEVATED"
    else:
        status = "NORMAL"

    # ── 2. Last year daily mean (same calendar day) ───────────────────────────
    ly_date      = (pt_now - timedelta(days=365)).date()
    ly_flow_mean = None
    try:
        dv_raw = fetch_json(BASE_DV, {
            "sites":       sid,
            "parameterCd": "00060",
            "startDT":     ly_date.isoformat(),
            "endDT":       (ly_date + timedelta(days=1)).isoformat(),
            "format":      "json",
            "siteStatus":  "active",
        })
        dv_ts = dv_raw.get("value", {}).get("timeSeries", [])
        if dv_ts:
            vals = dv_ts[0].get("values", [{}])[0].get("value", [])
            if vals:
                ly_flow_mean = float(vals[0]["value"])
    except Exception:
        pass

    # ── 3. Build 7-day sparkline arrays (down-sampled to ~168 pts) ───────────
    # Keep every point — the dashboard will plot these with Chart.js
    sparkline_flow  = flow_pts
    sparkline_stage = stage_pts

    # ── 4. Formatted last-update timestamp ───────────────────────────────────
    last_dt = datetime.fromtimestamp(latest_t / 1000, tz=timezone.utc).astimezone(PT)
    last_update = f"{last_dt.month}/{last_dt.day}/{last_dt.year} {last_dt.strftime('%I').lstrip('0') or '12'}:{last_dt.strftime('%M')} {last_dt.strftime('%p')} PT"

    return {
        **station,
        "status":          status,
        "trend":           trend,
        "trend_emoji":     trend_emoji,

        "current_flow":    round(latest_flow, 1),
        "current_stage":   round(latest_stage, 2) if latest_stage is not None else None,

        "flow_d1h":        round(flow_d1h, 1)  if flow_d1h  is not None else None,
        "flow_d24h":       round(flow_d24h, 1) if flow_d24h is not None else None,
        "flow_d1h_fmt":    signed(flow_d1h,  1),
        "flow_d24h_fmt":   signed(flow_d24h, 1),

        "flow_7d_min":     round(flow_7d_min, 1),
        "flow_7d_max":     round(flow_7d_max, 1),

        "ly_flow_mean":    round(ly_flow_mean, 1) if ly_flow_mean is not None else None,
        "ly_pct":          round((latest_flow / ly_flow_mean - 1) * 100, 1)
                           if ly_flow_mean and ly_flow_mean > 0 else None,

        "sparkline_flow":  sparkline_flow,
        "sparkline_stage": sparkline_stage,

        "last_update":     last_update,
        "last_t":          latest_t,
        "usgs_url":        f"https://waterdata.usgs.gov/monitoring-location/{sid}/",
    }


def main():
    print(f"[{datetime.now(PT).strftime('%H:%M PT')}] Fetching {len(STATIONS)} Sierra gages…")
    results = []
    for st in STATIONS:
        print(f"  → {st['id']}  {st['name']}", end=" … ", flush=True)
        try:
            rec = process_station(st)
            results.append(rec)
            flow = rec.get("current_flow", "N/A")
            print(f"{flow} cfs  [{rec.get('status')}]")
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            results.append({**st, "status": "error", "error": str(e)})

    # ── Write output ──────────────────────────────────────────────────────────
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_at_pt": (lambda d: f"{d.month}/{d.day}/{d.year} {d.strftime('%I').lstrip('0') or '12'}:{d.strftime('%M')} {d.strftime('%p')} PT")(datetime.now(PT)),
        "stations": results,
    }
    out_path = OUT_DIR / "streamflow.json"
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"\n✅ Wrote {out_path}  ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
