"""Backward-compatible wrapper. Prefer `python -m app.ingestion.importer --config ... --file ...`."""
import argparse, asyncio, json
from app.ingestion.import_risk_zones import legacy_config
from app.ingestion.importer import run_import
async def run(path, source, dry_run=False):
    result = await run_import(legacy_config(source, "incidents"), path, "skip-existing", dry_run); print(json.dumps(result, default=str)); return result
if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("path"); p.add_argument("--source", required=True); p.add_argument("--dry-run", action="store_true"); a = p.parse_args(); asyncio.run(run(a.path, a.source, a.dry_run))
