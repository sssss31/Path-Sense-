"""Schema-level contract tests that do not need a database."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.domain import DELIVERY_PRIORITIES, DELIVERY_STATUSES, DELIVERY_TRANSITIONS, SENSITIVE_DELIVERY_STATUSES
from app.schemas.contracts import DatasetContract, ReportsSummaryContract, SpatialRiskSummaryContract
from app.schemas.delivery import DeliveryDetailResponse, DeliveryResponse, TransitionRules
from app.services.datasets import normalize_provenance, serialize_dataset, validate_bbox
from app.services.delivery import serialize, serialize_detail
from app.services.reports import factor_label, resolve_range
from app.services.spatial_risk import SpatialRiskService

NOW = datetime.now(timezone.utc)

def snapshot():
    return {"source": {"name": "Guwahati", "coordinate": {"lat": 26.1, "lng": 91.7}}, "destination": {"name": "Shillong", "coordinate": {"lat": 25.5, "lng": 91.9}},
            "data_quality": {"routing": {"status": "simulated", "provider": "demo"}}, "explanation": "x", "data_disclaimer": "d",
            "routes": [{"id": "route-2", "name": "Route B", "distance_km": 108.8, "duration_minutes": 194, "eta_minutes": 204, "road_quality": 84, "recommended": True, "recommended_vehicle": "Cargo Van",
                        "geometry": [{"lat": 26.1, "lng": 91.7}, {"lat": 25.5, "lng": 91.9}], "accessibility": {"score": 84, "status": "good", "factors": {}, "confidence": .7},
                        "risk": {"score": 21, "level": "low", "main_risks": []}, "weather": {"condition": "Clear"}, "terrain": {"classification": "hill"}, "hazards": {"status": "simulated", "zones_crossed": 0}}]}

def delivery_row(status="planned"):
    return SimpleNamespace(id=uuid.uuid4(), identifier="DLV-TEST", analysis_id=uuid.uuid4(), cargo_type="medicine", vehicle="Cargo Van", priority="high", status=status,
                           planned_departure=NOW, eta=NOW, actual_arrival=None, notes=None, created_at=NOW, updated_at=NOW, status_history=[{"from_status": None, "to_status": "planned", "note": None, "at": NOW.isoformat()}])

def test_delivery_response_contract_includes_allowed_transitions():
    payload = DeliveryResponse.model_validate(serialize((delivery_row(), "Guwahati", "Shillong", snapshot())))
    assert payload.allowed_transitions == ["in_transit", "cancelled"] and payload.accessibility == 84 and payload.risk_level == "low"

def test_delivery_detail_contract():
    analysis = SimpleNamespace(id=uuid.uuid4(), created_at=NOW, requested_vehicle="cargo_van", emergency_mode=False)
    summary = SpatialRiskService().unavailable(SimpleNamespace(data_quality={}), "Spatial database unavailable")
    detail = DeliveryDetailResponse.model_validate(serialize_detail((delivery_row("in_transit"), "Guwahati", "Shillong", snapshot()), analysis, {**summary, "analysis_id": "a", "route_id": None}))
    assert detail.route["name"] == "Route B" and len(detail.geometry) == 2 and detail.sensitive_transitions == ["completed", "cancelled"]
    assert detail.hazards["summary"]["hazard_status"] == "unavailable" and detail.status_history[0].to_status == "planned"
    assert detail.analysis["route_count"] == 1 and detail.source_coordinate == {"lat": 26.1, "lng": 91.7}

def test_transition_rules_contract():
    rules = TransitionRules(statuses=DELIVERY_STATUSES, transitions=DELIVERY_TRANSITIONS, sensitive=SENSITIVE_DELIVERY_STATUSES, priorities=DELIVERY_PRIORITIES)
    assert set(rules.transitions) == set(rules.statuses)

def test_spatial_summary_unavailable_contract_is_honest():
    summary = SpatialRiskService().unavailable(SimpleNamespace(data_quality={"routing": {"status": "live"}}), "Spatial database unavailable")
    payload = SpatialRiskSummaryContract.model_validate({**summary, "analysis_id": "a", "route_id": None})
    assert payload.hazard_status == "unavailable" and payload.zones_crossed is None and payload.confidence < .5

def test_dataset_contract_and_provenance_rules():
    row = SimpleNamespace(id=uuid.uuid4(), name="Demo", slug="demo", provider="p", source_organization="o", hazard_category="landslide", data_type="risk_zones", dataset_version="1", record_count=4,
                          published_at=None, downloaded_at=None, ingested_at=NOW, provenance_type="simulated", coverage_area="x", coverage_bbox=[91, 25, 92, 26], crs="EPSG:4326", status="imported",
                          is_live=False, license=None, source_url=None, metadata_json={"last_import": {"imported": 4}}, created_at=NOW, updated_at=NOW,
                          layer_type="landslide_susceptibility", attribution="© GSI", period_start=None, period_end=None)
    payload = DatasetContract.model_validate(serialize_dataset(row))
    assert payload.records == 4 and payload.last_import == {"imported": 4}
    assert serialize_dataset(row)["layer_label"] == "Landslide Susceptibility" and serialize_dataset(row)["attribution"] == "© GSI"
    assert normalize_provenance("static") == "historical" and normalize_provenance("susceptibility") == "estimated"
    try:
        normalize_provenance("authoritative-live-feed"); assert False
    except ValueError:
        pass
    assert validate_bbox([91, 25, 92, 26]) == [91.0, 25.0, 92.0, 26.0]

def test_reports_contract_and_range_resolution():
    start, end, key = resolve_range("7d", None, None)
    assert key == "7d" and (end - start).days == 7
    assert resolve_range("bogus", None, None)[2] == "30d"
    assert resolve_range(None, datetime(2026, 1, 1, tzinfo=timezone.utc), None)[2] == "custom"
    payload = ReportsSummaryContract.model_validate({"range": {"key": "7d"}, "risk_distribution": [{"name": "low", "value": 1}], "cargo_distribution": [], "delivery_status": [],
                                                    "accessibility_trend": [{"date": "2026-09-01", "average_accessibility": 80.5, "analyses": 3}], "risk_factors": [{"name": "Heavy rainfall", "value": 2}]})
    assert payload.accessibility_trend[0].average_accessibility == 80.5
    assert factor_label("Steep landslide-prone terrain") == "Steep terrain" and factor_label("Historical flood zone exposure") == "Flood exposure" and factor_label("No material route risks detected") is None
