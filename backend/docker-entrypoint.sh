#!/bin/sh
# Container start: migrate, seed demo fixtures once, then serve.
set -e
# Managed databases: make sure PostGIS exists before migrating (no-op when already installed / no permission).
python - <<'PY' || true
import asyncio
from sqlalchemy import text
from app.database.session import engine
async def m():
    async with engine.begin() as c:
        await c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
asyncio.run(m())
PY
alembic upgrade head
python -m app.ingestion.importer --config tests/fixtures/gsi_landslide_inventory.fixture.yaml --file tests/fixtures/gsi_inventory_sample.csv >/dev/null 2>&1 || true
python -m app.ingestion.importer --config tests/fixtures/gsi_landslide_susceptibility.fixture.yaml --file tests/fixtures/gsi_susceptibility_sample.geojson >/dev/null 2>&1 || true
python -m app.ingestion.importer --config tests/fixtures/nrsc_flood_hazard.fixture.yaml --file tests/fixtures/nrsc_flood_sample.geojson >/dev/null 2>&1 || true
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
