"""Mapping-config loader for dataset imports (JSON or YAML).

A config declares the dataset registry entry, how source properties map onto
normalized fields, and which predefined transformers to apply. No dataset-
specific Python is needed per source.

Example (YAML):

    dataset:
      name: Meghalaya Historical Landslide Inventory
      slug: meghalaya-landslides-2024
      source_organization: Geological Survey of India
      hazard_category: landslide
      data_type: risk_zones          # or incidents
      provenance_type: historical    # live | historical | estimated | simulated
      coverage_area: Meghalaya
      coverage_bbox: [89.8, 25.0, 92.9, 26.2]
    mapping:
      category: [hazard_type, type, category]
      severity: [risk_level, severity, class]
      date: [event_date, date, occurred_on]
      description: [description, remarks, details]
      external_id: [id, feature_id]
    transforms:
      category: [strip, lowercase, category_map]
      severity: [{name: severity_map}]
      date: [parse_date]
    defaults:
      category: landslide
      severity: 3
    required: [geometry]
"""
import json
from pathlib import Path

from app.core.domain import DATASET_DATA_TYPES, HAZARD_CATEGORIES

DEFAULT_MAPPING = {
    "category": ["hazard_type", "type", "category", "hazard", "class_name"],
    "severity": ["risk_level", "severity", "class", "susceptibility", "hazard_class", "level"],
    "date": ["event_date", "date", "occurred_on", "occurred_at", "timestamp", "year"],
    "description": ["description", "remarks", "details", "note", "notes", "name"],
    "external_id": ["id", "feature_id", "objectid", "OBJECTID", "gid", "uid", "code"],
    "latitude": ["latitude", "lat", "y"],
    "longitude": ["longitude", "lon", "lng", "long", "x"],
}
DEFAULT_TRANSFORMS = {
    "category": ["strip", "lowercase", "category_map"],
    "severity": [{"name": "severity_map"}],
    "date": ["parse_date"],
    "description": ["strip"],
    "latitude": ["to_float"],
    "longitude": ["to_float"],
}
REQUIRED_DATASET_KEYS = ["name", "slug", "source_organization", "hazard_category", "data_type", "provenance_type"]

class MappingConfigError(ValueError):
    pass

def load_config(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise MappingConfigError(f"mapping config not found: {path}")
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise MappingConfigError("PyYAML is required for YAML mapping files") from exc
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    return validate_config(raw or {})

def validate_config(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise MappingConfigError("mapping config must be an object")
    dataset = raw.get("dataset") or {}
    missing = [k for k in REQUIRED_DATASET_KEYS if not dataset.get(k)]
    if missing:
        raise MappingConfigError(f"dataset block missing required keys: {missing}")
    if dataset["hazard_category"] not in HAZARD_CATEGORIES:
        raise MappingConfigError(f"hazard_category must be one of {HAZARD_CATEGORIES}")
    if dataset["data_type"] not in DATASET_DATA_TYPES:
        raise MappingConfigError(f"data_type must be one of {DATASET_DATA_TYPES}")
    mapping = {**DEFAULT_MAPPING, **{k: (v if isinstance(v, list) else [v]) for k, v in (raw.get("mapping") or {}).items()}}
    transforms = {**DEFAULT_TRANSFORMS, **(raw.get("transforms") or {})}
    for field, specs in transforms.items():
        if not isinstance(specs, list):
            raise MappingConfigError(f"transforms.{field} must be a list of transformer names")
        for spec in specs:
            if not isinstance(spec, (str, dict)) or (isinstance(spec, dict) and "name" not in spec):
                raise MappingConfigError(f"transforms.{field} contains an invalid spec: {spec!r}")
            if isinstance(spec, dict) and any(k in {"code", "eval", "exec", "lambda", "python"} for k in spec):
                raise MappingConfigError("transform specs may not contain executable code")
    return {
        "dataset": dataset, "mapping": mapping, "transforms": transforms, "defaults": raw.get("defaults") or {},
        "required": raw.get("required") or ["geometry"], "crs": raw.get("crs") or dataset.get("crs") or "EPSG:4326",
        "duplicate_mode": raw.get("duplicate_mode") or "skip-existing", "format": raw.get("format"),
    }
