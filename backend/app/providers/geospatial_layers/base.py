"""External geospatial layer providers (remote WMS/tiles).

Remote layers are rendered by the map client directly from official services;
the backend only publishes *which* layers exist, with provenance, period and
attribution. URLs are validated against a trusted host allowlist so neither a
dataset record nor a request can turn the backend into an open proxy.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from app.core.config import get_settings

class UntrustedLayerURL(ValueError):
    pass

def validate_external_url(url: str) -> str:
    parsed = urlparse(url)
    settings = get_settings()
    if parsed.scheme != "https":
        raise UntrustedLayerURL("external layer URLs must use https")
    host = (parsed.hostname or "").lower()
    if host not in {h.lower() for h in settings.external_layer_allowed_hosts}:
        raise UntrustedLayerURL(f"host {host!r} is not in external_layer_allowed_hosts")
    if parsed.username or parsed.password:
        raise UntrustedLayerURL("credentials in external layer URLs are not allowed")
    return url

@dataclass
class ExternalLayer:
    id: str
    name: str                 # human label following the claim rule
    kind: str                 # wms | tile
    url: str
    layers: str               # WMS LAYERS parameter
    organization: str
    provenance: str           # historical | live | estimated
    layer_type: str           # flood_inundation | flood_hazard | landslide_susceptibility ...
    attribution: str
    period: str | None = None
    format: str = "image/png"
    transparent: bool = True
    version: str = "1.1.1"
    srs: str = "EPSG:4326"
    bbox: list[float] | None = None
    opacity: float = 0.6
    note: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

class GeospatialLayerProvider(ABC):
    key: str = "base"

    @abstractmethod
    def layers(self) -> list[ExternalLayer]: ...

    @abstractmethod
    async def health(self) -> dict: ...
