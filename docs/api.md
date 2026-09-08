# API

Base path: `/api/v1`. All routes except `POST /analysis/route`, `POST /assistant/chat` and `GET /system/health` require a bearer token.

## Route analysis
- `POST /analysis/route` accepts source, destination, cargo, vehicle, priority, emergency mode and departure time. With a token the analysis is persisted for the operator (`persistence_status: persisted`). Each route carries `hazards` (`status`: `intersections` | `no_intersection` | `partial_coverage` | `unavailable` | `simulated`) and `accessibility.confidence` with `confidence_reasons`.
- `GET /analysis` paginated owner-scoped summaries (no geometry).
- `GET /analysis/{id}` full stored snapshot; `DELETE /analysis/{id}`.
- `GET /analysis/{id}/map?alternatives=false` lightweight map payload: source, destination, recommended geometry, optional alternatives. Nothing is re-routed.
- `GET /analysis/{id}/spatial-risk-summary` PostGIS summary: `hazard_status`, per-category exposure, landslide/flood exposure km, affected distance, highest severity, incidents within 2 km, coverage ratio, confidence and reasons, plus `intersecting_zone_ids`, `nearby_zone_ids`, `nearby_incident_ids` so the map can state backend-confirmed relationships.

## Deliveries
- `GET /deliveries/transitions` central transition rules (`transitions`, `sensitive`, `priorities`).
- `GET /deliveries` paginated with `status`, `priority`, `cargo_type`, `search`, dates; returns `total`.
- `POST /deliveries` `{analysis_id, vehicle?, priority?, planned_departure?, notes?}` — corridor and cargo always come from the owned analysis. 404 for unknown/foreign analyses, 422 for invalid priority/date.
- `GET /deliveries/{id}` full detail: route summary, accessibility, risk, weather/terrain snapshot, hazards (+ live spatial summary), geometry, status history, `allowed_transitions`, `sensitive_transitions`, data provenance, related analysis.
- `GET /deliveries/{id}/transitions` allowed next statuses for one delivery.
- `PATCH /deliveries/{id}` `{status?, status_note?, planned_departure?, actual_arrival?, notes?}`; invalid transitions return 409, unknown statuses 422. Status changes append to `status_history`.
- `POST /deliveries/{id}/explain` assistant explanation from a server-built, controlled delivery context.
- `DELETE /deliveries/{id}`.

## Workspace endpoints
- `GET /system/weather?lat&lon&name` current weather at a point from the configured provider (OpenWeather live / deterministic demo), 15-minute cache; used by the topbar.
- `GET /notifications` operational alerts derived from persisted records: delayed deliveries, departures due within 6 h, overdue planned departures, high-risk analyses from the last 3 days (rules in `NOTIFICATION_RULES`).
- `GET /system/config` the rule tables the backend actually uses: scoring weights, risk contributions, confidence factors, coverage thresholds, susceptibility mapping, delivery transitions, vehicle profiles, report ranges. The frontend never duplicates these.
- Route results carry `vehicle_assessment`: suitability of every vehicle profile (`VEHICLE_PROFILES`) against slope, road quality, cargo and risk, the recommended vehicle, and the requested vehicle's score with a warning when a better fit exists.

## Map layers, datasets, reports, system
- `GET /risk-zones` and `GET /incidents` require a WGS84 viewport bounding box and return GeoJSON with `provenance`, `dataset` and a claim-safe `label` (e.g. "Historical Landslide Zone"). Live mode excludes simulated datasets. 503 when the spatial database is unavailable.
- `GET /datasets`, `GET /datasets/{id}` dataset registry (provenance, coverage, records, last import report).
- `GET /dashboard/summary` metrics, recent analyses, risk distribution, 14-day accessibility trend, delivery status.
- `GET /reports/summary?range=7d|30d|90d|365d` or `date_from`/`date_to`: risk distribution, cargo distribution, delivery status, daily accessibility trend, top normalized risk factors.
- `GET /system/health` provider status only (routing, geocoding, weather, terrain, Gemini, cache, database, PostGIS). Dataset status is deliberately separate.

Interactive schemas are available from FastAPI at `/docs`. Response contracts used by tests live in `app/schemas/contracts.py`.
