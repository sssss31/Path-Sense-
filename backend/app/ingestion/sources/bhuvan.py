"""NRSC/ISRO Bhuvan flood data helper.

Verified 2026-09-07 from the build network:
* ``https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe`` — official "Bhuvan OGC Web
  Service of Disaster Datasets - Flood" (WMS 1.1.1, EPSG:4326, image/png, 121
  layers incl. Assam annual inundation ``as_fld_1998``…``as_fld_2010`` and dated
  2011-2013 event layers). Anonymous GetCapabilities/GetMap work.
* ``bhuvan-vec1/vec2 .../bhuvan/gwc/service/wms`` — Bhuvan thematic WMS; slow/timeouts.
* No anonymous vector (shapefile/GeoJSON) download of Flood Hazard Zonation was
  found; NDEM/NRSC publish atlases (PDF) and WMS visualisation.

This helper only *inspects* the WMS (capabilities, layer list, sample GetMap)
so operators can confirm availability. It never converts imagery into
polygons — raster visualisation is rendered as a remote map layer instead.

    python -m app.ingestion.sources.bhuvan capabilities
    python -m app.ingestion.sources.bhuvan sample --layer as_fld_2010 --output /tmp/as_fld_2010.png
"""
import argparse
import json
import re
import sys

import httpx

from app.core.config import get_settings
from app.providers.geospatial_layers.base import validate_external_url

UA = {"User-Agent": "PathSense/1.0 (hackathon research)"}

def capabilities(url: str | None = None, timeout: float = 60) -> dict:
    s = get_settings()
    url = validate_external_url(url or s.bhuvan_flood_wms_url)
    with httpx.Client(timeout=timeout, headers=UA) as client:
        r = client.get(url, params={"service": "WMS", "request": "GetCapabilities", "version": "1.1.1"})
    r.raise_for_status()
    text = r.text
    layers = []
    for block in re.findall(r"<Layer[^>]*>(.*?)</Layer>", text, re.S):
        name = re.search(r"<Name>([^<]+)</Name>", block)
        bbox = re.search(r'<LatLonBoundingBox minx="([^"]+)" miny="([^"]+)" maxx="([^"]+)" maxy="([^"]+)"', block)
        if name and bbox:
            layers.append({"name": name.group(1), "bbox": [round(float(v), 4) for v in bbox.groups()], "year": (re.search(r"_(\d{4})$", name.group(1)) or [None, None])[1]})
    return {"url": url, "title": (re.search(r"<Title>([^<]+)</Title>", text) or [None, None])[1], "abstract": (re.search(r"<Abstract>([^<]+)</Abstract>", text) or [None, None])[1],
            "contact": (re.search(r"<ContactOrganization>([^<]+)</ContactOrganization>", text) or [None, None])[1], "srs": sorted(set(re.findall(r"<SRS>([^<]+)</SRS>", text))),
            "formats": re.findall(r"<Format>([^<]+)</Format>", text)[:8], "layers": layers, "configured_layers_present": [l for l in s.bhuvan_flood_layers if any(x["name"] == l for x in layers)]}

def sample(layer: str, output: str, bbox: str = "89.7,24.13,96.02,27.97", size: int = 900, timeout: float = 60) -> dict:
    s = get_settings()
    url = validate_external_url(s.bhuvan_flood_wms_url)
    with httpx.Client(timeout=timeout, headers=UA) as client:
        r = client.get(url, params={"service": "WMS", "version": "1.1.1", "request": "GetMap", "layers": layer, "styles": "", "srs": "EPSG:4326", "bbox": bbox, "width": size, "height": int(size * .6), "format": "image/png", "transparent": "true"})
    r.raise_for_status()
    with open(output, "wb") as handle:
        handle.write(r.content)
    return {"layer": layer, "output": output, "bytes": len(r.content), "content_type": r.headers.get("content-type")}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect the Bhuvan flood WMS (no vector conversion)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capabilities")
    sm = sub.add_parser("sample"); sm.add_argument("--layer", default="as_fld_2010"); sm.add_argument("--output", required=True); sm.add_argument("--bbox", default="89.7,24.13,96.02,27.97")
    args = parser.parse_args(argv)
    try:
        result = capabilities() if args.command == "capabilities" else sample(args.layer, args.output, args.bbox)
    except Exception as exc:
        print(json.dumps({"status": "unavailable", "error": type(exc).__name__, "detail": str(exc)[:200]})); sys.exit(1)
    print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    main()
