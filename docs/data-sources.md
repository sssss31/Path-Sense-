# Data sources and provenance

Every analysis returns `data_quality` (per provider status) and `data_sources` (one row per source: organization, status, provenance, coverage, period/updated time, attribution). Allowed statuses: `live`, `historical`, `cached`, `estimated`, `simulated`, `partial`, `unavailable`. Provenance types in the dataset registry: `live`, `historical`, `estimated`, `simulated`.

| Source | Mode | Provenance | Notes |
|---|---|---|---|
| Nominatim | live | live | debounced, cached 24 h, custom user agent |
| OSRM | live | live | three alternatives when available |
| OpenWeather | live | live | sampled at five route points; unavailable without key |
| Open-Elevation | live | estimated | slope estimated from sampled elevation |
| GSI landslide inventory / susceptibility | PostGIS | historical | manual acquisition, see [authoritative-data.md](authoritative-data.md) |
| NRSC/ISRO Bhuvan flood WMS | remote layer | historical | rendered only; never a current alert |
| Simulated demo seeds | demo | simulated | excluded from live mode |
| Current flood/landslide events, road closures | — | unavailable | provider interfaces only; user reports shown as unverified issues |

Demo mode uses deterministic simulated routing/weather/terrain and labels them accordingly. Live mode ("LIVE DATA MODE" badge) uses the live providers but individual source badges remain authoritative: historical datasets are never live alerts, and an unavailable feed is reported as unknown, never as "no hazard".

Dataset age is shown from the source period and publication date, not the import time. Attribution strings are stored in the registry and shown on map layers.
