import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingestion.config import MappingConfigError, load_config, validate_config
from app.ingestion.importer import ImportReport, prepare, read_features, run_import
from app.ingestion.mapping import fingerprint, geometry_hash, normalized
from app.ingestion.transformers import TransformError, apply_transforms
from app.ingestion.validation import GeometryError, ZONE_TYPES, POINT_TYPES, check_crs, validate_geometry

DATA = Path(__file__).resolve().parents[1] / "data"
ZONES_CONFIG = DATA / "mappings" / "demo_hazard_zones.yaml"
ZONES_FILE = DATA / "demo" / "demo_hazard_zones.geojson"
INCIDENT_CONFIG = DATA / "mappings" / "demo_incidents.yaml"
INCIDENT_FILE = DATA / "demo" / "demo_incidents.csv"

def square(x=91.0, y=25.0, size=0.1):
    return {"type": "Polygon", "coordinates": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]}

# --- transformers -------------------------------------------------------------
def test_predefined_transformers():
    assert apply_transforms(" High ", ["strip", "lowercase"]) == "high"
    assert apply_transforms("Very High", [{"name": "severity_map"}]) == 5
    assert apply_transforms("Debris Flow", ["lowercase", "category_map"]) == "landslide"
    assert apply_transforms(3, [{"name": "int_to_severity", "scale": [1, 3]}]) == 5
    assert apply_transforms(None, [{"name": "null_replace", "value": "other"}]) == "other"
    assert apply_transforms("2023-07-14", ["parse_date"]) == datetime(2023, 7, 14, tzinfo=timezone.utc)
    assert apply_transforms("14/07/2023", [{"name": "parse_date", "formats": ["%d/%m/%Y"]}]).month == 7
    assert apply_transforms("7", ["clamp_severity"]) == 5

def test_unknown_or_unsafe_transformers_are_rejected():
    with pytest.raises(TransformError):
        apply_transforms("x", ["__import__"])
    with pytest.raises(TransformError):
        apply_transforms("x", [{"name": "eval"}])
    with pytest.raises(MappingConfigError):
        validate_config({"dataset": {"name": "n", "slug": "s", "source_organization": "o", "hazard_category": "landslide", "data_type": "risk_zones", "provenance_type": "historical"}, "transforms": {"category": [{"name": "lowercase", "code": "os.system('x')"}]}})

# --- mapping + fingerprint ------------------------------------------------------
def test_mapping_uses_alternative_property_names():
    config = load_config(ZONES_CONFIG)
    feature = {"geometry": square(), "properties": {"hazard_type": "Landslide", "risk_level": "High", "event_date": "2023-07-14", "feature_id": "A1"}}
    values = normalized(feature, config)
    assert values["category"] == "landslide" and values["severity"] == 4 and values["external_id"] == "A1" and values["date"].year == 2023

def test_fingerprint_prefers_external_id_and_is_deterministic():
    feature = {"geometry": square()}
    a = fingerprint("ds", feature, {"external_id": "X1", "date": "2023-01-01", "category": "landslide"})
    b = fingerprint("ds", {"geometry": square(91.5)}, {"external_id": "X1", "date": "2023-01-01", "category": "landslide"})
    assert a == b  # same external id wins over different geometry
    c = fingerprint("ds", feature, {"external_id": None, "date": "2023-01-01", "category": "landslide"})
    d = fingerprint("ds", {"geometry": square(91.0000001)}, {"external_id": None, "date": "2023-01-01", "category": "landslide"})
    assert c == d  # geometry hash is normalised to 6 decimals
    assert c != fingerprint("other-ds", feature, {"external_id": None, "date": "2023-01-01", "category": "landslide"})
    assert geometry_hash(square()) == geometry_hash(json.loads(json.dumps(square())))

# --- validation ---------------------------------------------------------------------
def test_geometry_validation_rejects_bad_input():
    with pytest.raises(GeometryError): validate_geometry(None, ZONE_TYPES)
    with pytest.raises(GeometryError): validate_geometry({"type": "Point", "coordinates": [91, 25]}, ZONE_TYPES)
    with pytest.raises(GeometryError): validate_geometry({"type": "Polygon", "coordinates": [[[200, 25], [201, 25], [201, 26], [200, 25]]]}, ZONE_TYPES)
    with pytest.raises(GeometryError): validate_geometry({"type": "Polygon", "coordinates": [[[91, 25], [92, 25], [92, 26]]]}, ZONE_TYPES)
    with pytest.raises(GeometryError): validate_geometry({"type": "Polygon", "coordinates": []}, ZONE_TYPES)
    with pytest.raises(GeometryError): validate_geometry({"type": "Point", "coordinates": [91, 95]}, POINT_TYPES)
    assert validate_geometry(square(), ZONE_TYPES)["type"] == "Polygon"
    with pytest.raises(GeometryError): check_crs("EPSG:32646")
    check_crs("urn:ogc:def:crs:OGC:1.3:CRS84")

# --- dry run -----------------------------------------------------------------------------
def test_prepare_classifies_invalid_and_in_file_duplicates():
    config = load_config(ZONES_CONFIG)
    features, crs = read_features(ZONES_FILE, config)
    features = features + [features[0], {"type": "Feature", "geometry": None, "properties": {}}, {"type": "Feature", "geometry": {"type": "Point", "coordinates": [91, 25]}, "properties": {"hazard_type": "Landslide"}}]
    report = ImportReport("demo", "skip-existing", True)
    prepared = prepare(features, config, "demo", report)
    assert report.total == 7 and report.valid == 5 and report.invalid == 2
    assert sum(1 for p in prepared if p["in_file_duplicate"]) == 1
    assert report.bbox and report.bbox[0] >= 91.3 and report.bbox[2] <= 92.0
    assert len({p["fingerprint"] for p in prepared}) == 4

def test_dry_run_reports_counts_without_database_writes(tmp_path):
    result = asyncio.run(run_import(str(ZONES_CONFIG), str(ZONES_FILE), "skip-existing", dry_run=True))
    assert result["dry_run"] is True and result["would_write"] is False
    assert result["total_records"] == 4 and result["valid"] == 4 and result["invalid"] == 0
    assert {"imported", "updated", "duplicates", "skipped", "invalid", "elapsed_seconds"} <= set(result)
    incidents = asyncio.run(run_import(str(INCIDENT_CONFIG), str(INCIDENT_FILE), "skip-existing", dry_run=True))
    assert incidents["valid"] == 4 and incidents["dataset_spec"]["provenance_type"] == "simulated"

def test_dry_run_rejects_unknown_crs(tmp_path):
    bad = tmp_path / "bad.geojson"
    bad.write_text(json.dumps({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:32646"}}, "features": []}))
    with pytest.raises(GeometryError):
        asyncio.run(run_import(str(ZONES_CONFIG), str(bad), "skip-existing", dry_run=True))

def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        asyncio.run(run_import(str(ZONES_CONFIG), str(ZONES_FILE), "overwrite-everything", dry_run=True))
