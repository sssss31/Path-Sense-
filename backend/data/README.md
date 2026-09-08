# Hazard datasets

This folder holds **mapping configs** (`mappings/`) and, optionally, dataset files.

**No authoritative landslide or flood dataset ships with the repository.** The only
files under `demo/` are clearly labelled *simulated* demo seeds used for demo mode
and integration tests. They are registered with `provenance_type: simulated` and can
never be promoted to live; live mode ignores them entirely.

To import a real dataset (for example a Geological Survey of India landslide inventory
or a state flood-susceptibility layer):

1. Transform the file to EPSG:4326 GeoJSON (`Polygon`/`MultiPolygon` for zones, `Point`
   for incidents) or CSV with latitude/longitude columns.
2. Copy `mappings/template_landslide_zones.yaml` or `mappings/template_incidents_csv.yaml`,
   fill in the `dataset` block (organisation, version, licence, coverage, provenance) and
   adjust the property mapping / transformers for the file's column names.
3. Dry-run, review the report, then import:

```bash
cd backend
python -m app.ingestion.importer --config data/mappings/<your-mapping>.yaml --file data/<file>.geojson --dry-run
python -m app.ingestion.importer --config data/mappings/<your-mapping>.yaml --file data/<file>.geojson --mode skip-existing
```

Provenance vocabulary: `live`, `historical`, `estimated`, `simulated`. A historical
dataset produces "Historical Landslide Zone" labels; a susceptibility layer produces
"Flood-Prone Area"; only a real-time source may produce alert language.
