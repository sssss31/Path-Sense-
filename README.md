# PathSense — AI Smart Logistics & Accessibility Intelligence

PathSense answers a harder question than navigation software: **can a destination be reached safely and reliably?** It compares routes using weather, terrain, historical risk, road quality, current disruption and vehicle suitability, then explains the recommendation through Gemini.

## What works in the MVP

- Responsive logistics command center and route-analysis workspace
- Three comparable routes with map geometry and synchronized selection
- Config-driven accessibility scoring, rule-based risk, ranking and vehicle recommendation
- FastAPI versioned API with isolated provider adapters and graceful fallbacks
- Gemini-ready assistant endpoint; deterministic explanation fallback without a key
- PostgreSQL/PostGIS-ready models, optional Redis-ready architecture and mock development mode
- Unit tests for scoring, risk, route ranking and vehicle selection

## Run locally

**One command, any OS** (needs only Python 3.12 and Node.js): `run.bat` on Windows, `./run.sh` on macOS/Linux. It creates the virtualenv, installs dependencies, picks a database (your PostGIS if reachable → Docker PostGIS if Docker is running → SQLite demo mode otherwise), applies migrations or creates tables, seeds the demo operator (`demo@smartlogistics.local` / `Demo123!`), writes `frontend/.env.local`, starts both servers on free ports and opens the browser. `python scripts/bootstrap.py --check` shows what it would use. SQLite demo mode runs everything except PostGIS hazard layers, which are reported as unavailable (never as zero risk).

**Full stack in Docker**: `docker compose up --build` (migrations and demo fixtures run automatically), then open http://localhost:3000.

### Manual setup

Copy `.env.example` to `.env`, then run `docker compose up --build`. Open `http://localhost:3000`; API docs are at `http://localhost:8000/docs`.

Without Docker:

```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

Mock mode is on by default so the Guwahati → Shillong demo works without provider keys. Set `USE_MOCK_DATA=false` for Nominatim/OSRM. Add `GEMINI_API_KEY` to enable Gemini explanations. Never expose secrets through `NEXT_PUBLIC_*` variables.

Live mode now includes Nominatim, OSRM, route-sampled OpenWeather and estimated Open Elevation adapters. The persistence foundation includes async SQLAlchemy, PostGIS geometries/spatial indexes, Alembic, JWT authentication and optional Redis. See [data-source provenance](docs/data-sources.md) and [deployment guidance](docs/deployment.md).

The route analysis workspace is fully backend-driven: it loads the operator's latest saved analysis (or runs one), renders real route geometry and PostGIS hazard layers on Leaflet, shows live weather and record-derived notifications in the topbar, assesses the requested vehicle against terrain/road/cargo, and offers a grounded Gemini follow-up chat (deterministic fallback when unavailable). Operational pages now include authenticated Dashboard, History, Risk Map, Deliveries, Reports and Settings. A successful, saved route analysis offers **Create Delivery**; each delivery has a detail page with status controls driven by backend transition rules, a saved-route map and hazard exposure. The Risk Map overlays saved routes with a PostGIS spatial-risk panel, Reports use aggregation APIs with reusable charts, and Settings shows Provider Status separately from the Dataset Registry. Hazard datasets are imported through a mapping-config importer with fingerprint duplicate detection (see [docs/data-ingestion.md](docs/data-ingestion.md)); **no authoritative hazard dataset ships with the repository**, only labelled simulated demo seeds. Phase 3 adds a verified [authoritative data guide](docs/authoritative-data.md) (GSI Bhukosh/Bhusanket landslide inventory & susceptibility — manual download; NRSC/ISRO Bhuvan flood WMS — rendered as an official remote layer), separate inventory/susceptibility/flood hazard features, factor-level confidence, a per-analysis Data Sources panel, dataset source filtering on the Risk Map, readiness diagnostics and a [hackathon checklist](docs/hackathon-checklist.md).

## Architecture

`Next.js → FastAPI → provider adapters → risk/accessibility/decision engines → structured result → Gemini explanation`

Business logic lives in backend services, provider calls behind adapters, API access in the frontend client, and UI state in a small Zustand store. See [docs/architecture.md](docs/architecture.md), [docs/scoring.md](docs/scoring.md), [docs/api.md](docs/api.md), [docs/database.md](docs/database.md), and [docs/demo.md](docs/demo.md).

## Quality checks

```bash
cd backend && pytest --ignore=tests/integration
TEST_DATABASE_URL=postgresql+asyncpg://pathsense_test:pathsense_test@localhost:55432/pathsense_test pytest tests/integration
cd frontend && npm run lint && npm run build
```

See [docs/testing.md](docs/testing.md) for the PostGIS integration environment.
