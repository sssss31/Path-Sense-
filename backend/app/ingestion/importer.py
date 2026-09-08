"""Unified hazard dataset importer.

    python -m app.ingestion.importer --config data/mappings/demo_hazard_zones.yaml --file data/demo/demo_hazard_zones.geojson --dry-run
    python -m app.ingestion.importer --config <mapping.yaml> --file <geojson|csv> --mode skip-existing|update-existing|fail-on-duplicate

Dry-run performs parsing, geometry/CRS validation, mapping, normalisation and
fingerprinting without any database write. Every record is classified as
new / duplicate / updated / invalid / skipped and counts are always reported.
"""
import argparse
import asyncio
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.core.domain import HAZARD_CATEGORIES
from app.ingestion.config import load_config
from app.ingestion.mapping import fingerprint, normalized
from app.ingestion.validation import GeometryError, POINT_TYPES, ZONE_TYPES, bbox_of, check_crs, crs_name, validate_geometry
from app.models import HistoricalIncident, RiskZone
from app.services.datasets import DatasetRegistryService

DUPLICATE_MODES = ["skip-existing", "update-existing", "fail-on-duplicate"]

class ImportReport:
    def __init__(self, dataset: str, mode: str, dry_run: bool):
        self.dataset = dataset; self.mode = mode; self.dry_run = dry_run
        self.total = 0; self.valid = 0; self.imported = 0; self.updated = 0; self.duplicates = 0; self.skipped = 0; self.invalid = 0
        self.errors: list[dict] = []; self.started = time.perf_counter(); self.db_duplicate_check = True; self.bbox: list[float] | None = None
        self.invalid_geometry = 0; self.missing_coordinates = 0; self.missing_fields = 0; self.unknown_severity = 0; self.provenance = None; self.layer_type = None

    def error(self, index, message):
        self.invalid += 1
        text = str(message).lower()
        if "empty feature" in text or "empty geometry" in text or "coordinates" in text and "missing" in text: self.missing_coordinates += 1
        elif "geometry" in text or "ring" in text or "coordinate" in text or "position" in text: self.invalid_geometry += 1
        elif "severity" in text or "susceptib" in text: self.unknown_severity += 1
        elif "missing" in text: self.missing_fields += 1
        if len(self.errors) < 50:
            self.errors.append({"record": index, "error": str(message)})

    def to_dict(self) -> dict:
        return {"dataset": self.dataset, "mode": self.mode, "dry_run": self.dry_run, "total_records": self.total, "valid": self.valid, "imported": self.imported,
                "updated": self.updated, "duplicates": self.duplicates, "skipped": self.skipped, "invalid": self.invalid, "elapsed_seconds": round(time.perf_counter() - self.started, 3),
                "database_duplicate_check": self.db_duplicate_check, "coverage_bbox_observed": self.bbox, "errors": self.errors, "completed_at": datetime.now(timezone.utc).isoformat(),
                "source_records": self.total, "valid_records": self.valid, "invalid_geometry": self.invalid_geometry, "missing_coordinates": self.missing_coordinates,
                "missing_fields": self.missing_fields, "unknown_severity": self.unknown_severity, "provenance": self.provenance, "layer_type": self.layer_type,
                "coverage": {"bbox": self.bbox, "source": "observed"} if self.bbox else None}

    def summary(self) -> str:
        lines = [f"Dataset: {self.dataset}", f"Mode: {self.mode}{' (dry run)' if self.dry_run else ''}", f"Total records: {self.total:,}", f"Valid: {self.valid:,}",
                 f"Imported: {self.imported:,}", f"Updated: {self.updated:,}", f"Duplicates: {self.duplicates:,}", f"Skipped: {self.skipped:,}", f"Invalid: {self.invalid:,}",
                 f"Elapsed time: {round(time.perf_counter() - self.started, 2)}s"]
        if not self.db_duplicate_check:
            lines.append("Note: database duplicate check skipped (no database available); duplicates counted within file only.")
        return "\n".join(lines)

def read_features(path: Path, config: dict) -> tuple[list[dict], str]:
    """Return GeoJSON-like features from GeoJSON or CSV, plus CRS name."""
    fmt = (config.get("format") or path.suffix.lstrip(".")).lower()
    if fmt in {"geojson", "json"}:
        data = json.loads(path.read_text())
        if data.get("type") == "Feature":
            return [data], crs_name(data)
        if data.get("type") != "FeatureCollection":
            raise ValueError("GeoJSON must be a FeatureCollection or Feature")
        return list(data.get("features") or []), crs_name(data)
    if fmt == "csv":
        mapping = config["mapping"]
        features = []
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                lat = _first_csv(row, mapping.get("latitude", [])); lon = _first_csv(row, mapping.get("longitude", []))
                geometry = None
                if lat not in (None, "") and lon not in (None, ""):
                    try:
                        geometry = {"type": "Point", "coordinates": [float(lon), float(lat)]}
                    except ValueError:
                        geometry = {"type": "Point", "coordinates": [lon, lat]}
                features.append({"type": "Feature", "geometry": geometry, "properties": dict(row)})
        return features, config.get("crs", "EPSG:4326")
    raise ValueError(f"unsupported file format {fmt!r}; use GeoJSON or CSV")

