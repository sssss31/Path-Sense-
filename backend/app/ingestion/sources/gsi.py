"""Geological Survey of India (Bhukosh / Bhusanket) acquisition helper.

Verified 2026-09-07:
* Bhukosh (https://bhukosh.gsi.gov.in/Bhukosh/Public) publishes landslide inventory
  and NLSM susceptibility as shapefiles for free download **after registration**
  (NDSAP). Downloads are interactive; there is no anonymous file URL.
* Bhusanket's map services (``gisserver/rest/services/.../FeatureServer``) answer
  ``{"code": 499, "message": "Token Required"}`` anonymously.

Therefore this module does **not** download anything. It converts a manually
downloaded shapefile/geodatabase export into EPSG:4326 GeoJSON/CSV that the
mapping-config importer accepts, and prints the manual steps. Authentication,
CAPTCHA and access controls are never circumvented.

    python -m app.ingestion.sources.gsi convert --input downloads/Landslide_Inventory.shp --output data/gsi/inventory.geojson
    python -m app.ingestion.sources.gsi steps
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

MANUAL_STEPS = """GSI landslide data (manual acquisition, no automated access):
1. Register a free account at https://bhukosh.gsi.gov.in/Bhukosh/Public (NDSAP terms).
2. Open the 'Landslide' theme; choose the state layer (Assam, Meghalaya, ...):
   - 'Landslide Inventory' (points, field-validated events)        -> layer_type landslide_inventory
   - 'Landslide Susceptibility (NLSM, 1:50K)' (polygons)             -> layer_type landslide_susceptibility
3. Download as Shapefile (zip). Record: download date, dataset version/date shown on the portal, licence text.
4. Convert to EPSG:4326 GeoJSON with this helper (uses ogr2ogr when available):
   python -m app.ingestion.sources.gsi convert --input <file.shp> --output data/gsi/<name>.geojson
5. Fill data/mappings/gsi_landslide_inventory.yaml / gsi_landslide_susceptibility.yaml (version, dates, coverage, licence).
6. Dry-run, review the quality report, then import:
   python -m app.ingestion.importer --config data/mappings/gsi_landslide_inventory.yaml --file data/gsi/inventory.geojson --dry-run
   python -m app.ingestion.importer --config data/mappings/gsi_landslide_inventory.yaml --file data/gsi/inventory.geojson
7. Verify corridor coverage: python scripts/validate_demo_corridor.py
Never label these layers as live alerts: inventory = historical observed events; susceptibility = terrain classification."""

def ogr2ogr_available() -> str | None:
    return shutil.which("ogr2ogr")

def convert(input_path: str, output_path: str, source_srs: str | None = None) -> dict:
    """Shapefile / GeoPackage / KML -> EPSG:4326 GeoJSON via ogr2ogr. Never alters attributes."""
    src, dst = Path(input_path), Path(output_path)
    if not src.exists():
        raise FileNotFoundError(f"input not found: {src}")
    tool = ogr2ogr_available()
    if not tool:
        raise RuntimeError("ogr2ogr (GDAL) is required for shapefile conversion; install GDAL or export GeoJSON from QGIS")
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [tool, "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-lco", "RFC7946=YES"]
    if source_srs:
        cmd += ["-s_srs", source_srs]
    cmd += [str(dst), str(src)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ogr2ogr failed: {result.stderr.strip()}")
    data = json.loads(dst.read_text())
    features = data.get("features", [])
    props = sorted({k for f in features for k in (f.get("properties") or {})})
    return {"output": str(dst), "features": len(features), "properties": props, "geometry_types": sorted({(f.get("geometry") or {}).get("type") for f in features if f.get("geometry")})}

def main(argv=None):
    parser = argparse.ArgumentParser(description="GSI landslide data helper (manual download + conversion)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("steps", help="print manual acquisition steps")
    conv = sub.add_parser("convert", help="convert a downloaded shapefile/GeoPackage to EPSG:4326 GeoJSON")
    conv.add_argument("--input", required=True); conv.add_argument("--output", required=True); conv.add_argument("--source-srs")
    args = parser.parse_args(argv)
    if args.command == "steps":
        print(MANUAL_STEPS); return
    print(json.dumps(convert(args.input, args.output, args.source_srs), indent=2))

if __name__ == "__main__":
    main()
