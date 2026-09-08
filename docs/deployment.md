# Deployment

Use PostgreSQL 16 with PostGIS, a strong JWT secret and HTTPS. Copy `.env.example`, set provider credentials server-side, then run `alembic upgrade head` before starting API processes. Redis is optional; configure `REDIS_URL` to activate it. Keep `USE_MOCK_DATA=true` for deterministic judging, or `false` for live providers.

Deploy the frontend with only `NEXT_PUBLIC_API_BASE_URL`. Gemini and weather keys belong exclusively in the backend environment. Health checks should target `/api/v1/system/health`.


## Deployment profiles
**DEMO:** `USE_MOCK_DATA=true`, SQLite allowed, deterministic routes/weather/terrain and simulated hazard seeds, no external dependency (OSM tiles optional). **PRODUCTION/LIVE:** `APP_ENV=production`, `USE_MOCK_DATA=false`, PostgreSQL + PostGIS required (startup fails with SQLite unless `SQLITE_IN_PRODUCTION_POLICY=warn`), strong `JWT_SECRET`, `OPENWEATHER_API_KEY`, authoritative datasets imported, simulated datasets excluded automatically, Redis and Gemini optional. External map layers are limited to `EXTERNAL_LAYER_ALLOWED_HOSTS` (`BHUVAN_FLOOD_WMS_URL`, `BHUVAN_FLOOD_LAYERS`). `GET /system/readiness` and `GET /system/health` report database, PostGIS, providers, Redis, hazard datasets (registry summary only) and external layer status.
