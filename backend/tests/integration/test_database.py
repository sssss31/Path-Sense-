"""PostGIS integration tests (require TEST_DATABASE_URL)."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.schemas.contracts import AnalysisMapContract, DatasetListContract, HealthContract, HistoryContract, ReportsSummaryContract, SpatialRiskSummaryContract
from app.schemas.delivery import DeliveryDetailResponse, DeliveryResponse
from tests.integration.conftest import ANALYSIS_PAYLOAD, HAZARD_A, HAZARD_B, INCIDENT_A, INCIDENT_B, ROUTE_WKT, create_analysis

pytestmark = pytest.mark.asyncio
DATA = Path(__file__).resolve().parents[2] / "data"

# --- migrations & schema ---------------------------------------------------------
async def test_migrations_created_expected_tables_and_spatial_indexes(client):
    async with client.session_factory() as session:
        tables = {r[0] for r in (await session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))).all()}
        assert {"users", "locations", "route_analyses", "analyzed_routes", "risk_zones", "historical_incidents", "dataset_sources", "deliveries", "weather_snapshots"} <= tables
        version = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        assert version == "20260907_0005"
        gist = {r[0] for r in (await session.execute(text("SELECT indexname FROM pg_indexes WHERE indexdef ILIKE '%USING gist%'"))).all()}
        assert {"ix_risk_zones_geometry_gist", "ix_analyzed_routes_geometry_gist", "ix_historical_incidents_geometry_gist"} <= gist
        columns = {r[0] for r in (await session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='deliveries'"))).all()}
        assert "status_history" in columns
        assert "coverage_bbox" in {r[0] for r in (await session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='dataset_sources'"))).all()}

# --- analysis persistence -----------------------------------------------------------
async def test_analysis_persists_locations_routes_geometry_and_weather(client, owner):
    from app.models import AnalyzedRoute, Location, RouteAnalysis, WeatherSnapshot
    body = await create_analysis(client, owner)
    async with client.session_factory() as session:
        analysis = await session.get(RouteAnalysis, uuid.UUID(body["analysis_id"]))
        assert analysis is not None and analysis.cargo_type == "medicine" and analysis.status == "completed"
        assert (await session.scalar(select(func.count(Location.id)))) == 2
        routes = list((await session.scalars(select(AnalyzedRoute).where(AnalyzedRoute.analysis_id == analysis.id))).all())
        assert len(routes) == 3 and sum(r.is_recommended for r in routes) == 1
        length_km = await session.scalar(select(func.ST_Length(func.Geography(AnalyzedRoute.geometry)) / 1000).where(AnalyzedRoute.id == routes[0].id))
        assert 60 < length_km < 120
        assert analysis.recommended_route_id in {r.id for r in routes}
        snapshots = await session.scalar(select(func.count(WeatherSnapshot.id)))
        assert snapshots == 3
        assert body["routes"][0]["hazards"]["status"] in {"simulated", "unavailable", "no_intersection", "intersections", "partial_coverage"}

# --- ownership -----------------------------------------------------------------------------
async def test_history_is_owner_scoped_and_cross_user_denied(client, owner, stranger):
    body = await create_analysis(client, owner)
    history = await client.get("/api/v1/analysis", headers=owner)
    HistoryContract.model_validate(history.json())
    assert history.json()["total"] == 1
    assert (await client.get("/api/v1/analysis", headers=stranger)).json()["total"] == 0
    assert (await client.get(f"/api/v1/analysis/{body['analysis_id']}", headers=stranger)).status_code == 404
    assert (await client.get(f"/api/v1/analysis/{body['analysis_id']}/map", headers=stranger)).status_code == 404
    assert (await client.delete(f"/api/v1/analysis/{body['analysis_id']}", headers=stranger)).status_code == 404
    assert (await client.delete(f"/api/v1/analysis/{body['analysis_id']}", headers=owner)).status_code == 204
    assert (await client.get(f"/api/v1/analysis/{body['analysis_id']}", headers=owner)).status_code == 404

async def test_analysis_map_endpoint_is_lightweight(client, owner):
    body = await create_analysis(client, owner)
    response = await client.get(f"/api/v1/analysis/{body['analysis_id']}/map", headers=owner)
    payload = AnalysisMapContract.model_validate(response.json())
    assert payload.recommended_route["recommended"] is True and len(payload.recommended_route["geometry"]) >= 2 and payload.alternatives == []
    with_alternatives = await client.get(f"/api/v1/analysis/{body['analysis_id']}/map?alternatives=true", headers=owner)
    assert len(with_alternatives.json()["alternatives"]) == 2
    history_item = (await client.get("/api/v1/analysis", headers=owner)).json()["items"][0]
    assert "geometry" not in history_item

# --- deliveries ------------------------------------------------------------------------------
async def test_delivery_crud_transitions_and_error_cases(client, owner, stranger):
    body = await create_analysis(client, owner)
    departure = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    created = await client.post("/api/v1/deliveries", json={"analysis_id": body["analysis_id"], "vehicle": "4x4 Utility Vehicle", "priority": "critical", "planned_departure": departure, "notes": "Cold chain"}, headers=owner)
    assert created.status_code == 201, created.text
    delivery = DeliveryResponse.model_validate(created.json())
    assert delivery.vehicle == "4x4 Utility Vehicle" and delivery.priority == "critical" and delivery.status == "planned" and delivery.allowed_transitions == ["in_transit", "cancelled"]
    assert delivery.estimated_arrival is not None and delivery.estimated_arrival > delivery.planned_departure
    # error cases
    assert (await client.post("/api/v1/deliveries", json={"analysis_id": str(uuid.uuid4())}, headers=owner)).status_code == 404
    assert (await client.post("/api/v1/deliveries", json={"analysis_id": body["analysis_id"]}, headers=stranger)).status_code == 404
    assert (await client.post("/api/v1/deliveries", json={"analysis_id": body["analysis_id"], "priority": "asap"}, headers=owner)).status_code == 422
    assert (await client.post("/api/v1/deliveries", json={"analysis_id": body["analysis_id"], "planned_departure": "not-a-date"}, headers=owner)).status_code == 422
    assert (await client.get(f"/api/v1/deliveries/{delivery.id}", headers=stranger)).status_code == 404
    assert (await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "in_transit"}, headers=stranger)).status_code == 404
    assert (await client.delete(f"/api/v1/deliveries/{delivery.id}", headers=stranger)).status_code == 404
    assert (await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "teleported"}, headers=owner)).status_code == 422
    assert (await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "completed"}, headers=owner)).status_code == 409
    # detail
    detail = DeliveryDetailResponse.model_validate((await client.get(f"/api/v1/deliveries/{delivery.id}", headers=owner)).json())
    assert detail.route["name"] and len(detail.geometry) >= 2 and detail.hazards is not None and detail.analysis["analysis_id"] == body["analysis_id"]
    assert detail.hazards["summary"]["hazard_status"] in {"unavailable", "no_intersection", "intersections", "partial_coverage", "simulated"}
    transitions = (await client.get(f"/api/v1/deliveries/{delivery.id}/transitions", headers=owner)).json()
    assert transitions["allowed_transitions"] == ["in_transit", "cancelled"]
    # valid transitions with notes
    updated = await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "in_transit", "status_note": "Departed depot"}, headers=owner)
    assert updated.status_code == 200 and updated.json()["status"] == "in_transit" and updated.json()["status_history"][-1]["note"] == "Departed depot"
    delayed = await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "delayed"}, headers=owner)
    assert delayed.json()["allowed_transitions"] == ["in_transit", "completed", "cancelled"]
    completed = await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "completed", "status_note": "Signed"}, headers=owner)
    assert completed.json()["status"] == "completed" and completed.json()["actual_arrival"] and completed.json()["allowed_transitions"] == []
    assert (await client.patch(f"/api/v1/deliveries/{delivery.id}", json={"status": "cancelled"}, headers=owner)).status_code == 409
    listing = (await client.get("/api/v1/deliveries?status=completed", headers=owner)).json()
    assert listing["total"] == 1 and listing["items"][0]["identifier"] == delivery.identifier
    explain = await client.post(f"/api/v1/deliveries/{delivery.id}/explain", json={"message": "Explain"}, headers=owner)
    assert explain.status_code == 200 and delivery.identifier in explain.json()["message"]
    assert (await client.delete(f"/api/v1/deliveries/{delivery.id}", headers=owner)).status_code == 204
    assert (await client.get(f"/api/v1/deliveries/{delivery.id}", headers=owner)).status_code == 404

# --- spatial ---------------------------------------------------------------------------------
async def test_postgis_geometry_relationships(client, seeded_hazards):
    from app.models import HistoricalIncident, RiskZone
    async with client.session_factory() as session:
        route = func.ST_GeomFromText(ROUTE_WKT, 4326)
        intersecting = [str(x) for x in (await session.scalars(select(RiskZone.id).where(func.ST_Intersects(RiskZone.geometry, route)))).all()]
        assert intersecting == [seeded_hazards["zone_a"]]
        within = [str(x) for x in (await session.scalars(select(HistoricalIncident.id).where(func.ST_DWithin(func.Geography(HistoricalIncident.geometry), func.Geography(route), 2000)))).all()]
        assert within == [seeded_hazards["incident_a"]]
        affected = await session.scalar(select(func.ST_Length(func.Geography(func.ST_Intersection(route, RiskZone.geometry))) / 1000).where(RiskZone.id == uuid.UUID(seeded_hazards["zone_a"])))
        assert 5 < affected < 20
        rows = (await session.execute(select(RiskZone.category, func.count(RiskZone.id), func.max(RiskZone.severity)).where(func.ST_Intersects(RiskZone.geometry, route)).group_by(RiskZone.category))).all()
        assert rows == [("landslide", 1, 4)]

async def test_spatial_risk_summary_uses_backend_relationships(client, owner, seeded_hazards):
    body = await create_analysis(client, owner)
    response = await client.get(f"/api/v1/analysis/{body['analysis_id']}/spatial-risk-summary", headers=owner)
    summary = SpatialRiskSummaryContract.model_validate(response.json())
    assert summary.hazard_status in {"intersections", "no_intersection", "partial_coverage"}
    assert summary.datasets == ["Integration Simulated Zones"] and summary.provenance == "simulated"
    assert seeded_hazards["zone_b"] not in summary.intersecting_zone_ids and seeded_hazards["incident_b"] not in summary.nearby_incident_ids
    if summary.hazard_status == "intersections":
        assert summary.zones_crossed >= 1 and summary.highest_severity in {"high", "critical", "moderate", "low"}
    assert (await client.get(f"/api/v1/analysis/{uuid.uuid4()}/spatial-risk-summary", headers=owner)).status_code == 404

async def test_route_analysis_consumes_hazard_metrics_with_coverage_semantics(client, owner, seeded_hazards):
    body = await create_analysis(client, owner)
    statuses = {r["hazards"]["status"] for r in body["routes"]}
    assert statuses <= {"intersections", "no_intersection", "partial_coverage"}
    assert body["data_quality"]["landslide"]["status"] in {"simulated", "historical", "partial"}
    assert all(0 <= r["accessibility"]["confidence"] <= 1 for r in body["routes"])

async def test_viewport_queries_and_empty_results(client, owner, seeded_hazards):
    zones = (await client.get("/api/v1/risk-zones?min_lat=25.8&min_lon=91.7&max_lat=26.0&max_lon=92.0", headers=owner)).json()
    assert [f["id"] for f in zones["features"]] == [seeded_hazards["zone_a"]] and zones["features"][0]["properties"]["provenance"] == "simulated" and "demo" in zones["features"][0]["properties"]["label"]
    incidents = (await client.get("/api/v1/incidents?min_lat=25.8&min_lon=91.7&max_lat=26.0&max_lon=92.0", headers=owner)).json()
    assert [f["id"] for f in incidents["features"]] == [seeded_hazards["incident_a"]]
    empty = (await client.get("/api/v1/risk-zones?min_lat=10&min_lon=70&max_lat=11&max_lon=71", headers=owner)).json()
    assert empty["features"] == []
    assert (await client.get("/api/v1/risk-zones?min_lat=25&min_lon=91&max_lat=26", headers=owner)).status_code == 422

# --- dataset import ---------------------------------------------------------------------------
async def test_dataset_import_duplicates_and_registry(client, owner):
    from app.ingestion.importer import run_import
    first = await run_import(str(DATA / "mappings" / "demo_hazard_zones.yaml"), str(DATA / "demo" / "demo_hazard_zones.geojson"), "skip-existing", False, client.session_factory)
    assert first["imported"] == 4 and first["duplicates"] == 0 and first["record_count"] == 4
    again = await run_import(str(DATA / "mappings" / "demo_hazard_zones.yaml"), str(DATA / "demo" / "demo_hazard_zones.geojson"), "skip-existing", False, client.session_factory)
    assert again["imported"] == 0 and again["duplicates"] == 4 and again["skipped"] == 4 and again["record_count"] == 4
    updated = await run_import(str(DATA / "mappings" / "demo_hazard_zones.yaml"), str(DATA / "demo" / "demo_hazard_zones.geojson"), "update-existing", False, client.session_factory)
    assert updated["updated"] == 4 and updated["record_count"] == 4
    with pytest.raises(RuntimeError):
        await run_import(str(DATA / "mappings" / "demo_hazard_zones.yaml"), str(DATA / "demo" / "demo_hazard_zones.geojson"), "fail-on-duplicate", False, client.session_factory)
    incidents = await run_import(str(DATA / "mappings" / "demo_incidents.yaml"), str(DATA / "demo" / "demo_incidents.csv"), "skip-existing", False, client.session_factory)
    assert incidents["imported"] == 4
    registry = DatasetListContract.model_validate((await client.get("/api/v1/datasets", headers=owner)).json())
    assert registry.total == 2 and all(d.provenance == "simulated" and not d.is_live and d.status == "imported" for d in registry.items)
    zones = next(d for d in registry.items if d.data_type == "risk_zones")
    assert zones.records == 4 and zones.last_import["duplicates"] == 4 and zones.coverage_bbox == [91.3, 25.4, 92.2, 26.3]
    assert (await client.get(f"/api/v1/datasets/{zones.id}", headers=owner)).json()["slug"] == "demo-simulated-hazard-zones"
    dry = await run_import(str(DATA / "mappings" / "demo_hazard_zones.yaml"), str(DATA / "demo" / "demo_hazard_zones.geojson"), "skip-existing", True, client.session_factory)
    assert dry["duplicates"] == 4 and dry["database_duplicate_check"] is True and dry["would_write"] is False

# --- aggregation -----------------------------------------------------------------------------
async def test_dashboard_and_reports_aggregation(client, owner):
    body = await create_analysis(client, owner)
    await create_analysis(client, owner)
    await client.post("/api/v1/deliveries", json={"analysis_id": body["analysis_id"]}, headers=owner)
    dashboard = (await client.get("/api/v1/dashboard/summary", headers=owner)).json()
    assert dashboard["metrics"]["total_analyses"] == 2 and dashboard["metrics"]["active_deliveries"] == 1 and dashboard["metrics"]["last_7_days"] == 2
    assert sum(x["count"] for x in dashboard["risk_distribution"]) == 2 and dashboard["accessibility_trend"][0]["analyses"] == 2 and dashboard["delivery_status"] == [{"name": "planned", "value": 1}]
    reports = ReportsSummaryContract.model_validate((await client.get("/api/v1/reports/summary?range=7d", headers=owner)).json())
    assert reports.range["key"] == "7d" and sum(x.value for x in reports.risk_distribution) == 2 and reports.cargo_distribution == [{"name": "medicine", "value": 2}] or reports.cargo_distribution[0].value == 2
    assert reports.accessibility_trend and reports.accessibility_trend[0].analyses == 2
    assert isinstance(reports.risk_factors, list) and all(f.value >= 1 for f in reports.risk_factors)  # demo recommended route may carry no risk factors
    old = (await client.get("/api/v1/reports/summary?date_from=2000-01-01T00:00:00Z&date_to=2000-01-02T00:00:00Z", headers=owner)).json()
    assert old["accessibility_trend"] == [] and old["range"]["key"] == "custom"

async def test_health_reports_postgis_and_provider_status(client):
    health = HealthContract.model_validate((await client.get("/api/v1/system/health")).json())
    assert health.services["postgis"] == "online" and health.services["database"] == "online"