def _first_csv(row: dict, names: list[str]):
    lowered = {k.lower(): v for k, v in row.items() if k}
    for name in names:
        if row.get(name) not in (None, ""):
            return row[name]
        if lowered.get(str(name).lower()) not in (None, ""):
            return lowered[str(name).lower()]
    return None

def prepare(features: list[dict], config: dict, dataset_key: str, report: ImportReport) -> list[dict]:
    """Validate + normalise + fingerprint every feature; no I/O."""
    dataset = config["dataset"]
    report.provenance = report.provenance or dataset.get("provenance_type"); report.layer_type = report.layer_type or dataset.get("layer_type")
    allowed = ZONE_TYPES if dataset["data_type"] == "risk_zones" else POINT_TYPES
    prepared: list[dict] = []
    seen: set[str] = set()
    bbox = None
    for index, feature in enumerate(features):
        report.total += 1
        try:
            if not feature or (not feature.get("geometry") and not feature.get("properties")):
                raise GeometryError("empty feature")
            if feature.get("properties") and not feature.get("geometry"):
                raise GeometryError("missing coordinates for feature")
            geometry = validate_geometry(feature.get("geometry"), allowed)
            values = normalized(feature, config)
            for field in config.get("required", []):
                if field != "geometry" and values.get(field) in (None, ""):
                    raise ValueError(f"missing required field {field!r}")
            category = values.get("category") or dataset["hazard_category"]
            if category not in HAZARD_CATEGORIES:
                category = "other"
            severity = values.get("severity")
            if severity is None:
                severity = config.get("defaults", {}).get("severity")
            if severity is None:
                raise ValueError("missing severity (add a mapping, transformer or default)")
            severity = max(1, min(5, int(severity)))
            if dataset["data_type"] == "incidents" and values.get("date") is None:
                raise ValueError("missing event date for incident")
            values["category"] = category; values["severity"] = severity
            fp = fingerprint(dataset_key, {"geometry": geometry}, values)
            fb = bbox_of(geometry)
            bbox = fb if bbox is None else [min(bbox[0], fb[0]), min(bbox[1], fb[1]), max(bbox[2], fb[2]), max(bbox[3], fb[3])]
            in_file_duplicate = fp in seen
            seen.add(fp)
            prepared.append({"index": index, "geometry": geometry, "values": values, "fingerprint": fp, "in_file_duplicate": in_file_duplicate, "properties": feature.get("properties") or {}})
            report.valid += 1
        except Exception as exc:
            report.error(index, exc)
    report.bbox = [round(x, 5) for x in bbox] if bbox else None
    return prepared

def zone_values(item: dict, dataset_row, dataset: dict) -> dict:
    v = item["values"]
    status = "live" if dataset_row.is_live else dataset["provenance_type"] if dataset["provenance_type"] != "live" else "historical"
    return dict(dataset_source_id=dataset_row.id, fingerprint=item["fingerprint"], category=v["category"], severity=v["severity"], status=status, source=dataset_row.name[:120],
                geometry=func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(item["geometry"])), 4326)),
                metadata_json={"external_id": v.get("external_id"), "event_date": v["date"].isoformat() if isinstance(v.get("date"), datetime) else v.get("date"), "description": v.get("description"),
                               "original_category": v.get("original_category"), "original_severity": v.get("original_severity"), "dataset_version": dataset_row.dataset_version,
                               "provenance_type": dataset_row.provenance_type, "source_url": dataset_row.source_url, "original_properties": _jsonable(item["properties"])})

def incident_values(item: dict, dataset_row, dataset: dict) -> dict:
    v = item["values"]
    lon, lat = item["geometry"]["coordinates"][:2]
    return dict(dataset_source_id=dataset_row.id, fingerprint=item["fingerprint"], category=v["category"], severity=v["severity"], occurred_at=v["date"],
                geometry=func.ST_SetSRID(func.ST_Point(lon, lat), 4326), source=dataset_row.name[:120], description=str(v.get("description") or ""),
                metadata_json={"external_id": v.get("external_id"), "original_category": v.get("original_category"), "original_severity": v.get("original_severity"),
                               "dataset_version": dataset_row.dataset_version, "provenance_type": dataset_row.provenance_type, "status": "historical", "original_properties": _jsonable(item["properties"])})

def _jsonable(props: dict) -> dict:
    return json.loads(json.dumps(props, default=str))

