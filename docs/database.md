# Database design

The schema is organized around users, locations, route analyses, analyzed routes, weather snapshots, risk zones, historical incidents, dataset sources, vehicle types, deliveries and user reports. Spatial columns use PostGIS geometry with WGS84 (SRID 4326) and GiST indexes; proximity checks use geography casts on indexed geometries. Analyses retain factor snapshots so historical decisions remain auditable when weights change.

Relationships: `User → RouteAnalysis → AnalyzedRoute → WeatherSnapshot`. A delivery belongs to a user, references its authoritative route analysis and source/destination locations, and keeps a lightweight `status_history` JSON list of transitions. `DatasetSource` records provenance, version, licence, coverage (`coverage_area` text and `coverage_bbox`), record count and the last import report; `RiskZone` and `HistoricalIncident` reference it via `dataset_source_id` and carry a unique `fingerprint` for duplicate detection while keeping the legacy `source` text.

Alembic revisions: `20260907_0001` initial PostGIS schema → `20260907_0002` delivery workflow fields → `20260907_0003` dataset registry, `dataset_source_id`/`fingerprint` columns → `20260907_0004` delivery `status_history`. Upgrade and downgrade were validated against a real PostGIS 3.6 server. Application startup intentionally does not call `create_all()`.
