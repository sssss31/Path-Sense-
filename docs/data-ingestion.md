# Dataset ingestion

Hazard evidence enters PostGIS through the dataset registry (`dataset_sources`) and a
configurable importer. No dataset-specific Python is required: each source ships a
mapping config (JSON or YAML) describing the registry entry, property mapping and
predefined transformers.

```bash
cd backend
python -m app.ingestion.importer --config data/mappings/<mapping>.yaml --file data/<file>.geojson --dry-run
python -m app.ingestion.importer --config data/mappings/<mapping>.yaml --file data/<file>.geojson --mode skip-existing
```

Modes: `skip-existing` (default), `update-existing`, `fail-on-duplicate`. Formats: EPSG:4326 GeoJSON (`Polygon`/`MultiPolygon` zones, `Point` incidents) or CSV with latitude/longitude columns.

## Mapping config
`dataset` block: name, slug, provider, source_organization, source_url, dataset_version, license, hazard_category, `data_type` (`risk_zones` | `incidents`), `provenance_type` (`live` | `historical` | `estimated` | `simulated`), coverage_area, `coverage_bbox` `[min_lon, min_lat, max_lon, max_lat]`, crs.
`mapping`: candidate property names per normalized field (`category`, `severity`, `date`, `description`, `external_id`, `latitude`, `longitude`).
`transforms`: ordered predefined transformer names per field — `lowercase`, `uppercase`, `strip`, `to_int`, `to_float`, `parse_date` (optional `formats`), `severity_map` (optional `table`), `category_map` (optional `table`), `int_to_severity` (`scale: [min,max]`), `clamp_severity`, `null_replace` (`value`). Arbitrary code is rejected.
`defaults`, `required`, `duplicate_mode` are optional. Templates live in `backend/data/mappings/`.

## Validation and duplicates
Rejected: invalid coordinate range, unknown CRS, unsupported/empty geometry, unclosed rings, missing required fields. Shapely (optional) may repair mildly invalid polygons only when type and area are preserved; corrupted geometry is reported, never silently changed.
Every feature gets a deterministic fingerprint: dataset slug + external id (preferred) or a normalized geometry hash + event date + category. Fingerprints are unique per table, so re-imports report `duplicates`/`skipped`/`updated` instead of silently inserting.

## Report
Dry-run executes parsing, geometry/CRS validation, mapping, normalization and fingerprinting with no database writes. Every run prints total, valid, imported, updated, duplicates, skipped, invalid and elapsed time; real imports store the report on the registry entry (`metadata.last_import`) with `record_count`, `ingested_at` and status (`registered`, `validated`, `imported`, `failed`, `disabled`).

## Source manifest and layer types
`backend/data/sources.yaml` describes every known authoritative source (organization, URL, verified access mechanism, expected CRS, mapping file, allowed wording) without secrets. The `dataset` block of a mapping config may also set `layer_type` (`landslide_inventory`, `landslide_susceptibility`, `flood_hazard`, `flood_inundation`, `hazard_zones`, `incidents`), `attribution`, `period_start`/`period_end`, `access_method` and `source_metadata`. Inventory records become `HistoricalIncident`; susceptibility and flood zonation become `RiskZone`. Susceptibility classes use the `susceptibility_map` transformer (central table in `app/core/domain.py`); the original class is always stored in metadata. Dates and severity are never invented: missing dates reject incident records, missing severity records the config default with `original_severity: null`.

One-command GSI pipeline: drop the Bhukosh downloads (shapefile zip, .shp, .gpkg, GeoJSON or CSV) plus `download_metadata.yaml` into `backend/data/gsi/` and run `python scripts/import_gsi.py --check` (convert + dry-run) then `python scripts/import_gsi.py` (register, dry-run, import, count validation, sample spatial queries, demo-corridor coverage; reports in `data/gsi/reports/`). Acquisition helpers: `python -m app.ingestion.sources.gsi steps|convert` (manual GSI download → EPSG:4326 GeoJSON) and `python -m app.ingestion.sources.bhuvan capabilities|sample` (inspect the Bhuvan WMS; no vector conversion). Corridor snapshot: `python -m app.ingestion.snapshot --output data/snapshots/<name>` (authoritative datasets only unless `--include-simulated`).

The quality report now includes `source_records`, `valid_records`, `invalid_geometry`, `missing_coordinates`, `missing_fields`, `unknown_severity`, `coverage`, `provenance` and `layer_type`.

## Provenance rules
Imported files never become live automatically; only `provenance_type: live` may set `is_live`. Labels follow the claim rule: historical → "Historical Landslide Zone", estimated → "Flood-Prone Area", live → alert wording. Simulated datasets (the `data/demo` seeds) are used in demo mode and tests only and are excluded from live-mode queries. **No authoritative landslide or flood dataset ships with the repository** — see `backend/data/README.md`.
