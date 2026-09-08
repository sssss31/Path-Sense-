# GSI Bhukosh downloads (drop folder)

Place the files downloaded manually from https://bhukosh.gsi.gov.in/Bhukosh/Public here
(requires a free registered account; the portal cannot be fetched automatically and
access controls are never bypassed). Accepted: the Bhukosh shapefile `.zip`, an unzipped
`.shp` set, `.gpkg`, or an EPSG:4326 `.geojson`/`.csv` you exported yourself.

Expected layers (one file each):

| File name pattern (case-insensitive) | Layer | Mapping config |
|---|---|---|
| `*inventory*` or `*landslide_point*` or `*incid*` | Field-validated landslide inventory (points) | `data/mappings/gsi_landslide_inventory.yaml` |
| `*suscept*` or `*lsz*` or `*nlsm*` | NLSM landslide susceptibility (polygons) | `data/mappings/gsi_landslide_susceptibility.yaml` |

Also add `download_metadata.yaml` next to the files so the registry records real source facts:

```yaml
dataset_version: "Bhukosh landslide layers, Meghalaya & Assam, portal date 2025-xx-xx"
published_at: "2025-01-15"          # as shown on the portal, if available
downloaded_at: "2026-09-08"
license: "NDSAP – attribute Geological Survey of India"
coverage_area: "Meghalaya, Assam"
period_start: "2000-01-01"          # earliest event date in the inventory (or mapping campaign start)
period_end: "2024-12-31"
```

Then run the pipeline:

```bash
cd backend
python scripts/import_gsi.py --check          # inspect files, convert, dry-run only
python scripts/import_gsi.py                  # convert, register, dry-run, import, validate, coverage report
```

Reports are written to `data/gsi/reports/`. Files in this folder are ignored by git except this README.
