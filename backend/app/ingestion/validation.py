"""Geometry / CRS validation for dataset imports.

Rejects out-of-range coordinates, unsupported or empty geometry, unknown CRS
and structurally broken rings. Shapely (optional) may repair mildly invalid
polygons; badly corrupted geometry is flagged, never silently altered.
"""
import json

ACCEPTED_CRS = {"EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326", "CRS84", "WGS84", "OGC:CRS84"}
ZONE_TYPES = {"Polygon", "MultiPolygon"}
POINT_TYPES = {"Point"}

class GeometryError(ValueError):
    pass

def crs_name(collection: dict) -> str:
    """Resolve the GeoJSON `crs` member. GeoJSON (RFC 7946) defaults to WGS84/CRS84."""
    crs = collection.get("crs")
    if not crs:
        return "EPSG:4326"
    if isinstance(crs, str):
        return crs
    name = (crs.get("properties") or {}).get("name") or crs.get("name")
    return str(name) if name else "unknown"

def check_crs(name: str) -> None:
    if name not in ACCEPTED_CRS and name.upper() not in {x.upper() for x in ACCEPTED_CRS}:
        raise GeometryError(f"unknown or unsupported CRS {name!r}; transform to EPSG:4326 before import")

def _check_position(pos) -> None:
    if not isinstance(pos, (list, tuple)) or len(pos) < 2:
        raise GeometryError("position must be [lon, lat]")
    lon, lat = pos[0], pos[1]
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise GeometryError("coordinates must be numeric")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise GeometryError(f"coordinate outside EPSG:4326 bounds: ({lon}, {lat})")

def _check_ring(ring) -> None:
    if not isinstance(ring, list) or len(ring) < 4:
        raise GeometryError("polygon ring needs at least 4 positions")
    for pos in ring:
        _check_position(pos)
    if ring[0][:2] != ring[-1][:2]:
        raise GeometryError("polygon ring is not closed")

def validate_geometry(geometry: dict | None, allowed: set[str]) -> dict:
    if not geometry or not isinstance(geometry, dict):
        raise GeometryError("empty feature geometry")
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype not in allowed:
        raise GeometryError(f"unsupported geometry type {gtype!r}; expected {sorted(allowed)}")
    if coords in (None, []):
        raise GeometryError("empty geometry coordinates")
    if gtype == "Point":
        _check_position(coords)
    elif gtype == "Polygon":
        for ring in coords:
            _check_ring(ring)
    elif gtype == "MultiPolygon":
        if not any(coords):
            raise GeometryError("empty MultiPolygon")
        for polygon in coords:
            for ring in polygon:
                _check_ring(ring)
    return maybe_repair(geometry)

def maybe_repair(geometry: dict) -> dict:
    """Use Shapely when available to detect invalid polygons and repair only mild self-touching cases.

    A repair is accepted only when the result keeps the same geometry family and
    its area stays within 1% of the original; anything else is rejected.
    """
    try:
        from shapely.geometry import shape, mapping
        from shapely.validation import make_valid
    except Exception:
        return geometry
    geom = shape(geometry)
    if geom.is_empty:
        raise GeometryError("empty geometry")
    if geom.is_valid or geom.geom_type == "Point":
        return geometry
    repaired = make_valid(geom)
    same_family = repaired.geom_type in {"Polygon", "MultiPolygon"} and geom.geom_type in {"Polygon", "MultiPolygon"}
    if not same_family or geom.area == 0 or abs(repaired.area - geom.area) / geom.area > 0.01:
        raise GeometryError("invalid geometry could not be safely repaired")
    return json.loads(json.dumps(mapping(repaired)))

def bbox_of(geometry: dict) -> list[float]:
    lons, lats = [], []
    def walk(node):
        if isinstance(node, (list, tuple)) and node and isinstance(node[0], (int, float)):
            lons.append(node[0]); lats.append(node[1])
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
    walk(geometry.get("coordinates"))
    return [min(lons), min(lats), max(lons), max(lats)]
