#!/bin/sh
# Container start: migrate (PostgreSQL only), seed demo fixtures once, then serve.
# Never dies silently: on migration trouble it prints the reason and still starts the API so
# /api/v1/system/readiness and the logs explain what is wrong.
echo "[entrypoint] DATABASE_URL host: $(echo "${DATABASE_URL:-<unset>}" | sed -E 's#.*@##; s#\?.*##')"
case "${DATABASE_URL:-}" in
  postgres*)
    echo "[entrypoint] ensuring PostGIS extension"
    python - <<'PY' || echo "[entrypoint] WARNING: could not create the postgis extension (run CREATE EXTENSION postgis; manually if migrations fail)"
import asyncio
from sqlalchemy import text
from app.database.session import engine
async def m():
    async with engine.begin() as c:
        await c.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
asyncio.run(m())
PY
    echo "[entrypoint] running migrations"
    if alembic upgrade head; then
      for f in gsi_landslide_inventory:gsi_inventory_sample.csv gsi_landslide_susceptibility:gsi_susceptibility_sample.geojson nrsc_flood_hazard:nrsc_flood_sample.geojson; do
        USE_MOCK_DATA=true python -m app.ingestion.importer --config "tests/fixtures/${f%%:*}.fixture.yaml" --file "tests/fixtures/${f##*:}" >/dev/null 2>&1 || true
      done
      echo "[entrypoint] migrations + demo fixtures done"
    else
      echo "[entrypoint] ERROR: migrations failed; check DATABASE_URL and PostGIS. Starting the API anyway so readiness reports the problem."
    fi
    ;;
  "")
    echo "[entrypoint] ERROR: DATABASE_URL is not set. Set it to your PostgreSQL/PostGIS URL (Render: Internal Database URL)."
    ;;
  *)
    echo "[entrypoint] non-PostgreSQL DATABASE_URL: skipping migrations (SQLite tables are created on startup in non-production)"
    ;;
esac
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
