from app.ai.assistant_service import hazard_state
from app.core.domain import HAZARD_STATUS_NO_INTERSECTION, HAZARD_STATUS_PARTIAL, HAZARD_STATUS_UNAVAILABLE, hazard_label
from app.schemas.analysis import HazardCategoryExposure, HazardExposure, Terrain, Weather
from app.services.confidence import confidence_for, hazard_quality
from app.services.engines import RuleBasedRiskModel
from app.services.hazards import coverage_ratio, hazard_sentence, simulated_exposure
from app.schemas.analysis import Coordinate

LIVE = {k: {"status": "live"} for k in ["routing", "weather", "terrain", "landslide", "road_condition"]}

def weather(rain=2):
    return Weather(temperature_c=20, rainfall_mm=rain, rainfall_probability=10, humidity=60, wind_kph=5, visibility_km=9, condition="Clear")

def test_partial_coverage_lowers_confidence_and_explains_why():
    full, _ = confidence_for({**LIVE, "landslide": {"status": "historical"}})
    partial, reasons = confidence_for({**LIVE, "landslide": hazard_quality(HazardExposure(status=HAZARD_STATUS_PARTIAL, provenance="historical", coverage_ratio=.6))})
    missing, missing_reasons = confidence_for({**LIVE, "landslide": hazard_quality(HazardExposure(status=HAZARD_STATUS_UNAVAILABLE))})
    assert full > partial > missing
    assert "Historical landslide dataset does not cover the full route." in reasons
    assert any("unavailable" in r.lower() for r in missing_reasons)

def test_unavailable_hazard_data_does_not_change_risk_or_accessibility_inputs():
    model = RuleBasedRiskModel()
    base = model.evaluate(weather(), Terrain(elevation_m=100, average_slope=2, classification="flat"), 90)
    unavailable = model.evaluate(weather(), Terrain(elevation_m=100, average_slope=2, classification="flat"), 90, HazardExposure(status=HAZARD_STATUS_UNAVAILABLE))
    none = model.evaluate(weather(), Terrain(elevation_m=100, average_slope=2, classification="flat"), 90, HazardExposure(status=HAZARD_STATUS_NO_INTERSECTION, provenance="historical"))
    assert base.score == unavailable.score == none.score
    assert "No material risk factors detected from available data" in base.main_risks

def test_confirmed_hazard_exposure_adds_risk_with_historical_wording():
    model = RuleBasedRiskModel()
    exposure = HazardExposure(status="intersections", provenance="historical", zones_crossed=2, affected_distance_km=3.4, highest_severity="critical",
                              categories={"landslide": HazardCategoryExposure(zones_crossed=2, affected_distance_km=3.4, highest_severity="critical", label="Historical Landslide Zone")}, historical_incidents_nearby=4)
    result = model.evaluate(weather(), Terrain(elevation_m=100, average_slope=2, classification="flat"), 90, exposure)
    assert result.score > 8 and "Historical landslide zone exposure" in result.main_risks and "Historical incidents near route" in result.main_risks
    assert not any("live" in r.lower() or "alert" in r.lower() for r in result.main_risks)

def test_coverage_ratio_and_status_semantics():
    points = [Coordinate(lat=25.5 + i * .1, lng=91.5) for i in range(5)]
    assert coverage_ratio(points, [[91, 25, 92, 27]]) == 1.0
    assert coverage_ratio(points, [[91, 25, 92, 25.65]]) == .4
    assert coverage_ratio(points, []) is None

def test_hazard_sentences_never_rephrase_missing_data_as_safe():
    assert "unknown rather than zero" in hazard_sentence(HazardExposure(status=HAZARD_STATUS_UNAVAILABLE))
    assert "only part" in hazard_sentence(HazardExposure(status=HAZARD_STATUS_PARTIAL, provenance="historical", coverage_ratio=.5))
    assert "no risk-zone intersections" in hazard_sentence(HazardExposure(status=HAZARD_STATUS_NO_INTERSECTION, provenance="historical"))
    assert "unknown, not zero" in hazard_sentence(HazardExposure(status=HAZARD_STATUS_PARTIAL, provenance="historical", coverage_ratio=.5))
    assert "not authoritative" in hazard_sentence(simulated_exposure(1))
    assert "unknown, not zero" in hazard_state(None)
    assert "not authoritative" in hazard_state(simulated_exposure(1).model_dump())

def test_hazard_labels_follow_claim_rules():
    assert hazard_label("landslide", "historical") == "Historical Landslide Zone"
    assert hazard_label("flood", "estimated") == "Flood-Prone Area"
    assert "demo" in hazard_label("landslide", "simulated")
    assert hazard_label("landslide", "live") == "Live Landslide Alert"
