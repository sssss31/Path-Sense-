# Deployment

Use PostgreSQL 16 with PostGIS, a strong JWT secret and HTTPS. Copy `.env.example`, set provider credentials server-side, then run `alembic upgrade head` before starting API processes. Redis is optional; configure `REDIS_URL` to activate it. Keep `USE_MOCK_DATA=true` for deterministic judging, or `false` for live providers.

Deploy the frontend with only `NEXT_PUBLIC_API_BASE_URL`. Gemini and weather keys belong exclusively in the backend environment. Health checks should target `/api/v1/system/health`.


## Deployment profiles
**DEMO:** `USE_MOCK_DATA=true`, SQLite allowed, deterministic routes/weather/terrain and simulated hazard seeds, no external dependency (OSM tiles optional). **PRODUCTION/LIVE:** `APP_ENV=production`, `USE_MOCK_DATA=false`, PostgreSQL + PostGIS required (startup fails with SQLite unless `SQLITE_IN_PRODUCTION_POLICY=warn`), strong `JWT_SECRET`, `OPENWEATHER_API_KEY`, authoritative datasets imported, simulated datasets excluded automatically, Redis and Gemini optional. External map layers are limited to `EXTERNAL_LAYER_ALLOWED_HOSTS` (`BHUVAN_FLOOD_WMS_URL`, `BHUVAN_FLOOD_LAYERS`). `GET /system/readiness` and `GET /system/health` report database, PostGIS, providers, Redis, hazard datasets (registry summary only) and external layer status.

## Vercel (frontend only)

The repository is a monorepo (backend + frontend). In the Vercel project set **Settings → General → Root Directory = `frontend`** (Framework Preset then shows Next.js; leave Output Directory at its default). `frontend/vercel.json` pins the Next.js framework and build commands; `.vercelignore` keeps the backend out of the upload. Without the root directory Vercel treats the repo as a static site and fails with "No Output Directory named public".

Vercel environment variables: `NEXT_PUBLIC_API_BASE_URL` (public backend URL + `/api/v1`) and optionally `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`. Redeploy after changing them; they are inlined at build time.

The FastAPI backend and PostGIS cannot run on Vercel: host the backend on Render/Railway/Fly/a VM (use `backend/Dockerfile`, which runs migrations) with a managed PostGIS (Neon or Supabase, run `CREATE EXTENSION postgis;` once), and set its `ALLOWED_ORIGINS` to the exact Vercel URL, e.g. `["https://your-app.vercel.app"]`, otherwise the browser reports "Failed to fetch" on login.
