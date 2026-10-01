#!/usr/bin/env python3
"""
Sierra Streamflow Monitor — USGS data fetcher (stdlib only)

Every run (hourly, GitHub Actions):
  • last 7 days of 15-minute discharge and stage   → current flow, deltas, storm-pulse chart
  • daily means for the current and previous water year
  • where today's flow sits against every day like it since 1980 (percentile class)

When the cached record is missing a completed water year, or once a week:
  • the full daily record since Oct 1980 for each gage → data/history/<site>.json
  • per-day-of-year percentile bands, per-water-year runoff, peak and timing
  • NOAA's Oceanic Niño Index, to set each water year's ENSO phase

Sources
  USGS Water Data APIs (api.waterdata.usgs.gov), which replace the legacy
  WaterServices (waterservices.usgs.gov) that USGS is decommissioning in the
  first quarter of 2027. The legacy service is kept as a fallback until then.
  NOAA CPC ONI: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt

Outputs
  data/processed/streamflow.json   small, loaded first: current conditions
  data/processed/history.json      percentile bands, water-year table, ENSO
  data/history/<site>.json         raw daily cache (re-used between runs)

If a gage fails, its previous record is kept and marked stale rather than
replaced by an error — the page should never lose data because USGS hiccuped.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Station registry ─────────────────────────────────────────────────────────
# Coordinates, elevations (ft, NAVD88) and drainage areas (sq mi) are USGS's own
# site metadata, checked against the site service on 2026-10-01. The earlier
# hand-typed values had Grand Canyon and Big Creek several miles off, and the
# valley gages hundreds of feet too high.
# regulated: flow is set by dam releases upstream, not by the weather.
STATIONS = [
    {"id": "11264500", "name": "Merced R at Happy Isles Bridge, Yosemite", "short": "Happy Isles",  "river": "Merced",     "elev_ft": 4020, "drain_sqmi": 181,  "lat": 37.7313, "lon": -119.5590, "regulated": False,
     "note": "Yosemite's high country before it reaches the Valley. No dams above."},
    {"id": "11266500", "name": "Merced R at Pohono Bridge, Yosemite",      "short": "Pohono Bridge","river": "Merced",     "elev_ft": 3865, "drain_sqmi": 321,  "lat": 37.7163, "lon": -119.6657, "regulated": False,
     "note": "The bottom of Yosemite Valley. Unregulated; the classic Yosemite flood gage."},
    {"id": "11274790", "name": "Tuolumne R, Grand Canyon of the Tuolumne above Hetch Hetchy", "short": "Grand Canyon", "river": "Tuolumne", "elev_ft": 3814, "drain_sqmi": 301, "lat": 37.9166, "lon": -119.6599, "regulated": False,
     "note": "The wild Tuolumne just above Hetch Hetchy Reservoir. No dams above."},
    {"id": "11276500", "name": "Tuolumne R near Hetch Hetchy",            "short": "Hetch Hetchy", "river": "Tuolumne",   "elev_ft": 3452, "drain_sqmi": 457,  "lat": 37.9374, "lon": -119.7982, "regulated": True,
     "note": "Below O'Shaughnessy Dam: what San Francisco's reservoir lets go."},
    {"id": "11284400", "name": "Big Creek above Whites Gulch, near Groveland", "short": "Big Creek", "river": "Big Creek", "elev_ft": 2568, "drain_sqmi": 16.4, "lat": 37.8419, "lon": -120.1849, "regulated": False,
     "note": "A 16-square-mile foothill creek near Groveland. Rain-fed, no dams; often dry by fall."},
    {"id": "11289650", "name": "Tuolumne R below La Grange Dam",           "short": "La Grange Dam","river": "Tuolumne",   "elev_ft": 173,  "drain_sqmi": 1538, "lat": 37.6663, "lon": -120.4421, "regulated": True,
     "note": "Below Don Pedro and La Grange dams: what enters the valley."},
    {"id": "11290000", "name": "Tuolumne R at Modesto",                    "short": "Modesto",      "river": "Tuolumne",   "elev_ft": 2,    "drain_sqmi": 1884, "lat": 37.6272, "lon": -120.9844, "regulated": True,
     "note": "The Tuolumne on the valley floor, near its mouth on the San Joaquin."},
    {"id": "11303000", "name": "Stanislaus R at Ripon",                    "short": "Ripon",        "river": "Stanislaus", "elev_ft": 3,    "drain_sqmi": 1075, "lat": 37.7296, "lon": -121.1105, "regulated": True,
     "note": "Below New Melones Reservoir, near the confluence with the San Joaquin."},
]

RECORD_START = date(1980, 10, 1)          # start of water year 1981
PT = ZoneInfo("America/Los_Angeles")
API = "https://api.waterdata.usgs.gov/ogcapi/v0"
LEGACY_IV = "https://waterservices.usgs.gov/nwis/iv/"
LEGACY_DV = "https://waterservices.usgs.gov/nwis/dv/"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
API_KEY = os.environ.get("USGS_API_KEY", "").strip()   # optional; raises the anonymous rate limit
RATE = {}                                     # last X-RateLimit-* headers seen from the Water Data API

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
CACHE = ROOT / "data" / "history"
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)
CFS_DAY_TO_AF = 1.98347                   # 1 cfs for a day = 1.98 acre-feet

# ── Water-year helpers ───────────────────────────────────────────────────────
def water_year(d):
    return d.year + 1 if d.month >= 10 else d.year


def wy_start(wy):
    return date(wy - 1, 10, 1)


def day_of_wy(d):
    return (d - wy_start(water_year(d))).days + 1


def fmt_dt(dt):
    h = dt.strftime("%I").lstrip("0") or "12"
    return f"{dt.month}/{dt.day}/{dt.year} {h}:{dt.strftime('%M')} {dt.strftime('%p')} PT"


# ── HTTP ─────────────────────────────────────────────────────────────────────
def get(url, params=None, raw=False, retries=3):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = {"Accept": "application/json",
               "User-Agent": "sierra-streamflow-monitor/2.0 (github.com/bdgroves/sierra-streamflow)"}
    if API_KEY and url.startswith(API):
        headers["X-Api-Key"] = API_KEY
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                if url.startswith(API):
                    for h in ("X-RateLimit-Limit", "X-RateLimit-Remaining"):
                        if r.headers.get(h):
                            RATE[h] = r.headers.get(h)
                body = r.read()
                return body.decode() if raw else json.loads(body)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 2)


def ogc_items(collection, **params):
    """All features from a Water Data OGC collection, following 'next' links."""
    params = {"f": "json", "limit": 10000, **params}
    url, q, feats = f"{API}/collections/{collection}/items", params, []
    for _ in range(50):
        d = get(url, q)
        feats += d.get("features", [])
        nxt = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)
        if not nxt:
            break
        url, q = nxt, None
    return feats


# ── Fetchers: new API first, legacy WaterServices as fallback ────────────────
def daily_values(site, start, end):
    """{date: cfs} daily means."""
    try:
        feats = ogc_items("daily", monitoring_location_id=f"USGS-{site}", parameter_code="00060",
                          statistic_id="00003", time=f"{start}/{end}")
        out = {}
        for f in feats:
            p = f["properties"]
            try:
                out[p["time"][:10]] = float(p["value"])
            except (TypeError, ValueError):
                pass
        if out:
            return out, "water-data-api"
    except Exception as e:
        print(f"    [warn] daily API {site}: {e}", file=sys.stderr)
    d = get(LEGACY_DV, {"sites": site, "parameterCd": "00060", "startDT": start, "endDT": end,
                        "format": "json", "siteStatus": "all"})
    out = {}
    for ts in d.get("value", {}).get("timeSeries", []):
        for v in ts["values"][0]["value"]:
            try:
                val = float(v["value"])
            except (TypeError, ValueError):
                continue
            if val >= 0:                     # -999999 is the "no data" sentinel
                out[v["dateTime"][:10]] = val
    return out, "waterservices"


def instantaneous(site):
    """(flow_pts, stage_pts) for the last 7 days, each [{t: ms, v}]."""
    try:
        res = {}
        for code in ("00060", "00065"):
            feats = ogc_items("continuous", monitoring_location_id=f"USGS-{site}", parameter_code=code, time="P7D")
            pts = []
            for f in feats:
                p = f["properties"]
                try:
                    pts.append({"t": int(datetime.fromisoformat(p["time"]).timestamp() * 1000), "v": float(p["value"])})
                except (TypeError, ValueError):
                    pass
            res[code] = sorted(pts, key=lambda x: x["t"])
        if res["00060"]:
            return res["00060"], res["00065"], "water-data-api"
    except Exception as e:
        print(f"    [warn] continuous API {site}: {e}", file=sys.stderr)
    d = get(LEGACY_IV, {"sites": site, "parameterCd": "00060,00065", "period": "P7D", "format": "json", "siteStatus": "all"})
    res = {"00060": [], "00065": []}
    for ts in d.get("value", {}).get("timeSeries", []):
        code = ts["variable"]["variableCode"][0]["value"]
        for v in ts["values"][0]["value"]:
            try:
                res.setdefault(code, []).append({"t": int(datetime.fromisoformat(v["dateTime"]).timestamp() * 1000), "v": float(v["value"])})
            except (TypeError, ValueError):
                pass
    return sorted(res["00060"], key=lambda x: x["t"]), sorted(res["00065"], key=lambda x: x["t"]), "waterservices"


# ── History cache ────────────────────────────────────────────────────────────
def load_cache(site):
    p = CACHE / f"{site}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def refresh_history(site, last_complete_wy, force=False):
    """Daily record from RECORD_START through the last completed water year."""
    cached = load_cache(site)
    end = date(last_complete_wy, 9, 30)
    fresh = cached and cached.get("through") == end.isoformat() and \
        (date.today() - date.fromisoformat(cached.get("fetched", "2000-01-01"))).days < 7
    if fresh and not force:
        return cached
    vals, src = daily_values(site, RECORD_START.isoformat(), end.isoformat())
    if len(vals) < 365:
        if cached:
            print(f"    [warn] history for {site} came back short ({len(vals)} days); keeping cache", file=sys.stderr)
            return cached
        raise RuntimeError(f"no daily history for {site}")
    first = min(vals)
    start = date.fromisoformat(first)
    n = (end - start).days + 1
    series = [vals.get((start + timedelta(days=i)).isoformat()) for i in range(n)]
    rec = {"site": site, "start": first, "through": end.isoformat(), "source": src,
           "fetched": date.today().isoformat(), "values": series}
    (CACHE / f"{site}.json").write_text(json.dumps(rec, separators=(",", ":")))
    print(f"    history {site}: {first} → {end} ({sum(v is not None for v in series)} days, {src})")
    return rec


def by_water_year(rec):
    out = defaultdict(dict)                 # wy -> {doy: cfs}
    start = date.fromisoformat(rec["start"])
    for i, v in enumerate(rec["values"]):
        if v is None:
            continue
        d = start + timedelta(days=i)
        out[water_year(d)][day_of_wy(d)] = v
    return out


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def bands(wys):
    """Per day-of-water-year percentiles over all complete years, ±3-day window."""
    by_doy = defaultdict(list)
    for y in wys.values():
        for d, v in y.items():
            by_doy[d].append(v)
    out = []
    for doy in range(1, 367):
        vals = sorted(v for d in range(doy - 3, doy + 4) for v in by_doy.get(d, ()))
        if len(vals) < 20:
            out.append(None)
            continue
        out.append([round(pct(vals, q), 2) for q in (0.0, 0.10, 0.25, 0.50, 0.75, 0.90, 1.0)])
    return out                              # [min, p10, p25, p50, p75, p90, max]


def annual(wys):
    rows = {}
    for wy, days in sorted(wys.items()):
        if len(days) < 355:                 # skip years with big gaps
            continue
        vals = [days[d] for d in sorted(days)]
        total = sum(vals)
        cum, centroid = 0, None
        for d in sorted(days):
            cum += days[d]
            if centroid is None and total and cum >= total / 2:
                centroid = d
        peak_doy = max(days, key=days.get)
        rows[str(wy)] = {"af": round(total * CFS_DAY_TO_AF), "peak": round(days[peak_doy], 1),
                         "peak_doy": peak_doy, "half_doy": centroid}
    return rows


def classify(value, band):
    """USGS WaterWatch-style class for a flow against that day's percentiles."""
    if value is None or not band:
        return None, None
    mn, p10, p25, p50, p75, p90, mx = band
    # approximate percentile by interpolating between the stored points
    pts = [(0, mn), (10, p10), (25, p25), (50, p50), (75, p75), (90, p90), (100, mx)]
    if value <= mn:
        p = 0
    elif value >= mx:
        p = 100
    else:
        p = 50
        for (q0, v0), (q1, v1) in zip(pts, pts[1:]):
            if v0 <= value <= v1:
                p = q0 + (q1 - q0) * ((value - v0) / (v1 - v0) if v1 > v0 else 0.5)
                break
    if value > mx:
        cls = "RECORD_HIGH"
    elif value < mn:
        cls = "RECORD_LOW"
    elif p >= 90:
        cls = "MUCH_ABOVE"
    elif p > 75:
        cls = "ABOVE"
    elif p >= 25:
        cls = "NORMAL"
    elif p >= 10:
        cls = "BELOW"
    else:
        cls = "MUCH_BELOW"
    return cls, round(p)


