"""GSI Bhukosh import pipeline (steps 1-12 of docs/data-ingestion.md) for files placed in data/gsi/.

    cd backend && python scripts/import_gsi.py --check     # inspect, convert, dry-run; no database writes
    cd backend && python scripts/import_gsi.py             # full: register, dry-run, import, validate, corridor coverage
    python scripts/import_gsi.py --mode update-existing    # re-import a newer download

Nothing is downloaded here: Bhukosh requires an interactive registered login. The script
detects inventory/susceptibility files, converts shapefiles with ogr2ogr, merges the
operator-supplied download_metadata.yaml into the mapping configs (real version/dates
only; nothing is invented), runs the importer, validates counts with sample spatial
queries and reports corridor coverage. Machine-readable reports go to data/gsi/reports/.
"""
import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
GSI_DIR = BACKEND / "data" / "gsi"
REPORTS = GSI_DIR / "reports"
LAYERS = {
    "landslide_inventory": {"patterns": [r"inventor", r"landslide_?point", r"incid", r"ls_?pt"], "mapping": BACKEND / "data/mappings/gsi_landslide_inventory.yaml"},
    "landslide_susceptibility": {"patterns": [r"suscept", r"lsz", r"nlsm", r"hazard_?zon"], "mapping": BACKEND / "data/mappings/gsi_landslide_susceptibility.yaml"},
}
DATA_EXT = {".zip", ".shp", ".gpkg", ".geojson", ".json", ".csv", ".kml"}
CORRIDOR = "LINESTRING(91.7362 26.1445, 91.78 26.0, 91.82 25.9, 91.86 25.8, 91.88 25.7, 91.8933 25.5788)"

def log(msg: str):
    print(f"[gsi-import] {msg}")

def discover() -> dict[str, Path]:
    found = {}
    for path in sorted(GSI_DIR.iterdir()):
        if path.suffix.lower() not in DATA_EXT or path.name.startswith("."):
            continue
        for layer, spec in LAYERS.items():
            if layer not in found and any(re.search(p, path.stem, re.I) for p in spec["patterns"]):
                found[layer] = path
    return found