async def run_import(config_path: str, file_path: str, mode: str = "skip-existing", dry_run: bool = False, session_factory=None) -> dict:
    if mode not in DUPLICATE_MODES:
        raise ValueError(f"mode must be one of {DUPLICATE_MODES}")
    config = load_config(config_path)
    dataset = config["dataset"]
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"dataset file not found: {path}")
    report = ImportReport(dataset["name"], mode, dry_run)
    report.provenance = dataset.get("provenance_type"); report.layer_type = dataset.get("layer_type")
    features, crs = read_features(path, config)
    check_crs(crs)
    if config.get("crs", "EPSG:4326") not in {"EPSG:4326", "CRS84", "WGS84"}:
        raise GeometryError(f"mapping config declares CRS {config['crs']!r}; transform to EPSG:4326 first")
    prepared = prepare(features, config, dataset["slug"], report)
    if session_factory is None:
        from app.database.session import SessionLocal
        session_factory = SessionLocal
    model = RiskZone if dataset["data_type"] == "risk_zones" else HistoricalIncident
    values_for = zone_values if dataset["data_type"] == "risk_zones" else incident_values

    async with session_factory() as session:
        registry = DatasetRegistryService()
        existing: dict[str, object] = {}
        try:
            fps = [p["fingerprint"] for p in prepared]
            rows = []
            for chunk in range(0, len(fps), 500):
                rows.extend((await session.scalars(select(model).where(model.fingerprint.in_(fps[chunk:chunk + 500])))).all())
            existing = {r.fingerprint: r for r in rows}
        except Exception:
            await session.rollback()
            report.db_duplicate_check = False
        if dry_run:
            for item in prepared:
                if item["in_file_duplicate"] or item["fingerprint"] in existing:
                    report.duplicates += 1
                    if mode == "skip-existing": report.skipped += 1
                    elif mode == "update-existing": report.updated += 1
                else:
                    report.imported += 1
            if mode == "fail-on-duplicate" and report.duplicates:
                report.imported = 0
            result = report.to_dict(); result["dataset_spec"] = dataset; result["would_write"] = False
            return result
        if not report.db_duplicate_check:
            raise RuntimeError("database unavailable; cannot import (dry-run still works)")
        dataset_row = await registry.register(session, {**dataset, "coverage_bbox": dataset.get("coverage_bbox") or report.bbox})
        if mode == "fail-on-duplicate" and any(p["in_file_duplicate"] or p["fingerprint"] in existing for p in prepared):
            report.duplicates = sum(1 for p in prepared if p["in_file_duplicate"] or p["fingerprint"] in existing)
            # A refused re-import never invalidates records already imported; only an empty dataset becomes "failed".
            await registry.record_import(session, dataset_row, {**report.to_dict(), "failed": "duplicates present"}, dataset_row.record_count, "failed" if not dataset_row.record_count else dataset_row.status)
            await session.commit()
            raise RuntimeError(f"{report.duplicates} duplicate record(s) present and mode is fail-on-duplicate")
        for item in prepared:
            duplicate_of = existing.get(item["fingerprint"])
            if item["in_file_duplicate"]:
                report.duplicates += 1; report.skipped += 1; continue
            if duplicate_of is not None:
                report.duplicates += 1
                if mode == "update-existing":
                    for k, v in values_for(item, dataset_row, dataset).items():
                        setattr(duplicate_of, k, v)
                    report.updated += 1
                else:
                    report.skipped += 1
                continue
            session.add(model(**values_for(item, dataset_row, dataset)))
            report.imported += 1
        await session.flush()
        count = await session.scalar(select(func.count(model.id)).where(model.dataset_source_id == dataset_row.id))
        await registry.record_import(session, dataset_row, report.to_dict(), int(count or 0), "imported" if (report.imported or report.updated or count) else "validated")
        await session.commit()
        result = report.to_dict(); result["dataset_id"] = str(dataset_row.id); result["record_count"] = int(count or 0); result["would_write"] = True
        return result

def main(argv=None):
    parser = argparse.ArgumentParser(description="Import a hazard dataset using a mapping config.")
    parser.add_argument("--config", required=True, help="Mapping config (JSON or YAML)")
    parser.add_argument("--file", required=True, help="GeoJSON or CSV dataset file")
    parser.add_argument("--mode", default="skip-existing", choices=DUPLICATE_MODES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report")
    args = parser.parse_args(argv)
    result = asyncio.run(run_import(args.config, args.file, args.mode, args.dry_run))
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        r = ImportReport(result["dataset"], result["mode"], result["dry_run"])
        for key in ["total", "valid", "imported", "updated", "duplicates", "skipped", "invalid"]:
            setattr(r, key, result.get(key if key != "total" else "total_records", 0))
        r.db_duplicate_check = result["database_duplicate_check"]
        print(r.summary())
        if result["errors"]:
            print("Invalid records (first 50):")
            for e in result["errors"]:
                print(f"  #{e['record']}: {e['error']}")
    return result

if __name__ == "__main__":
    main()
