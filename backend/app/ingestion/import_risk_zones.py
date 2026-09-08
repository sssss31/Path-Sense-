"""Backward-compatible wrapper. Prefer `python -m app.ingestion.importer --config ... --file ...`.

Imports EPSG:4326 GeoJSON polygons using the default property mapping and a
historical provenance registry entry derived from `--source`.
"""
import argparse, asyncio, json, re, tempfile
from pathlib import Path
from app.ingestion.importer import run_import
def legacy_config(source: str, data_type: str, category: str = "landslide") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-") or "legacy-dataset"
    config = {"dataset": {"name": source, "slug": slug, "provider": source, "source_organization": source, "dataset_version": "unversioned", "hazard_category": category, "data_type": data_type, "provenance_type": "historical"}, "defaults": {"severity": 1}}
    if data_type == "incidents": config["format"] = "csv"
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(config, handle); handle.close(); return handle.name
async def run(path, source, dry_run=False):
    result = await run_import(legacy_config(source, "risk_zones"), path, "skip-existing", dry_run); print(json.dumps(result, default=str)); return result
if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("path"); p.add_argument("--source", required=True); p.add_argument("--dry-run", action="store_true"); a = p.parse_args(); asyncio.run(run(a.path, a.source, a.dry_run))
