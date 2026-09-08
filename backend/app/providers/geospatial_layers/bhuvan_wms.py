"""NRSC/ISRO Bhuvan flood WMS (Bhuvan OGC Web Service of Disaster Datasets - Flood).

Verified 2026-09-07: ``https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe`` answers
WMS 1.1.1 GetCapabilities/GetMap anonymously, EPSG:4326, image/png, with Assam
annual inundation layers ``as_fld_1998`` … ``as_fld_2010`` (bbox 89.7,24.13 →
96.02,27.97) and dated 2011-2013 event layers. Layers are historical satellite-
derived inundation; they are rendered remotely and never converted into
polygons or treated as current alerts. Capabilities are cached in-process so
health checks stay cheap and the public service is not hammered.
"""
import re
import time

import httpx

from app.core.config import get_settings
from app.providers.geospatial_layers.base import ExternalLayer, GeospatialLayerProvider, validate_external_url

ASSAM_BBOX = [89.7, 24.13, 96.02, 27.97]
_CACHE: dict = {"checked_at": 0.0, "result": None}
CACHE_TTL_SECONDS = 900

def year_of(layer: str) -> str | None:
    m = re.search(r"_(\d{4})$", layer)
    return m.group(1) if m else None

class BhuvanFloodWMSProvider(GeospatialLayerProvider):
    key = "bhuvan_flood_wms"

    def __init__(self):
        self.settings = get_settings()
        self.url = validate_external_url(self.settings.bhuvan_flood_wms_url)

    def layers(self) -> list[ExternalLayer]:
        out = []
        for name in self.settings.bhuvan_flood_layers:
            year = year_of(name)
            state = "Assam" if name.startswith("as_") else "Bihar" if name.startswith("br_") else "India"
            out.append(ExternalLayer(
                id=f"bhuvan:{name}", name=f"Historical Flood Inundation · {state} {year or ''}".strip(), kind="wms", url=self.url, layers=name,
                organization="NRSC / ISRO (Bhuvan)", provenance="historical", layer_type="flood_inundation",
                attribution=self.settings.bhuvan_flood_attribution, period=year, bbox=ASSAM_BBOX if state == "Assam" else None,
                note="Satellite-derived annual flood inundation extent; historical evidence, not a current flood alert.", tags=["flood", "assam", "wms"],
            ))
        return out

    async def health(self) -> dict:
        now = time.time()
        if _CACHE["result"] and now - _CACHE["checked_at"] < CACHE_TTL_SECONDS:
            return {**_CACHE["result"], "cached": True}
        result = {"provider": self.key, "url": self.url, "status": "unavailable", "layers_available": 0, "latency_ms": None}
        try:
            started = time.perf_counter()
            async with httpx.AsyncClient(timeout=self.settings.external_layer_timeout_seconds, headers={"User-Agent": "PathSense/1.0 (hackathon research)"}) as client:
                response = await client.get(self.url, params={"service": "WMS", "request": "GetCapabilities", "version": "1.1.1"})
            latency = round((time.perf_counter() - started) * 1000)
            if response.status_code == 200 and "<Layer" in response.text:
                names = set(re.findall(r"<Name>([^<]+)</Name>", response.text))
                available = [l for l in self.settings.bhuvan_flood_layers if l in names]
                result.update(status="healthy" if available else "degraded", layers_available=len(available), latency_ms=latency, missing=[l for l in self.settings.bhuvan_flood_layers if l not in names])
            else:
                result.update(status="degraded", latency_ms=latency, detail=f"HTTP {response.status_code}")
        except Exception as exc:
            result.update(detail=type(exc).__name__)
        _CACHE.update(checked_at=now, result=result)
        return result

def external_layer_registry() -> list[GeospatialLayerProvider]:
    settings = get_settings()
    if not settings.external_layers_enabled:
        return []
    try:
        return [BhuvanFloodWMSProvider()]
    except ValueError:
        return []