# ── ENSO ─────────────────────────────────────────────────────────────────────
def fetch_oni():
    """{water_year: DJF ONI} plus the latest 3-month value."""
    txt = get(ONI_URL, raw=True)
    djf, latest = {}, None
    for line in txt.splitlines()[1:]:
        parts = line.split()
        if len(parts) != 4:
            continue
        seas, yr, _, anom = parts[0], int(parts[1]), parts[2], float(parts[3])
        latest = {"season": seas, "year": yr, "oni": anom}
        if seas == "DJF":
            djf[yr] = anom                 # DJF 1998 = the winter of water year 1998
    return djf, latest


OUTLOOK_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def fetch_outlook():
    """NOAA CPC's current ENSO Diagnostic Discussion: alert status, synopsis, issue date.

    CPC issues it monthly (the second Thursday), so the page quotes NOAA's own
    latest words instead of a sentence typed in September."""
    import html as _html
    import re
    page = get(OUTLOOK_URL, raw=True)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S | re.I)
    text = _html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text)
    status = re.search(r"ENSO Alert System Status:\s*(.+?)(?=\s+Synopsis:|\s{2,}|$)", text)
    synopsis = re.search(r"Synopsis:\s*(.+?\.)(?=\s+[A-Z][a-z]|\s*$)", text)
    issued = re.search(rf"\b(\d{{1,2}} (?:{MONTHS}) \d{{4}})\b", text)
    if not (status and synopsis):
        raise ValueError("could not find the status and synopsis on the CPC page")
    return {"status": status.group(1).strip()[:120], "synopsis": synopsis.group(1).strip()[:400],
            "issued": issued.group(1) if issued else None, "url": OUTLOOK_URL}


