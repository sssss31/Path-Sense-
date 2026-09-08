# Hackathon readiness checklist

Run `cd backend && python scripts/validate_demo_corridor.py` and `python scripts/live_smoke.py` before judging.

- [ ] PostGIS running (Docker `docker-compose.test.yml`, or local Postgres 17 + PostGIS on 55432 as in docs/testing.md); `GET /system/health` shows database + PostGIS `online`
- [ ] Migrations applied: `alembic upgrade head` → `20260907_0005`
- [ ] Demo user exists (`DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD`) and login works
- [ ] Authoritative snapshot imported (GSI inventory + susceptibility, NRSC flood vector) — or, if not yet obtained, demo seeds imported and the UI shows **Simulated** badges; `GET /system/readiness` → `hazard_intelligence`
- [ ] OSRM available (`live_smoke.py` → osrm healthy)
- [ ] Nominatim available (user agent + cache in place)
- [ ] OpenWeather key valid (`live_smoke.py` → openweather healthy); demo mode otherwise
- [ ] Gemini key optional (`scripts/gemini_smoke.py` → live or unconfigured, fallback ok)
- [ ] Bhuvan flood WMS reachable (Risk Map → Official remote layers); local layers still work if it is not
- [ ] Risk Map works: viewport layers, dataset source filter, saved-route overlay, spatial risk panel
- [ ] Route analysis works and shows Data Sources panel + factor explanations
- [ ] Create Delivery → delivery detail → Update Status works
- [ ] Reports show charts incl. Data Availability
- [ ] Demo scenario validated: `validate_demo_corridor.py` prints Route B recommended, confidence and coverage
- [ ] Demo fallback validated: `USE_MOCK_DATA=true` with SQLite still analyses (hazards simulated, clearly labelled)
- [ ] Live mode validated: `USE_MOCK_DATA=false` + PostGIS shows "LIVE DATA MODE" with per-source badges; simulated datasets excluded
