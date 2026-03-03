#!/usr/bin/env python3
"""
Sierra Streamflow Monitor — USGS Data Fetcher
Pulls:
  1. 7-day instantaneous values  → current flow, deltas, sparkline
  2. Current water-year daily values (Oct 1 → today) → current year line
  3. 20 years of daily values (2005–2024) → historical spaghetti lines
Outputs: data/processed/streamflow.json
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Station registry ──────────────────────────────────────────────────────────
STATIONS = [
    {"id": "11276500", "name": "Tuolumne R nr Hetch Hetchy",      "short": "Hetch Hetchy", "river": "Tuolumne",   "elev_ft": 3860, "lat": 37.9285, "lon": -119.7871},
    {"id": "11274790", "name": "Tuolumne R at Grand Canyon",       "short": "Grand Canyon", "river": "Tuolumne",   "elev_ft": 2200, "lat": 37.8913, "lon": -119.8232},
    {"id": "11289650", "name": "Tuolumne R bl LaGrange Dam",       "short": "LaGrange Dam", "river": "Tuolumne",   "elev_ft": 430,  "lat": 37.6621, "lon": -120.4451},
    {"id": "11290000", "name": "Tuolumne R at Modesto",            "short": "Modesto",      "river": "Tuolumne",   "elev_ft": 90,   "lat": 37.6388, "lon": -120.9996},
    {"id": "11266500", "name": "Merced R at Pohono Br (Yosemite)", "short": "Yosemite",     "river": "Merced",     "elev_ft": 3960, "lat": 37.7163, "lon": -119.6599},
    {"id": "11264500", "name": "Merced R at Happy Isles (Yosemite)",  "short": "Happy Isles",  "river": "Merced",     "elev_ft": 4000, "lat": 37.7327, "lon": -119.5571},
    {"id": "11303000", "name": "Stanislaus R at Ripon",            "short": "Ripon",        "river": "Stanislaus", "elev_ft": 60,   "lat": 37.7388, "lon": -121.1318},
    {"id": "11284400", "name": "Big Creek at Whites Gulch",        "short": "Big Creek",    "river": "Big Creek",  "elev_ft": 2100, "lat": 37.8566, "lon": -120.1388},
]

HIST_START_YEAR = 2005
HIST_END_YEAR   = 2024
PT      = ZoneInfo("America/Los_Angeles")
BASE_IV = "https://waterservices.usgs.gov/nwis/iv/"
BASE_DV = "https://waterservices.usgs.gov/nwis/dv/"
OUT_DIR = Path(__file__).parent.parent / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_json(url, params, retries=3):
    qs  = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{url}?{qs}",
        headers={"Accept": "application/json",
                 "User-Agent": "sierra-streamflow-monitor/1.0 (github.com/bdgroves)"},
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)


def fmt_dt(dt):
    h = dt.strftime("%I").lstrip("0") or "12"
    return f"{dt.month}/{dt.day}/{dt.year} {h}:{dt.strftime('%M')} {dt.strftime('%p')} PT"


def water_year(d):
    return d.year + 1 if d.month >= 10 else d.year


def wy_start(wy):
    return date(wy - 1, 10, 1)


def wy_end(wy):
    return date(wy, 9, 30)


def day_of_wy(d):
    return (d - wy_start(water_year(d))).days + 1


def extract_iv(ts_list, param_code):
    for ts in ts_list:
        code = ts.get("variable", {}).get("variableCode", [{}])[0].get("value", "")
        if code == param_code:
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


def extract_dv(ts_list):
    if not ts_list:
        return []
    pts = []
    for v in ts_list[0].get("values", [{}])[0].get("value", []):
        try:
            val = float(v["value"])
            d   = date.fromisoformat(v["dateTime"][:10])
            pts.append({"doy": day_of_wy(d), "v": val, "date": d.isoformat()})
        except (ValueError, KeyError):
            pass
    return sorted(pts, key=lambda x: x["doy"])


def signed(val, decimals=1):
    if val is None:
        return "N/A"
    s = "+" if val >= 0 else ""
    return f"{s}{val:.{decimals}f}"


def process_station(station):
    sid   = station["id"]
    today = datetime.now(tz=PT).date()
    cur_wy = water_year(today)

    # 1. Live IV — 7 days
    iv_raw  = fetch_json(BASE_IV, {"sites": sid, "parameterCd": "00060,00065",
                                    "period": "P7D", "format": "json", "siteStatus": "active"})
    ts_list    = iv_raw.get("value", {}).get("timeSeries", [])
    flow_pts   = extract_iv(ts_list, "00060")
    stage_pts  = extract_iv(ts_list, "00065")

    if not flow_pts:
        return {**station, "status": "no_data", "error": "No discharge data"}

    latest_flow  = flow_pts[-1]["v"]
    latest_t     = flow_pts[-1]["t"]
    latest_stage = stage_pts[-1]["v"] if stage_pts else None

    def delta_at(pts, ms_back):
        target = latest_t - ms_back
        for p in reversed(pts):
            if p["t"] <= target:
                return pts[-1]["v"] - p["v"]
        return None

    flow_d1h  = delta_at(flow_pts, 3_600_000)
    flow_d24h = delta_at(flow_pts, 86_400_000)
    flow_vals = [p["v"] for p in flow_pts]

    if flow_d1h is not None and abs(flow_d1h) >= 0.1:
        trend, trend_emoji = ("rising", "📈") if flow_d1h > 0 else ("falling", "📉")
    else:
        trend, trend_emoji = "stable", "➡️"

    if   latest_flow > 5000: status = "FLOOD"
    elif latest_flow > 1000: status = "HIGH"
    elif latest_flow > 200:  status = "ELEVATED"
    else:                    status = "NORMAL"

    last_dt     = datetime.fromtimestamp(latest_t / 1000, tz=timezone.utc).astimezone(PT)
    last_update = fmt_dt(last_dt)

    # 2. Current water-year daily values
    cur_wy_pts = []
    try:
        dv_cur = fetch_json(BASE_DV, {
            "sites": sid, "parameterCd": "00060",
            "startDT": wy_start(cur_wy).isoformat(),
            "endDT":   (today - timedelta(days=1)).isoformat(),
            "format": "json", "siteStatus": "active",
        })
        cur_wy_pts = extract_dv(dv_cur.get("value", {}).get("timeSeries", []))
    except Exception as e:
        print(f"\n    [warn] current WY: {e}", file=sys.stderr)

    # 3. Historical daily values — 20 water years
    hist_years = {}
    for wy in range(HIST_START_YEAR, HIST_END_YEAR + 1):
        try:
            dv_h = fetch_json(BASE_DV, {
                "sites": sid, "parameterCd": "00060",
                "startDT": wy_start(wy).isoformat(),
                "endDT":   wy_end(wy).isoformat(),
                "format": "json", "siteStatus": "active",
            })
            pts = extract_dv(dv_h.get("value", {}).get("timeSeries", []))
            if pts:
                hist_years[str(wy)] = pts
            time.sleep(0.15)
        except Exception as e:
            print(f"\n    [warn] WY{wy}: {e}", file=sys.stderr)

    # Median line across all historical years
    doy_vals = defaultdict(list)
    for pts in hist_years.values():
        for p in pts:
            doy_vals[p["doy"]].append(p["v"])
    median_line = []
    for doy in sorted(doy_vals):
        vals = sorted(doy_vals[doy])
        mid  = len(vals) // 2
        med  = vals[mid] if len(vals) % 2 else (vals[mid-1] + vals[mid]) / 2
        median_line.append({"doy": doy, "v": round(med, 1)})

    return {
        **station,
        "status":        status,
        "trend":         trend,
        "trend_emoji":   trend_emoji,
        "current_flow":  round(latest_flow, 1),
        "current_stage": round(latest_stage, 2) if latest_stage is not None else None,
        "flow_d1h":      round(flow_d1h, 1)  if flow_d1h  is not None else None,
        "flow_d24h":     round(flow_d24h, 1) if flow_d24h is not None else None,
        "flow_d1h_fmt":  signed(flow_d1h),
        "flow_d24h_fmt": signed(flow_d24h),
        "flow_7d_min":   round(min(flow_vals), 1),
        "flow_7d_max":   round(max(flow_vals), 1),
        "sparkline_flow": flow_pts,
        "cur_wy":        cur_wy_pts,
        "hist_years":    hist_years,
        "median_line":   median_line,
        "last_update":   last_update,
        "last_t":        latest_t,
        "usgs_url":      f"https://waterdata.usgs.gov/monitoring-location/{sid}/",
    }


def main():
    now_pt = datetime.now(PT)
    print(f"[{now_pt.hour}:{now_pt.strftime('%M')} PT] Fetching {len(STATIONS)} Sierra gages "
          f"(current + WY{HIST_START_YEAR}–{HIST_END_YEAR} historical)…")
    results = []
    for st in STATIONS:
        print(f"  → {st['id']}  {st['name']}", end=" … ", flush=True)
        try:
            rec = process_station(st)
            results.append(rec)
            hist_count = len(rec.get("hist_years", {}))
            print(f"{rec.get('current_flow','N/A')} cfs  [{rec.get('status')}]  ({hist_count} hist yrs)")
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            results.append({**st, "status": "error", "error": str(e)})

    out = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "generated_at_pt": fmt_dt(datetime.now(PT)),
        "hist_range":      f"{HIST_START_YEAR}–{HIST_END_YEAR}",
        "stations":        results,
    }
    out_path = OUT_DIR / "streamflow.json"
    out_path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"\n✅  Wrote {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
