from app.core.config import get_settings
from app.schemas.analysis import Weather,Terrain
from app.services.engines import RuleBasedRiskModel,AccessibilityEngine,VehicleService,DecisionService

def fixtures(rain=28,slope=15):
    return Weather(temperature_c=18,rainfall_mm=rain,rainfall_probability=88,humidity=82,wind_kph=13,visibility_km=3.8,condition="Rain"), Terrain(elevation_m=1500,average_slope=slope,classification="Mountain")

def test_heavy_rain_and_steep_terrain_is_high_risk():
    weather,terrain=fixtures(); risk=RuleBasedRiskModel().evaluate(weather,terrain,60)
    assert risk.level=="high" and risk.score>=60 and len(risk.main_risks)>=2

def test_accessibility_score_is_bounded_and_classified():
    weather,terrain=fixtures(2,4); risk=RuleBasedRiskModel().evaluate(weather,terrain,90)
    result=AccessibilityEngine(get_settings().scoring_weights).calculate(90,weather,terrain,risk,90)
    assert 70<=result.score<=100 and result.status in {"good","excellent"}

def test_vehicle_recommendation_matches_harsh_terrain():
    weather,terrain=fixtures(); risk=RuleBasedRiskModel().evaluate(weather,terrain,60)
    assert VehicleService().recommend(risk,terrain,"medicine")[0]=="4x4 Utility Vehicle"
