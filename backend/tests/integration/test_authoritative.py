"""Phase-3 PostGIS integration: official-schema fixtures → registry → route intersection/proximity → coverage → confidence → reports."""
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.schemas.contracts import DatasetListContract, HealthContract
from tests.integration.conftest import create_analysis

pytestmark = pytest.mark.asyncio
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

async def import_fixture(client, name, file):
    from app.ingestion.importer import run_import
    return await run_import(str(FIXTURES / f"{name}.fixture.yaml"), str(FIXTURES / file), "skip-existing", False, client.session_factory)

async def test_official_shaped_fixtures_import_with_quality_report(client, owner):
    inv = await import_fixture(client, "gsi_landslide_inventory", "gsi_inventory_sample.csv")
    sus = await import_fixture(client, "gsi_landslide_susceptibility", "gsi_susceptibility_sample.geojson")
    fl = await import_fixture(client, "nrsc_flood_hazard", "nrsc_flood_sample.geojson")
    assert inv["imported"] == 3 and inv["missing_coordinates"] == 1 and inv["missing_fields"] == 1 and inv["provenance"] == "historical" and inv["layer_type"] == "landslide_inventory"
    assert sus["imported"] == 3 and sus["unknown_severity"] == 1 and fl["imported"] == 2
    registry = DatasetListContract.model_validate((await client.get("/api/v1/datasets", headers=owner)).json())
    by_slug = {d.slug: d for d in registry.items}
    assert by_slug["test_gsi_landslide_inventory"].provenance == "historical" and not by_slug["test_gsi_landslide_inventory"].is_live
    raw = (await client.get("/api/v1/datasets", headers=owner)).json()["items"]
    sus_row = next(x for x in raw if x["slug"] == "test_gsi_landslide_susceptibility")
    assert sus_row["layer_type"] == "landslide_susceptibility" and sus_row["attribution"] and sus_row["dataset_period"] == "2020-01 → 2024-12" and sus_row["last_import"]["source_records"] == 4
    from app.models import DatasetSource, HistoricalIncident, RiskZone
    async with client.session_factory() as session:
        inv_id = (await session.scalar(select(DatasetSource.id).where(DatasetSource.slug == "test_gsi_landslide_inventory")))
        rows = list((await session.scalars(select(HistoricalIncident).where(HistoricalIncident.dataset_source_id == inv_id))).all())
        assert len(rows) == 3 and all(r.metadata_json["external_id"].startswith("SYN-GSI") for r in rows)
        assert next(r for r in rows if r.metadata_json["external_id"] == "SYN-GSI-0001").metadata_json["original_severity"] is None
        zones = list((await session.scalars(select(RiskZone).join(DatasetSource).where(DatasetSource.slug == "test_gsi_landslide_susceptibility"))).all())
        assert {z.metadata_json["original_severity"] for z in zones} == {"Very High", "Moderate", "Very Low"} and {z.severity for z in zones} == {5, 3, 1}

async def test_route_analysis_uses_separate_inventory_susceptibility_and_flood_layers(client, owner):
    await import_fixture(client, "gsi_landslide_inventory", "gsi_inventory_sample.csv")
    await import_fixture(client, "gsi_landslide_susceptibility", "gsi_susceptibility_sample.geojson")
    await import_fixture(client, "nrsc_flood_hazard", "nrsc_flood_sample.geojson")
    body = await create_analysis(client, owner)
    routes = {r["name"]: r for r in body["routes"]}
    a = routes["Route A · NH6 Direct"]["hazards"]
    assert a["status"] in {"intersections", "no_intersection"} and a["provenance"] == "historical"
    assert a["landslide"]["inventory_coverage"] == "full" and a["landslide"]["susceptibility_coverage"] == "full" and a["flood"]["dataset_coverage"] == "full"
    crossing = [r for r in body["routes"] if r["hazards"]["landslide"]["susceptibility_zones_crossed"] > 0]
    assert crossing and all(r["hazards"]["landslide"]["highest_susceptibility"] in {"moderate", "high", "critical"} for r in crossing)
    assert any(r["hazards"]["landslide"]["historical_incidents_within_2km"] >= 1 for r in body["routes"])
    best = next(r for r in body["routes"] if r["recommended"])
    cf = best["accessibility"]["confidence_factors"]
    assert cf["landslide_inventory"] == 0.9 and cf["landslide_susceptibility"] == 0.9 and cf["flood_hazard"] == 0.9 and cf["road_condition"] == 0.55
    assert best["accessibility"]["explanations"]["negative"] or best["accessibility"]["explanations"]["positive"]
    sources = {s["key"]: s for s in body["data_sources"]}
    assert sources["landslide_inventory"]["organization"] == "Geological Survey of India" and sources["landslide_inventory"]["status"] == "historical" and sources["flood_hazard"]["organization"] == "NRSC / ISRO"
    assert sources["road_closure"]["status"] == "unavailable" and sources["current_flood"]["status"] == "unavailable"
    assert "Not covered" not in body["explanation"] or "unknown, not zero" in body["explanation"]
    summary = (await client.get(f"/api/v1/analysis/{body['analysis_id']}/spatial-risk-summary", headers=owner)).json()
    assert summary["hazard_status"] in {"intersections", "no_intersection"} and summary["provenance"] == "historical"

