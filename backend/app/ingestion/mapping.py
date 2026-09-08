"""Field mapping, normalisation and deterministic feature fingerprints."""
import hashlib
import json
from datetime import datetime

from app.ingestion.transformers import apply_transforms

FINGERPRINT_PRECISION = 6  # decimal places (~0.1 m) for geometry normalisation

def first(props: dict, names: list[str]):
    lowered = {str(k).lower(): v for k, v in (props or {}).items()}
    for name in names:
        if name in props and props[name] not in (None, ""):
            return props[name]
        value = lowered.get(str(name).lower())
        if value not in (None, ""):
            return value
    return None

def normalized(feature: dict, config: dict | None = None) -> dict:
    """Map raw properties to normalized fields using a validated mapping config."""
    from app.ingestion.config import DEFAULT_MAPPING, DEFAULT_TRANSFORMS
    config = config or {}
    mapping = {**DEFAULT_MAPPING, **(config.get("mapping") or {})}
    transforms = {**DEFAULT_TRANSFORMS, **(config.get("transforms") or {})}
    defaults = config.get("defaults") or {}
    props = feature.get("properties") or {}
    out = {}
    for field, names in mapping.items():
        raw = first(props, names)
        value = apply_transforms(raw, transforms.get(field, []))
        if value in (None, "") and field in defaults:
            value = defaults[field]
        out[field] = value
    out["original_category"] = first(props, mapping["category"])
    out["original_severity"] = first(props, mapping["severity"])
    if out.get("external_id") is not None:
        out["external_id"] = str(out["external_id"]).strip()
    return out

def _round_coords(node):
    if isinstance(node, (list, tuple)) and node and isinstance(node[0], (int, float)):
        return [round(float(node[0]), FINGERPRINT_PRECISION), round(float(node[1]), FINGERPRINT_PRECISION)]
    if isinstance(node, (list, tuple)):
        return [_round_coords(x) for x in node]
    return node

def geometry_hash(geometry: dict | None) -> str:
    canonical = {"type": (geometry or {}).get("type"), "coordinates": _round_coords((geometry or {}).get("coordinates"))}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def fingerprint(dataset_id, feature: dict, values: dict) -> str:
    """Deterministic identity: dataset + external id (preferred) or normalized geometry hash + date + category."""
    date = values.get("date")
    if isinstance(date, datetime):
        date = date.date().isoformat()
    identity = f"ext:{values['external_id']}" if values.get("external_id") else f"geom:{geometry_hash(feature.get('geometry'))}"
    raw = f"{dataset_id}|{identity}|{date or ''}|{values.get('category') or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()