def storm_check(stations):
    """Gages with no dams above them that look like a storm is arriving.

    Used to open a GitHub issue the first time it happens each water year, so
    someone looks at how the percentile labels and charts behave in a real storm."""
    hits = []
    for st in stations:
        if st.get("regulated") or st.get("stale"):
            continue
        flow, d24 = st.get("current_flow") or 0, st.get("flow_d24h")
        if d24 is None:
            continue
        before = flow - d24
        jumped = d24 > 0 and (before <= 0.5 and flow >= 2 or before > 0.5 and flow >= 2 * before)
        high = st.get("status") in ("ABOVE", "MUCH_ABOVE", "RECORD_HIGH") and d24 > 0
        if jumped or high:
            hits.append({"id": st["id"], "short": st["short"], "flow": flow, "d24h": d24, "status": st.get("status")})
    return hits


def enso_phase(oni):
    if oni is None:
        return None
    if oni >= 2.0:
        return "very strong El Niño"
    if oni >= 1.5:
        return "strong El Niño"
    if oni >= 1.0:
        return "moderate El Niño"
    if oni >= 0.5:
        return "weak El Niño"
    if oni <= -1.5:
        return "strong La Niña"
    if oni <= -1.0:
        return "moderate La Niña"
    if oni <= -0.5:
        return "weak La Niña"
    return "neutral"


