"""PostGIS integration fixtures.

Skips cleanly unless TEST_DATABASE_URL is set. Refuses to run against anything
that looks like a development/production database. Applies Alembic migrations
to head, seeds deterministic geometry, and exposes an authenticated API client.
"""
import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_URL = os.environ.get("TEST_DATABASE_URL", "")
BACKEND = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration

def _guard():
    if not TEST_URL:
        pytest.skip("TEST_DATABASE_URL not set; PostGIS integration tests skipped", allow_module_level=True)
    if not TEST_URL.startswith("postgresql+asyncpg://"):
        pytest.skip("TEST_DATABASE_URL must be an asyncpg PostgreSQL URL", allow_module_level=True)
    dev = os.environ.get("DATABASE_URL", "")
    if dev and dev == TEST_URL:
        raise RuntimeError("Refusing to run integration tests against DATABASE_URL")
    if "test" not in TEST_URL.rsplit("/", 1)[-1].lower():
        raise RuntimeError("Refusing to run integration tests against a database whose name does not contain 'test'")

_guard()

@pytest.fixture(scope="session")
def migrated_database():
    """Run `alembic upgrade head` against the test database once per session."""
    env = {**os.environ, "DATABASE_URL": TEST_URL}
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    yield TEST_URL

@pytest.fixture(scope="session")
def engine(migrated_database):
    engine = create_async_engine(migrated_database, poolclass=__import__("sqlalchemy.pool", fromlist=["NullPool"]).NullPool)
    yield engine
    asyncio.run(engine.dispose())

@pytest.fixture(scope="session")
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

@pytest_asyncio.fixture
async def clean_db(session_factory):
    """Truncate every application table before each test for deterministic state."""
    async with session_factory() as session:
        await session.execute(text("TRUNCATE deliveries, weather_snapshots, analyzed_routes, route_analyses, locations, risk_zones, historical_incidents, dataset_sources, user_reports, users RESTART IDENTITY CASCADE"))
        await session.commit()
    yield

@pytest_asyncio.fixture
async def client(session_factory, clean_db, monkeypatch):
    from app.core.config import get_settings
    from app.database.session import get_session
    from app.main import app
    settings = get_settings()
    monkeypatch.setattr(settings, "use_mock_data", True)
    async def override():
        async with session_factory() as session:
            yield session
    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.session_factory = session_factory
        yield client
    app.dependency_overrides.clear()

async def register(client, email):
    response = await client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!"})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

@pytest_asyncio.fixture
async def owner(client):
    return await register(client, f"owner-{uuid.uuid4().hex[:6]}@example.com")

@pytest_asyncio.fixture
async def stranger(client):
    return await register(client, f"stranger-{uuid.uuid4().hex[:6]}@example.com")

# Deterministic geometry: the mock corridor runs Guwahati (26.1445, 91.7362) -> Shillong (25.5788, 91.8933).
ROUTE_WKT = "LINESTRING(91.7362 26.1445, 91.78 26.0, 91.82 25.9, 91.86 25.8, 91.88 25.7, 91.8933 25.5788)"
HAZARD_A = "MULTIPOLYGON(((91.80 25.85, 91.90 25.85, 91.90 25.95, 91.80 25.95, 91.80 25.85)))"   # intersects route
HAZARD_B = "MULTIPOLYGON(((91.30 25.40, 91.40 25.40, 91.40 25.50, 91.30 25.50, 91.30 25.40)))"   # far away
INCIDENT_A = "POINT(91.815 25.905)"   # ~0.3 km from route
INCIDENT_B = "POINT(91.35 25.45)"     # far away

@pytest_asyncio.fixture
async def seeded_hazards(session_factory):
    """Register a simulated dataset and seed hazard A/B and incident A/B with known relationships."""
    from app.models import DatasetSource, HistoricalIncident, RiskZone
    from sqlalchemy import func
    async with session_factory() as session:
        dataset = DatasetSource(name="Integration Simulated Zones", slug="integration-sim", provider="test", hazard_category="landslide", data_type="risk_zones", source_organization="test",
                                dataset_version="1", crs="EPSG:4326", coverage_area="corridor", coverage_bbox=[91.2, 25.3, 92.2, 26.3], status="imported", is_live=False, provenance_type="simulated", metadata_json={}, record_count=2)
        session.add(dataset); await session.flush()
        a = RiskZone(dataset_source_id=dataset.id, fingerprint="fp-a", category="landslide", severity=4, status="historical", source="test", geometry=func.ST_GeomFromText(HAZARD_A, 4326), metadata_json={})
        b = RiskZone(dataset_source_id=dataset.id, fingerprint="fp-b", category="flood", severity=2, status="historical", source="test", geometry=func.ST_GeomFromText(HAZARD_B, 4326), metadata_json={})
        ia = HistoricalIncident(dataset_source_id=dataset.id, fingerprint="fp-ia", category="landslide", severity=3, occurred_at=datetime(2023, 7, 1, tzinfo=timezone.utc), geometry=func.ST_GeomFromText(INCIDENT_A, 4326), source="test", description="near", metadata_json={})
        ib = HistoricalIncident(dataset_source_id=dataset.id, fingerprint="fp-ib", category="landslide", severity=1, occurred_at=datetime(2022, 7, 1, tzinfo=timezone.utc), geometry=func.ST_GeomFromText(INCIDENT_B, 4326), source="test", description="far", metadata_json={})
        session.add_all([a, b, ia, ib]); await session.commit()
        return {"dataset_id": str(dataset.id), "zone_a": str(a.id), "zone_b": str(b.id), "incident_a": str(ia.id), "incident_b": str(ib.id)}

ANALYSIS_PAYLOAD = {"source": {"name": "Guwahati"}, "destination": {"name": "Shillong"}, "cargo_type": "medicine", "vehicle_type": "cargo_van", "priority": "high", "emergency_mode": False, "departure_time": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()}

async def create_analysis(client, headers):
    response = await client.post("/api/v1/analysis/route", json=ANALYSIS_PAYLOAD, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["persistence_status"] == "persisted", body.get("persistence_status")
    return body
