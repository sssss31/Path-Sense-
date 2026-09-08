# Authoritative hazard data

Verified on 2026-09-07 from the build environment. Nothing below was scraped; every
mechanism listed is either an official machine interface used as documented or a
manual portal download. Access controls were never bypassed.

## Summary of access mechanisms

| Source | What we verified | Automated access | Platform use |
|---|---|---|---|
| GSI Bhusanket ArcGIS services (`gisserver/rest/services/Hosted/India_All_Landslided/FeatureServer/0`, `GSI/Landslide_Polygon/FeatureServer`, `GSI/Susceptibility/ImageServer`) | Discovered from the public portal config; all answer `{"code":499,"message":"Token Required"}` anonymously | **No** (credentials required; not requested) | Documented only |
| GSI Bhukosh (`https://bhukosh.gsi.gov.in/Bhukosh/Public`) | Official download portal (shapefiles, NDSAP). Unreachable from this network (connection timeout); public docs state free download after registration | **No** (interactive registration + download) | Manual download → `app/ingestion/sources/gsi.py convert` → mapping configs |
| Bhusanket static JSON (`json/Landslide Incidence/IncidentContent.json`) | Public narrative incident list (year, state, title, description, PDF flag) — **no coordinates** | Yes, but not spatial | Not imported (cannot become HistoricalIncident without invented coordinates) |
| NRSC/ISRO Bhuvan flood WMS (`https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe`) | WMS 1.1.1 GetCapabilities + GetMap anonymous, EPSG:4326, image/png; 121 layers incl. Assam annual inundation `as_fld_1998`…`as_fld_2010` (bbox 89.70, 24.13 → 96.02, 27.97) and dated 2011-2013 event layers; contact NRSC/ISRO | **Yes (render only)** | Remote WMS layer on the Risk Map (`GET /map-layers`), never converted to polygons |
| NRSC Flood Hazard Zonation (NDEM/Bhuvan) | Bihar atlas documented (1998-2010 satellite data); Assam/Meghalaya vector export not found anonymously; `bhuvan-vec1/vec2` thematic WMS timed out | **No** | Mapping config prepared (`nrsc_flood_hazard.yaml`) for a manual vector export |

## GSI landslide inventory
- **Organization:** Geological Survey of India. **Dataset:** field-validated landslide inventory (Bhukosh "Landslide" theme; Bhusanket "India_All_Landslided").
- **Official URLs:** https://bhukosh.gsi.gov.in/Bhukosh/Public · https://bhusanket.gsi.gov.in/
- **Coverage:** national, state-wise layers (Assam, Meghalaya, other NE states). **Temporal:** event dates per record where published.
- **Data type / CRS:** point shapefile; publish CRS varies (GCS WGS84 typical) → converted to EPSG:4326 by `ogr2ogr`.
- **Access method:** manual — register on Bhukosh, download the shapefile zip into `backend/data/gsi/` with a `download_metadata.yaml` (see `backend/data/gsi/README.md`), then `python scripts/import_gsi.py --check` and `python scripts/import_gsi.py` (conversion, registration, dry-run, import, validation and corridor coverage in one run).
- **Provenance:** `historical`; `layer_type: landslide_inventory`; records become **HistoricalIncident** (category landslide, `occurred_at` only when the source has a date, severity default recorded with `original_severity: null`, external id, description, original properties).
- **Used for:** historical landslide proximity (incidents within 2 km), inventory coverage in confidence, Risk Map "Historical Landslide Inventory".
- **Not used as:** live landslide alert. **Allowed wording:** "Historical Landslide Inventory", "N recorded landslide incident(s) within 2 km".
- **Limitations:** no anonymous machine access; dates/severity may be missing (never invented).

## GSI landslide susceptibility (NLSM)
- **Dataset:** National Landslide Susceptibility Mapping, 1:50K state sheets (10K where available). **URLs:** as above.
- **Data type:** polygon shapefile with a class field (`LSZ`/`Class`/`Susceptib`, values very low … very high). Bhusanket also exposes a raster ImageServer (token-protected, not used).
- **Access method:** manual Bhukosh download → `gsi.py convert` → `data/mappings/gsi_landslide_susceptibility.yaml`.
- **Provenance:** `historical` (terrain classification, not an event). `layer_type: landslide_susceptibility`; records become **RiskZone** with severity from `SUSCEPTIBILITY_MAPPING` (very_low→1 low, low→2 low, moderate→3, high→4, very_high→5 critical) and the original class kept in `metadata.original_severity`.
- **Used for:** susceptibility zones crossed / highest class / affected km; separate risk contribution from inventory proximity.
- **Not used as:** an observed event or a live alert. **Wording:** "Landslide Susceptibility · High", "Route crosses high landslide-susceptibility area".

## NRSC flood hazard
- **Organization:** NRSC / ISRO (Bhuvan, NDEM). **Datasets:** Flood Hazard Zonation atlases (integrated 1998-2010 satellite inundation), Flood Annual Layers, Bhuvan flood WMS.
- **URLs:** https://bhuvan-app1.nrsc.gov.in/disaster/disaster.php?id=flood_hz · https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe · https://ndem.nrsc.gov.in/
- **Verified machine access:** the flood WMS (render only). **Data type:** raster/vector rendered as PNG tiles; EPSG:4326; period 1998-2010 (annual) and dated 2011-2013 events.
- **Platform use:** optional Risk Map layers "Historical Flood Inundation · Assam <year>" with NRSC attribution; configuration in `BHUVAN_FLOOD_WMS_URL`, `BHUVAN_FLOOD_LAYERS`; host allowlist prevents arbitrary proxying. A vector Flood Hazard Zonation export, if obtained, imports as **RiskZone** (`layer_type: flood_hazard`, `provenance historical`) via `nrsc_flood_hazard.yaml`.
- **Wording:** "Historical Flood Inundation" / "Historical Flood Hazard" / "Flood-Prone Area". **Never:** "Current Flood Alert". Only a timestamped active source may use "Current Flood/Inundation Observation".
- **Limitations:** WMS imagery is not spatial evidence for PostGIS intersection; flood exposure in the risk engine requires an imported vector layer.

## What is imported today
No authoritative dataset file was obtainable from the build network. The repository ships **synthetic fixtures shaped like the official schemas** (`backend/tests/fixtures/`) for importer/integration tests and **labelled simulated demo seeds** (`backend/data/demo/`). Both are excluded from live mode. The corridor snapshot tool (`python -m app.ingestion.snapshot`) is ready and refuses simulated datasets unless explicitly asked.