# ── Per-station current conditions ───────────────────────────────────────────
def signed(val, decimals=1):
    if val is None:
        return "N/A"
    return f"{'+' if val >= 0 else ''}{val:.{decimals}f}"


def current(station, band_today, cur_wy, today):
    sid = station["id"]
    flow, stage, src = instantaneous(sid)
    if not flow:
        raise RuntimeError("no discharge data in the last 7 days")
    latest, latest_t = flow[-1]["v"], flow[-1]["t"]

    def delta(ms):
        target = latest_t - ms
        for p in reversed(flow):
            if p["t"] <= target:
                return latest - p["v"]
        return None

    d1, d24 = delta(3_600_000), delta(86_400_000)
    trend = "rising" if d1 is not None and d1 >= 0.1 and d1 > 0.01 * latest else \
            "falling" if d1 is not None and d1 <= -0.1 and -d1 > 0.01 * latest else "steady"
    cls, p = classify(latest, band_today)

    # daily means: this water year and last
    cur_start, prev_start = wy_start(cur_wy), wy_start(cur_wy - 1)
    dv, _ = daily_values(sid, prev_start.isoformat(), (today - timedelta(days=1)).isoformat())
    cur, prev = [], []
    for ds, v in sorted(dv.items()):
        d = date.fromisoformat(ds)
        (cur if d >= cur_start else prev).append([day_of_wy(d), v])

    # thin the 15-minute series to hourly for the page (7 x 24 points)
    hourly, last_h = [], None
    for pt in flow:
        h = pt["t"] // 3_600_000
        if h != last_h:
            hourly.append([pt["t"], pt["v"]])
            last_h = h
    if hourly[-1][0] != latest_t:
        hourly.append([latest_t, latest])

    last_dt = datetime.fromtimestamp(latest_t / 1000, tz=timezone.utc).astimezone(PT)
    return {
        "status": cls or "UNKNOWN", "percentile": p, "trend": trend,
        "current_flow": round(latest, 2), "current_stage": round(stage[-1]["v"], 2) if stage else None,
        "flow_d1h": round(d1, 1) if d1 is not None else None, "flow_d24h": round(d24, 1) if d24 is not None else None,
        "flow_d1h_fmt": signed(d1), "flow_d24h_fmt": signed(d24),
        "flow_7d_min": round(min(p["v"] for p in flow), 1), "flow_7d_max": round(max(p["v"] for p in flow), 1),
        "spark": hourly, "cur_wy": cur, "prev_wy": prev,
        "last_update": fmt_dt(last_dt), "last_t": latest_t, "source": src,
        "usgs_url": f"https://waterdata.usgs.gov/monitoring-location/USGS-{sid}/",
    }


