"""Live provider smoke checks (network; separate from unit tests, never brittle).

    cd backend && python scripts/live_smoke.py [--json]

Checks Nominatim, OSRM, OpenWeather, Open-Elevation and the Bhuvan flood WMS for
the Guwahati → Shillong corridor and records status, latency and sample-output
validity. Missing credentials are reported as ``unconfigured`` (not failures).
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402

GUWAHATI, SHILLONG = (26.1445, 91.7362), (25.5788, 91.8933)
UA = {"User-Agent": "PathSense/1.0 (hackathon smoke; contact: three-dteam@pw.live)"}

async def timed(name, coro):
    started = time.perf_counter()
    try:
        detail = await coro
        return {"provider": name, "status": "healthy", "latency_ms": round((time.perf_counter() - started) * 1000), **detail}
    except httpx.HTTPStatusError as exc:
        return {"provider": name, "status": "degraded", "latency_ms": round((time.perf_counter() - started) * 1000), "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"provider": name, "status": "unavailable", "latency_ms": round((time.perf_counter() - started) * 1000), "detail": f"{type(exc).__name__}: {str(exc)[:120]}"}

async def nominatim(client, s):
    r = await client.get(f"{s.nominatim_base_url}/search", params={"q": "Shillong, Meghalaya", "format": "jsonv2", "limit": 1, "countrycodes": "in"}); r.raise_for_status(); rows = r.json()
    assert rows and abs(float(rows[0]["lat"]) - SHILLONG[0]) < .3, "unexpected geocode"
    return {"sample": {"display_name": rows[0]["display_name"][:60], "lat": rows[0]["lat"], "lon": rows[0]["lon"]}, "valid": True}

async def osrm(client, s):
    r = await client.get(f"{s.osrm_base_url}/route/v1/driving/{GUWAHATI[1]},{GUWAHATI[0]};{SHILLONG[1]},{SHILLONG[0]}", params={"overview": "full", "geometries": "geojson", "alternatives": "true"}); r.raise_for_status(); p = r.json()
    assert p.get("code") == "Ok" and p["routes"], "no route"
    return {"routes": len(p["routes"]), "distance_km": round(p["routes"][0]["distance"] / 1000, 1), "duration_min": round(p["routes"][0]["duration"] / 60), "geometry_points": len(p["routes"][0]["geometry"]["coordinates"]), "valid": 60 < p["routes"][0]["distance"] / 1000 < 200}

async def openweather(client, s):
    if not s.openweather_api_key:
        raise RuntimeError("unconfigured: OPENWEATHER_API_KEY missing")
    r = await client.get("https://api.openweathermap.org/data/2.5/weather", params={"lat": SHILLONG[0], "lon": SHILLONG[1], "appid": s.openweather_api_key, "units": "metric"}); r.raise_for_status(); d = r.json()
    return {"sample": {"temp_c": d["main"]["temp"], "condition": d["weather"][0]["description"], "rain_1h": d.get("rain", {}).get("1h", 0)}, "valid": -10 < d["main"]["temp"] < 50}

async def terrain(client, s):
    r = await client.post("https://api.open-elevation.com/api/v1/lookup", json={"locations": [{"latitude": SHILLONG[0], "longitude": SHILLONG[1]}, {"latitude": GUWAHATI[0], "longitude": GUWAHATI[1]}]}); r.raise_for_status(); e = [x["elevation"] for x in r.json()["results"]]
    return {"sample": {"shillong_m": e[0], "guwahati_m": e[1]}, "valid": e[0] > e[1] and 1000 < e[0] < 2200}

async def bhuvan(client, s):
    r = await client.get(s.bhuvan_flood_wms_url, params={"service": "WMS", "version": "1.1.1", "request": "GetMap", "layers": "as_fld_2010", "styles": "", "srs": "EPSG:4326", "bbox": "91.3,25.4,92.3,26.4", "width": 256, "height": 256, "format": "image/png", "transparent": "true"}); r.raise_for_status()
    return {"content_type": r.headers.get("content-type"), "bytes": len(r.content), "valid": r.headers.get("content-type", "").startswith("image/png")}

async def run() -> dict:
    s = get_settings()
    async with httpx.AsyncClient(timeout=30, headers=UA) as client:
        results = [await timed("nominatim", nominatim(client, s)), await timed("osrm", osrm(client, s)), await timed("openweather", openweather(client, s)), await timed("open-elevation", terrain(client, s)), await timed("bhuvan-flood-wms", bhuvan(client, s))]
    for r in results:
        if r["status"] == "unavailable" and "unconfigured" in r.get("detail", ""):
            r["status"] = "unconfigured"
    return {"corridor": "Guwahati → Shillong", "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--json", action="store_true"); args = parser.parse_args(argv)
    report = asyncio.run(run())
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for r in report["results"]:
            print(f"{r['provider']:18s} {r['status']:12s} {r['latency_ms']:6d} ms  {r.get('detail') or r.get('sample') or {k: v for k, v in r.items() if k in ('routes', 'distance_km', 'duration_min', 'valid', 'bytes')}}")
    sys.exit(0)

if __name__ == "__main__":
    main()
