"""Phase-3 unit tests: provenance, normalisation, coverage, confidence v3, flood semantics, proximity, contracts, AI provenance, readiness."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.assistant_service import AssistantService, hazard_state
from app.core.config import get_settings
from app.core.domain import COVERAGE_FULL, COVERAGE_NONE, COVERAGE_PARTIAL, COVERAGE_UNKNOWN, FLOOD_LAYER_WORDING, LAYER_TYPE_LABELS, SUSCEPTIBILITY_MAPPING
from app.ingestion.config import load_config
from app.ingestion.importer import ImportReport, prepare, read_features
from app.ingestion.transformers import TransformError, apply_transforms
from app.main import startup_diagnostics
from app.providers.current_hazards import current_hazard_provider, road_closure_provider
from app.providers.geospatial_layers.base import UntrustedLayerURL, validate_external_url
from app.providers.geospatial_layers.bhuvan_wms import BhuvanFloodWMSProvider
from app.schemas.analysis import Coordinate, DataSource, FloodFeatures, HazardExposure, LandslideFeatures, Terrain, Weather
from app.services.confidence import confidence_v3, factor_confidence
from app.services.coverage import calculate_dataset_route_coverage, combined_coverage
from app.services.datasets import normalize_provenance, serialize_dataset
from app.services.engines import RuleBasedRiskModel, explain
from app.services.hazards import family_of, hazard_sentence
from app.services.sources import dataset_sources_for_route

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ROUTE = [Coordinate(lat=26.1445 - i * .0566, lng=91.7362 + i * .0157) for i in range(11)]  # Guwahati -> Shillong straight line

def ds(**kw):
    base = dict(slug="x", name="X", provenance_type="historical", layer_type="landslide_inventory", data_type="incidents", hazard_category="landslide", coverage_bbox=None, metadata_json={},
                source_organization="Org", attribution=None, period_start=None, period_end=None, ingested_at=None)
    base.update(kw)
    return SimpleNamespace(**base)

def weather(rain=2):
    return Weather(temperature_c=20, rainfall_mm=rain, rainfall_probability=10, humidity=60, wind_kph=5, visibility_km=9, condition="Clear")

# --- provenance & normalisation ------------------------------------------------------------
def test_dataset_provenance_and_layer_rules():
    assert normalize_provenance("historical") == "historical" and normalize_provenance("susceptibility") == "estimated"
    with pytest.raises(ValueError):
        normalize_provenance("live-ish")
    assert family_of(ds(layer_type="landslide_susceptibility", data_type="risk_zones")) == "susceptibility"
    assert family_of(ds(layer_type="flood_inundation", data_type="risk_zones")) == "flood"
    assert family_of(ds(layer_type="landslide_inventory", data_type="incidents")) == "inventory"
    assert family_of(ds(layer_type="hazard_zones", data_type="risk_zones", hazard_category="flood")) == "flood"
    assert LAYER_TYPE_LABELS["landslide_inventory"] != LAYER_TYPE_LABELS["landslide_susceptibility"]

def test_susceptibility_classes_normalise_without_losing_original():
    assert apply_transforms("Very High", ["susceptibility_map"]) == 5 and apply_transforms("very_low", ["susceptibility_map"]) == 1 and apply_transforms("Moderate", ["susceptibility_map"]) == 3
    assert SUSCEPTIBILITY_MAPPING["very_high"] == 5 and SUSCEPTIBILITY_MAPPING["low"] == 2
    with pytest.raises(TransformError):
        apply_transforms("Unclassified", ["susceptibility_map"])
    config = load_config(FIXTURES / "gsi_landslide_susceptibility.fixture.yaml")
    features, _ = read_features(FIXTURES / "gsi_susceptibility_sample.geojson", config)
    report = ImportReport("sus", "skip-existing", True)
    prepared = prepare(features, config, "test", report)
    assert report.valid == 3 and report.invalid == 1 and report.unknown_severity == 1
    assert {p["values"]["severity"] for p in prepared} == {5, 3, 1} and all(p["values"]["original_severity"] for p in prepared)

def test_inventory_never_invents_dates_or_coordinates():
    config = load_config(FIXTURES / "gsi_landslide_inventory.fixture.yaml")
    features, _ = read_features(FIXTURES / "gsi_inventory_sample.csv", config)
    report = ImportReport("inv", "skip-existing", True)
    prepared = prepare(features, config, "test", report)
    assert report.valid == 3 and report.missing_coordinates == 1 and report.missing_fields == 1
    assert all(p["values"]["date"] is not None for p in prepared)
    year_only = next(p for p in prepared if p["values"]["external_id"] == "SYN-GSI-0003")
    assert year_only["values"]["date"].year == 2021
    assert next(p for p in prepared if p["values"]["external_id"] == "SYN-GSI-0001")["values"]["original_severity"] is None
    d = report.to_dict(); assert d["source_records"] == 5 and d["provenance"] == "historical" and d["layer_type"] == "landslide_inventory" and d["coverage"]["bbox"]

# --- coverage ---------------------------------------------------------------------------------
def test_dataset_route_coverage_full_partial_none_unknown():
    assert calculate_dataset_route_coverage(ROUTE, ds(coverage_bbox=[91, 25, 93, 27]))["status"] == COVERAGE_FULL
    partial = calculate_dataset_route_coverage(ROUTE, ds(coverage_bbox=[91, 25.9, 93, 27]))
    assert partial["status"] == COVERAGE_PARTIAL and 0 < partial["coverage_percent"] < 100
    assert calculate_dataset_route_coverage(ROUTE, ds(coverage_bbox=[70, 10, 71, 11]))["status"] == COVERAGE_NONE
    assert calculate_dataset_route_coverage(ROUTE, ds())["status"] == COVERAGE_UNKNOWN
    observed = ds(metadata_json={"last_import": {"coverage_bbox_observed": [91, 25, 93, 27]}})
    assert calculate_dataset_route_coverage(ROUTE, observed)["status"] == COVERAGE_FULL
    assert combined_coverage(ROUTE, [])["status"] == COVERAGE_NONE
    assert combined_coverage(ROUTE, [ds(coverage_bbox=[91, 25, 93, 25.9]), ds(coverage_bbox=[91, 25.9, 93, 27])])["status"] == COVERAGE_FULL

# --- confidence v3 -----------------------------------------------------------------------------
def test_confidence_v3_is_factor_specific_and_coverage_aware():
    live = {"routing": {"provenance": "live", "coverage": COVERAGE_FULL}, "weather": {"provenance": "live", "coverage": COVERAGE_FULL}, "terrain": {"provenance": "estimated", "coverage": COVERAGE_FULL},
            "landslide_inventory": {"provenance": "historical", "coverage": COVERAGE_FULL}, "landslide_susceptibility": {"provenance": "historical", "coverage": COVERAGE_FULL},
            "flood_hazard": {"provenance": "historical", "coverage": COVERAGE_FULL, "period_end": datetime(2010, 12, 31, tzinfo=timezone.utc)}, "road_condition": {"provenance": "unavailable", "coverage": COVERAGE_NONE}}
    overall, factors, reasons = confidence_v3(live)
    assert factors["routing"] == 1.0 and factors["landslide_inventory"] == 0.9 and factors["road_condition"] == 0.0
    assert factors["flood_hazard"] == 0.75  # old (>10y) historical dataset penalised
    partial = confidence_v3({**live, "landslide_susceptibility": {"provenance": "historical", "coverage": COVERAGE_PARTIAL, "reason": "Landslide susceptibility dataset does not cover the full route."}})
    assert partial[0] < overall and "Landslide susceptibility dataset does not cover the full route." in partial[2]
    assert factor_confidence("historical", COVERAGE_NONE) == 0.0 and factor_confidence("simulated", COVERAGE_FULL) == 0.55

def test_low_confidence_never_changes_accessibility_inputs():
    model = RuleBasedRiskModel()
    terrain = Terrain(elevation_m=100, average_slope=2, classification="flat")
    unavailable = model.evaluate(weather(), terrain, 90, HazardExposure(status="unavailable"))
    covered_none = model.evaluate(weather(), terrain, 90, HazardExposure(status="no_intersection", provenance="historical", landslide=LandslideFeatures(inventory_coverage=COVERAGE_FULL, susceptibility_coverage=COVERAGE_FULL), flood=FloodFeatures(dataset_coverage=COVERAGE_FULL)))
    assert unavailable.score == covered_none.score == 8

# --- risk engine v3 & explanations --------------------------------------------------------------
def test_separate_hazard_contributions_and_explanations():
    model = RuleBasedRiskModel()
    terrain = Terrain(elevation_m=100, average_slope=2, classification="flat")
    exposure = HazardExposure(status="intersections", provenance="historical", zones_crossed=3, affected_distance_km=6.4, historical_incidents_nearby=6,
                              landslide=LandslideFeatures(susceptibility_zones_crossed=2, highest_susceptibility="high", susceptibility_affected_km=4.3, historical_incidents_within_2km=6, affected_distance_km=4.3, dataset_coverage=COVERAGE_FULL, inventory_coverage=COVERAGE_FULL, susceptibility_coverage=COVERAGE_FULL),
                              flood=FloodFeatures(historical_zones_crossed=1, affected_distance_km=2.1, highest_hazard="moderate", dataset_coverage=COVERAGE_FULL))
    result = model.evaluate(weather(), terrain, 90, exposure)
    risks = " | ".join(result.main_risks)
    assert "high landslide-susceptibility" in risks and "6 historical landslide incident(s) within 2 km" in risks and "2.1 km historical flood-hazard exposure" in risks
    assert not any(w in risks.lower() for w in ["live", "alert", "current"])
    only_sus = model.evaluate(weather(), terrain, 90, HazardExposure(status="intersections", provenance="historical", landslide=LandslideFeatures(susceptibility_zones_crossed=1, highest_susceptibility="critical", susceptibility_coverage=COVERAGE_FULL)))
    only_inv = model.evaluate(weather(), terrain, 90, HazardExposure(status="intersections", provenance="historical", landslide=LandslideFeatures(historical_incidents_within_2km=4, inventory_coverage=COVERAGE_FULL)))
    assert only_sus.score != only_inv.score and result.score > only_sus.score
    ex = explain(90, weather(28), Terrain(elevation_m=1500, average_slope=14.8, classification="steep"), 92, exposure)
    assert any("Heavy rainfall" in x for x in ex["negative"]) and any("landslide-susceptibility" in x for x in ex["negative"]) and any("flood-hazard exposure" in x for x in ex["negative"])
    assert any("vehicle suitability" in x.lower() for x in ex["positive"])
    unavailable = explain(90, weather(), terrain, 92, HazardExposure(status="unavailable"))
    assert any("unknown, not zero" in x for x in unavailable["negative"]) and not any("No landslide" in x for x in unavailable["positive"])

# --- flood semantics & wording ---------------------------------------------------------------------
def test_historical_flood_semantics_and_labels():
    assert FLOOD_LAYER_WORDING["flood_hazard"] == "Historical Flood Hazard" and FLOOD_LAYER_WORDING["flood_inundation"] == "Historical Flood Inundation"
    assert "Current" not in FLOOD_LAYER_WORDING["flood_hazard"] and "Current" in FLOOD_LAYER_WORDING["current_events"]
    layers = BhuvanFloodWMSProvider().layers()
    assert layers and all(l.provenance == "historical" and l.layer_type == "flood_inundation" and "Historical" in l.name and "NRSC" in l.attribution for l in layers)
    assert layers[0].period == "2010" and "not a current flood alert" in (layers[0].note or "")
    sentence = hazard_sentence(HazardExposure(status="intersections", provenance="historical", flood=FloodFeatures(historical_zones_crossed=1, affected_distance_km=2.1, dataset_coverage=COVERAGE_FULL), landslide=LandslideFeatures(inventory_coverage=COVERAGE_NONE, susceptibility_coverage=COVERAGE_NONE)))
    assert "flood hazard: 1 zone(s)" in sentence and "unknown, not zero" in sentence and "landslide inventory" in sentence

def test_external_layer_urls_are_allowlisted():
    validate_external_url("https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe")
    for bad in ["http://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe", "https://evil.example.com/wms", "https://user:pw@bhuvan-ras2.nrsc.gov.in/x", "https://169.254.169.254/latest"]:
        with pytest.raises(UntrustedLayerURL):
            validate_external_url(bad)

# --- data sources & AI provenance ------------------------------------------------------------------
def test_data_sources_panel_reflects_registry_and_coverage():
    datasets = [ds(slug="inv", name="Inv", layer_type="landslide_inventory", data_type="incidents", coverage_bbox=[91, 25, 93, 27], source_organization="Geological Survey of India", period_end=datetime(2024, 1, 1, tzinfo=timezone.utc)),
                ds(slug="fl", name="Flood", layer_type="flood_hazard", data_type="risk_zones", hazard_category="flood", coverage_bbox=[91, 25.9, 93, 27], source_organization="NRSC / ISRO")]
    sources = {s.key: s for s in dataset_sources_for_route(datasets, ROUTE, None)}
    assert sources["landslide_inventory"].status == "historical" and sources["landslide_inventory"].coverage == COVERAGE_FULL and "Geological Survey" in sources["landslide_inventory"].organization
    assert sources["flood_hazard"].status == "partial" and sources["flood_hazard"].coverage == COVERAGE_PARTIAL
    assert sources["landslide_susceptibility"].status == "unavailable" and "unknown, not zero" in (sources["landslide_susceptibility"].note or "")
    DataSource(**sources["flood_hazard"].model_dump())

def test_assistant_receives_provenance_and_never_infers_safety(monkeypatch):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")  # unit tests never call Gemini
    context = {"analysis_id": "a", "selected_route_id": "r1", "mode": "live", "explanation": "Route A recommended.",
               "data_sources": [{"key": "road_closure", "name": "Road Closure", "organization": "—", "status": "unavailable", "provenance": "unavailable"}],
               "routes": [{"id": "r1", "recommended": True, "hazards": {"status": "unavailable"}, "accessibility": {"score": 80, "explanations": {"negative": [], "positive": []}}}]}
    reply = asyncio.run(AssistantService().answer("Any landslide risk?", context))
    assert reply["source"] == "deterministic-fallback" and "unknown, not zero" in reply["message"]
    assert "not zero" in hazard_state({"status": "unavailable"}) and "not authoritative" in hazard_state({"status": "intersections", "provenance": "simulated"})
    covered = hazard_state({"status": "no_intersection", "provenance": "historical", "landslide": {"inventory_coverage": COVERAGE_FULL}})
    assert "confirm no" in covered

# --- current feeds, readiness, startup -----------------------------------------------------------------
def test_current_feeds_report_unavailable_never_empty_safe():
    flood = asyncio.run(current_hazard_provider().get_active_flood_events())
    closures = asyncio.run(road_closure_provider().get_road_closures())
    assert flood["status"] == "unavailable" and closures["status"] == "unavailable" and "unverified" in closures["reason"]

def test_startup_diagnostics_production_policy():
    prod_sqlite = SimpleNamespace(app_env="production", database_url="sqlite+aiosqlite:///./x.db", use_mock_data=False, jwt_secret="development-only-change-me", openweather_api_key="")
    diag = startup_diagnostics(prod_sqlite)
    assert diag["profile"] == "production" and any("SQLite" in p for p in diag["problems"]) and any("JWT_SECRET" in p for p in diag["problems"])
    demo = SimpleNamespace(app_env="development", database_url="sqlite+aiosqlite:///./x.db", use_mock_data=True, jwt_secret="x", openweather_api_key="")
    assert startup_diagnostics(demo)["problems"] == [] and startup_diagnostics(demo)["profile"] == "demo"
    live = SimpleNamespace(app_env="production", database_url="postgresql+asyncpg://u:p@h/db", use_mock_data=False, jwt_secret="a-long-random-secret", openweather_api_key="k")
    assert startup_diagnostics(live)["problems"] == [] and startup_diagnostics(live)["database"] == "postgresql"

def test_dataset_serialization_exposes_age_metadata():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(id="00000000-0000-0000-0000-000000000000", name="GSI inv", slug="gsi", provider="Bhukosh", source_organization="GSI", hazard_category="landslide", data_type="incidents", dataset_version="2024", record_count=10,
                          published_at=datetime(2024, 3, 1, tzinfo=timezone.utc), downloaded_at=now, ingested_at=now, provenance_type="historical", coverage_area="Meghalaya", coverage_bbox=None, crs="EPSG:4326", status="imported", is_live=False, license="NDSAP",
                          source_url=None, metadata_json={"access_method": "manual"}, created_at=now, updated_at=now, layer_type="landslide_inventory", attribution="© GSI", period_start=datetime(2015, 1, 1, tzinfo=timezone.utc), period_end=datetime(2023, 12, 1, tzinfo=timezone.utc))
    out = serialize_dataset(row)
    assert out["dataset_period"] == "2015-01 → 2023-12" and out["layer_label"] == "Historical Landslide Inventory" and out["access_method"] == "manual"

def test_unreachable_database_reports_unavailable_once_and_never_zero(monkeypatch):
    """A PostgreSQL URL that cannot connect must yield `unavailable` (not zero exposure) with a single probe."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.services.hazards import HazardIntelligenceService
    from app.services.sources import readiness
    engine = create_async_engine("postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere")
    monkeypatch.setattr(get_settings(), "use_mock_data", False)
    async def scenario():
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            service = HazardIntelligenceService(session)
            first = await service.exposure_for_points(ROUTE, 1); second = await service.exposure_for_points(ROUTE, 2)
            ready = await readiness(session)
            return first, second, ready, service._reachable
    first, second, ready, probed = asyncio.run(scenario())
    monkeypatch.setattr(get_settings(), "use_mock_data", True)
    assert first.status == "unavailable" and "unreachable" in first.reasons[0] and second.reasons == first.reasons and probed is False
    assert ready["ready"] is False and ready["database_reachable"] is False and ready["hazard_intelligence"] == "unavailable" and ready["missing"][0].startswith("database unreachable")