# ── Commit throttle ──────────────────────────────────────────────────────────
def quiet(out, prev):
    """True when nothing worth committing has happened.

    The job runs hourly, and every write is a git commit. In a dry spell that's
    24 near-identical commits a day, so: rewrite at most every 3 hours unless a
    status changes, a gage moves more than 10%, a storm is flagged, a gage goes
    stale or recovers, NOAA posts a new outlook, or the day rolls over."""
    if not prev or not prev.get("generated_at"):
        return False
    age = datetime.now(timezone.utc) - datetime.fromisoformat(prev["generated_at"])
    if age >= timedelta(hours=3) or out["wy_day"] != prev.get("wy_day") or out["storm"]:
        return False
    if (out["enso"].get("outlook") or {}).get("issued") != ((prev.get("enso") or {}).get("outlook") or {}).get("issued"):
        return False
    old = {s["id"]: s for s in prev.get("stations", [])}
    for st in out["stations"]:
        p = old.get(st["id"])
        if not p or p.get("status") != st.get("status") or bool(p.get("stale")) != bool(st.get("stale")):
            return False
        a, b = p.get("current_flow") or 0, st.get("current_flow") or 0
        if abs(b - a) > max(1.0, 0.10 * a):
            return False
    return True


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    now_pt = datetime.now(PT)
    today = now_pt.date()
    cur_wy = water_year(today)
    last_complete = cur_wy - 1
    force = "--history" in sys.argv
    print(f"[{now_pt:%Y-%m-%d %H:%M} PT] water year {cur_wy} (day {day_of_wy(today)}); history through WY{last_complete}")

    prev_out = {}
    prev_path = OUT / "streamflow.json"
    if prev_path.exists():
        try:
            prev_out = {s["id"]: s for s in json.loads(prev_path.read_text()).get("stations", [])}
        except Exception:
            prev_out = {}

    try:
        djf, oni_latest = fetch_oni()
    except Exception as e:
        print(f"  [warn] ONI: {e}", file=sys.stderr)
        djf, oni_latest = {}, None
        old = OUT / "history.json"
        if old.exists():
            h = json.loads(old.read_text())
            djf = {int(k): v for k, v in h.get("enso", {}).get("djf", {}).items()}
            oni_latest = h.get("enso", {}).get("latest")

    prev_full = {}
    if prev_path.exists():
        try:
            prev_full = json.loads(prev_path.read_text())
        except Exception:
            prev_full = {}
    try:
        outlook = fetch_outlook()
        print(f"  NOAA: {outlook['status']} ({outlook['issued']})")
    except Exception as e:
        print(f"  [warn] NOAA outlook: {e}", file=sys.stderr)
        outlook = (prev_full.get("enso") or {}).get("outlook")

    stations, hist_out, health = [], {}, {}
    for st in STATIONS:
        sid = st["id"]
        print(f"  → {sid} {st['short']}", flush=True)
        band, ann = None, {}
        try:
            rec = refresh_history(sid, last_complete, force)
            wys = by_water_year(rec)
            band = bands({y: d for y, d in wys.items() if y <= last_complete})
            ann = annual(wys)
            hist_out[sid] = {"bands": band, "annual": ann, "record_start": rec["start"], "source": rec.get("source")}
        except Exception as e:
            print(f"    [warn] history {sid}: {e}", file=sys.stderr)
            health[f"history {st['short']}"] = str(e)[:160]
        try:
            today_band = band[day_of_wy(today) - 1] if band else None
            cond = current(st, today_band, cur_wy, today)
            stations.append({**st, **cond})
            print(f"    {cond['current_flow']} cfs · {cond['status']} (p{cond['percentile']}) · {cond['source']}")
        except Exception as e:
            print(f"    [warn] current {sid}: {e}", file=sys.stderr)
            health[f"current {st['short']}"] = str(e)[:160]
            old = prev_out.get(sid)
            stations.append({**(old or st), **st, "stale": True, "status": (old or {}).get("status", "UNKNOWN"),
                             "error": str(e)[:160]})

    # median annual runoff per station, and each year as % of it
    for sid, h in hist_out.items():
        afs = sorted(r["af"] for r in h["annual"].values())
        med = pct(afs, 0.5)
        h["median_af"] = round(med) if med else None
        for wy, r in h["annual"].items():
            r["pct_median"] = round(100 * r["af"] / med) if med else None

    ok = sum(1 for s in stations if not s.get("stale"))
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at_pt": fmt_dt(now_pt),
        "water_year": cur_wy, "wy_day": day_of_wy(today),
        "record": f"WY{RECORD_START.year + 1}–{last_complete}",
        "health": {"stations_ok": ok, "stations": len(stations), "issues": health,
                   # whether a USGS key was sent, and the hourly limit USGS reported back
                   # (the key itself is never written anywhere)
                   "api_key": bool(API_KEY), "rate_limit": RATE.get("X-RateLimit-Limit"),
                   "rate_remaining": RATE.get("X-RateLimit-Remaining")},
        "enso": {"latest": oni_latest, "phase": enso_phase(oni_latest["oni"]) if oni_latest else None,
                 "outlook": outlook},
        "storm": storm_check(stations),
        "stations": stations,
    }
    if ok == 0 and prev_out:
        print("  ✗ every gage failed — keeping the previous streamflow.json", file=sys.stderr)
        sys.exit(1)
    if quiet(out, prev_full) and "--always" not in sys.argv:
        print("  quiet hour: no meaningful change in the last 3 hours, not rewriting streamflow.json")
    else:
        (OUT / "streamflow.json").write_text(json.dumps(out, separators=(",", ":")))

    if hist_out:
        old = {}
        if (OUT / "history.json").exists():
            try:
                old = json.loads((OUT / "history.json").read_text()).get("stations", {})
            except Exception:
                old = {}
        hist = {
            "generated_at": out["generated_at"], "record": out["record"],
            "enso": {"djf": {str(k): v for k, v in sorted(djf.items())},
                     "phase": {str(k): enso_phase(v) for k, v in sorted(djf.items())},
                     "latest": oni_latest},
            "stations": {**old, **hist_out},
        }
        same = False
        if (OUT / "history.json").exists():
            try:
                prev_h = json.loads((OUT / "history.json").read_text())
                same = {k: v for k, v in prev_h.items() if k != "generated_at"} == \
                       json.loads(json.dumps({k: v for k, v in hist.items() if k != "generated_at"}))
            except Exception:
                same = False
        if not same:     # rewrite only when something in it changed (it's 160 KB and committed)
            (OUT / "history.json").write_text(json.dumps(hist, separators=(",", ":")))
    print(f"✅ {ok}/{len(stations)} gages current · streamflow.json "
          f"{(OUT / 'streamflow.json').stat().st_size // 1024} KB · history.json "
          f"{(OUT / 'history.json').stat().st_size // 1024 if (OUT / 'history.json').exists() else 0} KB")


if __name__ == "__main__":
    main()