async def test_live_mode_excludes_simulated_datasets(client, owner, seeded_hazards, monkeypatch):
    from app.core.config import get_settings
    await import_fixture(client, "gsi_landslide_susceptibility", "gsi_susceptibility_sample.geojson")
    monkeypatch.setattr(get_settings(), "use_mock_data", False)
    zones = (await client.get("/api/v1/risk-zones?min_lat=24&min_lon=90&max_lat=27&max_lon=93", headers=owner)).json()
    assert zones["features"] and all(f["properties"]["provenance"] != "simulated" for f in zones["features"])
    assert seeded_hazards["zone_a"] not in {f["id"] for f in zones["features"]}
    only_sim = (await client.get("/api/v1/risk-zones?min_lat=24&min_lon=90&max_lat=27&max_lon=93&dataset=simulated", headers=owner)).json()
    assert only_sim["features"] == []  # live mode never serves simulated data even when explicitly requested
    monkeypatch.setattr(get_settings(), "use_mock_data", True)
    demo = (await client.get("/api/v1/risk-zones?min_lat=24&min_lon=90&max_lat=27&max_lon=93&dataset=simulated", headers=owner)).json()
    assert seeded_hazards["zone_a"] in {f["id"] for f in demo["features"]}
    by_slug = (await client.get("/api/v1/risk-zones?min_lat=24&min_lon=90&max_lat=27&max_lon=93&dataset=test_gsi_landslide_susceptibility", headers=owner)).json()
    assert by_slug["features"] and all(f["properties"]["layer_type"] == "landslide_susceptibility" and "Susceptibility" in f["properties"]["label"] for f in by_slug["features"])

async def test_readiness_health_map_layers_and_user_reports(client, owner):
    await import_fixture(client, "gsi_landslide_inventory", "gsi_inventory_sample.csv")
    ready = (await client.get("/api/v1/system/readiness")).json()
    assert ready["hazard_intelligence"] == "partial" and "landslide susceptibility dataset" in ready["missing"] and "current road closure provider" in ready["missing"]
    assert ready["hazard_datasets"][0]["layer_type"] == "landslide_inventory"
    health = HealthContract.model_validate((await client.get("/api/v1/system/health")).json())
    raw = (await client.get("/api/v1/system/health")).json()
    assert health.services["postgis"] == "online" and raw["hazard_datasets"]["authoritative"] == 1 and raw["services"]["road closures"] == "unavailable"
    layers = (await client.get("/api/v1/map-layers", headers=owner)).json()
    assert layers["total"] >= 1 and all(l["provenance"] == "historical" and l["url"].startswith("https://bhuvan-ras2.nrsc.gov.in") for l in layers["items"])
    created = await client.post("/api/v1/user-reports", json={"lat": 25.9, "lon": 91.85, "category": "road_issue", "description": "Debris on carriageway"}, headers=owner)
    assert created.status_code == 201 and created.json()["verification_status"] == "unverified" and created.json()["label"] == "Reported Road Issue"
    listed = (await client.get("/api/v1/user-reports?min_lat=25.8&min_lon=91.7&max_lat=26.0&max_lon=92.0", headers=owner)).json()
    assert len(listed["features"]) == 1 and listed["features"][0]["properties"]["verification_status"] == "unverified"
    assert (await client.post("/api/v1/user-reports", json={"lat": 95, "lon": 91}, headers=owner)).status_code == 422

async def test_reports_data_availability_and_snapshot(client, owner, tmp_path):
    await import_fixture(client, "gsi_landslide_susceptibility", "gsi_susceptibility_sample.geojson")
    await create_analysis(client, owner)
    reports = (await client.get("/api/v1/reports/summary?range=7d", headers=owner)).json()
    assert reports["data_availability"] and sum(x["value"] for x in reports["data_availability"]) >= 1
    from app.ingestion.snapshot import build_snapshot
    summary = await build_snapshot(client.session_factory, str(tmp_path / "snap"), buffer_km=15)
    assert summary["snapshot_type"].startswith("historical authoritative") and summary["datasets"][0]["slug"] == "test_gsi_landslide_susceptibility"
    assert summary["datasets"][0]["features_in_snapshot"] >= 2 and summary["datasets"][0]["attribution"] and summary["datasets"][0]["provenance_type"] == "historical"
    assert (tmp_path / "snap" / "snapshot.json").exists() and (tmp_path / "snap" / "test_gsi_landslide_susceptibility.geojson").exists()
