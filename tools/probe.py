"""Probe run in Actions (sandbox has no network): station metadata, new USGS Water Data API shapes, ONI, record lengths."""
import json, urllib.request, urllib.parse, traceback
H = {"User-Agent": "sierra-streamflow probe (github.com/bdgroves/sierra-streamflow)", "Accept": "application/json"}
def get(url, params=None, raw=False):
    if params: url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
        b = r.read()
        return b.decode() if raw else json.loads(b)
IDS = ["11276500","11274790","11289650","11290000","11266500","11264500","11303000","11284400"]
out = {}
def step(k, f):
    try: out[k] = f()
    except Exception: out[k] = {"error": traceback.format_exc()[-1200:]}
step("legacy_site", lambda: get("https://waterservices.usgs.gov/nwis/site/", {"sites": ",".join(IDS), "format": "rdb", "siteOutput": "expanded", "siteStatus": "all"}, raw=True)[-6000:])
step("legacy_dv_range", lambda: get("https://waterservices.usgs.gov/nwis/site/", {"sites": ",".join(IDS), "format": "rdb", "outputDataTypeCd": "dv", "parameterCd": "00060", "siteStatus": "all"}, raw=True)[-4000:])
API = "https://api.waterdata.usgs.gov/ogcapi/v0"
step("new_locations", lambda: get(f"{API}/collections/monitoring-locations/items", {"id": "USGS-11264500", "f": "json"}))
step("new_daily", lambda: (lambda d: {"n": len(d.get("features", [])), "first": d.get("features", [None])[:2], "links": d.get("links"), "numberMatched": d.get("numberMatched")})(get(f"{API}/collections/daily/items", {"monitoring_location_id": "USGS-11264500", "parameter_code": "00060", "statistic_id": "00003", "time": "2026-09-01/2026-09-30", "f": "json", "limit": 100})))
step("new_continuous", lambda: (lambda d: {"n": len(d.get("features", [])), "first": d.get("features", [None])[:2], "numberMatched": d.get("numberMatched")})(get(f"{API}/collections/continuous/items", {"monitoring_location_id": "USGS-11264500", "parameter_code": "00060", "time": "P1D", "f": "json", "limit": 200})))
step("new_latest", lambda: get(f"{API}/collections/latest-continuous/items", {"monitoring_location_id": "USGS-11264500", "f": "json"}))
step("oni", lambda: get("https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", raw=True)[-3000:])
step("legacy_dv_long", lambda: (lambda d: [ (ts["sourceInfo"]["siteCode"][0]["value"], len(ts["values"][0]["value"]), ts["values"][0]["value"][0]["dateTime"]) for ts in d["value"]["timeSeries"]])(get("https://waterservices.usgs.gov/nwis/dv/", {"sites": "11264500,11266500,11276500", "parameterCd": "00060", "startDT": "1980-10-01", "endDT": "2026-09-30", "format": "json", "siteStatus": "all"})))
json.dump(out, open("tools/probe_out.json", "w"), indent=1, default=str)
