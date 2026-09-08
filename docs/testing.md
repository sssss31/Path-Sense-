# Testing

Unit and contract tests have no network or database dependency:

```bash
cd backend && pytest --ignore=tests/integration
```

They cover scoring, risk, confidence/coverage semantics, delivery transition rules, importer transformers, mapping, fingerprints, geometry/CRS validation, dry-run reporting and response contracts (`app/schemas/contracts.py`).

## PostGIS integration tests
Start the isolated PostGIS service (Docker) or any PostgreSQL 16/17 server with PostGIS and a dedicated database whose name contains `test`:

```bash
docker compose -f docker-compose.test.yml up -d
export TEST_DATABASE_URL=postgresql+asyncpg://pathsense_test:pathsense_test@localhost:55432/pathsense_test
cd backend && pytest tests/integration
```

The fixtures apply `alembic upgrade head`, truncate tables per test, seed deterministic geometry (a corridor LINESTRING, hazard A intersecting it, hazard B far away, incident A within 2 km, incident B outside) and exercise: migration/table/index inspection, analysis/location/route geometry/weather persistence, owner-scoped history and cross-user denial, delivery CRUD/transitions/error cases, `ST_Intersects`/`ST_DWithin`/`ST_Intersection` affected distance, category totals and highest severity, spatial-risk summary relationships, route analysis hazard consumption, viewport queries including empty results, dataset import with duplicate modes and registry updates, dashboard/reports aggregation and health.

Tests skip when `TEST_DATABASE_URL` is absent and refuse to run when it equals `DATABASE_URL`. Migrations can also be checked offline: `DATABASE_URL=postgresql+asyncpg://x:x@localhost/x alembic upgrade head --sql`.

Without Docker on macOS, `brew install postgresql@17 postgis`, `initdb` a scratch directory, start it on port 55432 with `LC_ALL=C`, `CREATE EXTENSION postgis`, and use the URL above.

Phase-3 integration tests import synthetic fixtures shaped like the official GSI/NRSC schemas (`tests/fixtures/`) and verify registry metadata, inventory vs susceptibility layers, route intersection/proximity, coverage, confidence factors, live-mode exclusion of simulated data, readiness/health, user reports, reports data availability and the corridor snapshot. Real datasets stay outside the test suite.

Diagnostics: `python scripts/validate_demo_corridor.py`, `python scripts/live_smoke.py` (network), `python scripts/gemini_smoke.py`.

Frontend: `npm run lint && npm run build` (TypeScript is checked during the build; `npx tsc --noEmit` also works).