def convert(path: Path, workdir: Path) -> Path:
    """Return an EPSG:4326 GeoJSON/CSV path the importer accepts (shapefile/zip/gpkg/kml via ogr2ogr)."""
    if path.suffix.lower() in {".geojson", ".json", ".csv"}:
        return path
    tool = shutil.which("ogr2ogr")
    if not tool:
        raise RuntimeError("ogr2ogr (GDAL) is required to convert shapefiles; install GDAL or export GeoJSON from QGIS")
    source = path
    if path.suffix.lower() == ".zip":
        extract = workdir / path.stem
        with zipfile.ZipFile(path) as zf:
            zf.extractall(extract)
        shp = sorted(extract.rglob("*.shp")) + sorted(extract.rglob("*.gpkg"))
        if not shp:
            raise RuntimeError(f"{path.name} contains no .shp/.gpkg")
        source = shp[0]
        if len(shp) > 1:
            log(f"{path.name}: multiple layers, using {source.name}")
    out = workdir / f"{path.stem}.geojson"
    result = subprocess.run([tool, "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-lco", "RFC7946=YES", str(out), str(source)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ogr2ogr failed for {path.name}: {result.stderr.strip()[:300]}")
    return out

def build_config(layer: str, metadata: dict, workdir: Path, source_file: Path) -> Path:
    """Copy the mapping config and replace placeholders with real download metadata (never invented)."""
    cfg = yaml.safe_load(LAYERS[layer]["mapping"].read_text())
    d = cfg["dataset"]
    for key in ["dataset_version", "published_at", "downloaded_at", "license", "coverage_area", "period_start", "period_end", "coverage_bbox", "source_url"]:
        if metadata.get(key) not in (None, ""):
            d[key] = metadata[key]
    for key in list(d):
        if isinstance(d[key], str) and d[key].startswith("<"):
            if key in {"dataset_version", "coverage_area"}:
                d[key] = "unspecified (fill download_metadata.yaml)"
            else:
                d.pop(key)
    d["source_metadata"] = {**(d.get("source_metadata") or {}), "source_file": source_file.name, "converted_at": datetime.now(timezone.utc).isoformat(), "download_metadata": metadata}
    d.setdefault("access_method", "Manual download from Bhukosh (registered account); converted with ogr2ogr")
    if cfg.get("format") == "csv" and source_file.suffix.lower() != ".csv":
        cfg.pop("format", None)
    out = workdir / f"{layer}.generated.yaml"
    out.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    return out

async def validate_import(layer: str) -> dict:
    """Step 10-11: record count from the registry and sample spatial queries against the demo corridor."""
    from sqlalchemy import func, select
    from app.database.session import SessionLocal
    from app.models import DatasetSource, HistoricalIncident, RiskZone
    from app.schemas.analysis import Coordinate
    from app.services.coverage import calculate_dataset_route_coverage
    slug = f"gsi_{layer}"
    corridor_points = [Coordinate(lat=26.1445 - i * .0566, lng=91.7362 + i * .0157) for i in range(11)]
    async with SessionLocal() as session:
        ds = await session.scalar(select(DatasetSource).where(DatasetSource.slug == slug))
        if not ds:
            return {"layer": layer, "registered": False}
        model = HistoricalIncident if ds.data_type == "incidents" else RiskZone
        db_count = await session.scalar(select(func.count(model.id)).where(model.dataset_source_id == ds.id))
        corridor = func.ST_SetSRID(func.ST_GeomFromText(CORRIDOR), 4326)
        if model is RiskZone:
            near = await session.scalar(select(func.count(RiskZone.id)).where(RiskZone.dataset_source_id == ds.id, func.ST_Intersects(RiskZone.geometry, corridor)))
            sample = {"zones_intersecting_demo_corridor": int(near or 0)}
        else:
            near = await session.scalar(select(func.count(HistoricalIncident.id)).where(HistoricalIncident.dataset_source_id == ds.id, func.ST_DWithin(func.Geography(HistoricalIncident.geometry), func.Geography(corridor), 2000)))
            sample = {"incidents_within_2km_of_demo_corridor": int(near or 0)}
        coverage = calculate_dataset_route_coverage(corridor_points, ds)
        return {"layer": layer, "registered": True, "slug": slug, "registry_record_count": ds.record_count, "db_record_count": int(db_count or 0), "count_matches": ds.record_count == int(db_count or 0),
                "status": ds.status, "provenance": ds.provenance_type, "coverage_bbox": ds.coverage_bbox, "demo_corridor_coverage": coverage, "sample_spatial_query": sample}

async def run(check_only: bool, mode: str) -> int:
    from app.ingestion.importer import run_import
    REPORTS.mkdir(parents=True, exist_ok=True)
    files = discover()
    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "check_only": check_only, "mode": mode, "files": {k: v.name for k, v in files.items()}, "layers": {}}
    missing = [layer for layer in LAYERS if layer not in files]
    if not files:
        log(f"no Bhukosh files found in {GSI_DIR}. Nothing was imported.")
        log("Bhukosh requires a registered interactive download; see data/gsi/README.md for the exact steps, then re-run this script.")
        (REPORTS / "last_run.json").write_text(json.dumps({**summary, "result": "no_files"}, indent=2))
        return 2
    for layer in missing:
        log(f"warning: no file matched layer '{layer}' (patterns {LAYERS[layer]['patterns']}); it stays unavailable, not zero.")
    meta_path = GSI_DIR / "download_metadata.yaml"
    metadata = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}
    if not metadata:
        log("warning: download_metadata.yaml missing; registry version/dates will be recorded as unspecified (nothing is invented).")
    workdir = Path(tempfile.mkdtemp(prefix="gsi-import-"))
    exit_code = 0
    for layer, path in files.items():
        log(f"{layer}: source {path.name}")
        try:
            converted = convert(path, workdir)
            config = build_config(layer, metadata, workdir, path)
            log(f"{layer}: dry-run")
            dry = await run_import(str(config), str(converted), mode, dry_run=True)
            entry = {"source_file": path.name, "converted": str(converted), "dry_run": dry}
            log(f"{layer}: dry-run total={dry['total_records']} valid={dry['valid']} invalid={dry['invalid']} (geometry {dry['invalid_geometry']}, missing coords {dry['missing_coordinates']}, missing fields {dry['missing_fields']}, unknown severity {dry['unknown_severity']}) duplicates={dry['duplicates']}")
            if dry["errors"]:
                log(f"{layer}: first invalid records: {dry['errors'][:5]}")
            if dry["valid"] == 0:
                log(f"{layer}: no valid records; check the property mapping in {LAYERS[layer]['mapping'].name}"); exit_code = 1
            elif not check_only:
                log(f"{layer}: importing ({mode})")
                real = await run_import(str(config), str(converted), mode, dry_run=False)
                entry["import"] = real
                log(f"{layer}: imported={real['imported']} updated={real['updated']} duplicates={real['duplicates']} skipped={real['skipped']} invalid={real['invalid']} record_count={real.get('record_count')} in {real['elapsed_seconds']}s")
                validation = await validate_import(layer)
                entry["validation"] = validation
                log(f"{layer}: validation {json.dumps(validation, default=str)}")
                if not validation.get("count_matches", False):
                    exit_code = 1
            summary["layers"][layer] = entry
        except Exception as exc:
            log(f"{layer}: FAILED {type(exc).__name__}: {exc}")
            summary["layers"][layer] = {"source_file": path.name, "error": f"{type(exc).__name__}: {exc}"}
            exit_code = 1
    summary["result"] = "checked" if check_only else ("imported" if exit_code == 0 else "partial_failure")
    report_path = REPORTS / f"gsi_import_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(json.dumps(summary, indent=2, default=str))
    (REPORTS / "last_run.json").write_text(json.dumps(summary, indent=2, default=str))
    log(f"report written to {report_path}")
    if not check_only and exit_code == 0:
        log("next: python scripts/validate_demo_corridor.py  (confirms hazard_intelligence and corridor coverage)")
    return exit_code

def main(argv=None):
    parser = argparse.ArgumentParser(description="Import manually downloaded GSI Bhukosh landslide layers from data/gsi/")
    parser.add_argument("--check", action="store_true", help="convert + dry-run only, no database writes")
    parser.add_argument("--mode", default="skip-existing", choices=["skip-existing", "update-existing", "fail-on-duplicate"])
    args = parser.parse_args(argv)
    sys.exit(asyncio.run(run(args.check, args.mode)))

if __name__ == "__main__":
    main()
