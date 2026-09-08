"""Rule-based risk, accessibility, vehicle and decision engines (v3).

Risk contributions are separate and centrally configured in
app.core.domain.RISK_CONTRIBUTIONS: rainfall, visibility, terrain slope, road
quality, landslide susceptibility, historical landslide proximity and
historical flood exposure. Only confirmed normalized hazard features add
points; unavailable data adds nothing (confidence reports it instead).
Explanations are derived from the same normalized values.
"""
from app.core.domain import RISK_CONTRIBUTIONS, SUITABILITY_PENALTIES, SUSCEPTIBILITY_LABELS, UNAVAILABLE_FACTOR_SCORES, VEHICLE_ALIASES, VEHICLE_PROFILES
from app.schemas.analysis import Accessibility, HazardExposure, Risk, Terrain, Weather

# Kept for backward compatibility with earlier imports/tests.
HAZARD_RISK_POINTS = {"zone_base": 6, "per_zone": 4, "per_affected_km": 2, "critical_bonus": 8, "incidents_threshold": 3, "incidents_points": 6, "cap": 30}
SUSCEPTIBILITY_ORDER = ["none", "low", "moderate", "high", "critical"]

def hazard_prefix(hazards: HazardExposure | None) -> str:
    if hazards and (hazards.status == "simulated" or hazards.provenance == "simulated"):
        return "Simulated"
    return "Historical"

class RuleBasedRiskModel:
    def evaluate(self, weather: Weather, terrain: Terrain, road_quality: int, hazards: HazardExposure | None = None) -> Risk:
        cfg = RISK_CONTRIBUTIONS
        score, risks = cfg["base"], []
        if weather.rainfall_mm >= cfg["rainfall"]["heavy_mm"]: score += cfg["rainfall"]["heavy_points"]; risks.append("Heavy rainfall along exposed sections")
        elif weather.rainfall_mm >= cfg["rainfall"]["moderate_mm"]: score += cfg["rainfall"]["moderate_points"]; risks.append("Intermittent rainfall may reduce traction")
        if terrain.average_slope >= cfg["terrain"]["steep_slope"]: score += cfg["terrain"]["steep_points"]; risks.append("Steep landslide-prone terrain")
        elif terrain.average_slope >= cfg["terrain"]["sustained_slope"]: score += cfg["terrain"]["sustained_points"]; risks.append("Sustained mountain gradients")
        if road_quality < cfg["road"]["poor_quality"]: score += cfg["road"]["points"]; risks.append("Variable road surface quality")
        if weather.visibility_km < cfg["visibility"]["threshold_km"]: score += cfg["visibility"]["points"]; risks.append("Low visibility")
        score += self.hazard_points(hazards, risks)
        score = min(score, cfg["cap"])
        return Risk(score=score, level="high" if score >= 60 else "moderate" if score >= 35 else "low", main_risks=risks or ["No material risk factors detected from available data"])

    def hazard_points(self, hazards: HazardExposure | None, risks: list[str]) -> int:
        """Separate contributions: susceptibility zones, historical landslide proximity, historical flood exposure."""
        if not hazards or hazards.status == "unavailable":
            return 0
        cfg = RISK_CONTRIBUTIONS
        prefix = hazard_prefix(hazards)
        total = 0
        ls, fl = hazards.landslide, hazards.flood
        # 1. landslide susceptibility (terrain classification)
        if ls.susceptibility_zones_crossed > 0:
            sus = cfg["landslide_susceptibility"]
            points = min(sus["cap"], sus.get(ls.highest_susceptibility, sus["low"]) + sus["per_zone"] * ls.susceptibility_zones_crossed)
            total += points
            risks.append(f"Route crosses {ls.highest_susceptibility} landslide-susceptibility area" + (" (simulated)" if prefix == "Simulated" else ""))
        # 2. historical landslide proximity (validated observed events)
        prox = cfg["historical_landslide_proximity"]
        if ls.historical_incidents_within_2km >= prox["threshold"]:
            total += min(prox["cap"], prox["per_incident"] * ls.historical_incidents_within_2km)
            risks.append(f"{ls.historical_incidents_within_2km} {prefix.lower()} landslide incident(s) within 2 km")
        # 3. historical flood exposure
        if fl.historical_zones_crossed > 0:
            fx = cfg["historical_flood_exposure"]
            total += min(fx["cap"], fx["base"] + round(fx["per_km"] * fl.affected_distance_km))
            risks.append(f"{fl.affected_distance_km} km {prefix.lower()} flood-hazard exposure")
        # 4. legacy zones (datasets registered without a specific layer type) not already counted above
        for category, exposure in hazards.categories.items():
            if exposure.zones_crossed <= 0:
                continue
            if category == "landslide" and ls.susceptibility_zones_crossed > 0:
                continue
            if category == "flood" and fl.historical_zones_crossed > 0:
                continue
            points = HAZARD_RISK_POINTS["zone_base"] + HAZARD_RISK_POINTS["per_zone"] * exposure.zones_crossed + round(HAZARD_RISK_POINTS["per_affected_km"] * exposure.affected_distance_km)
            if exposure.highest_severity == "critical": points += HAZARD_RISK_POINTS["critical_bonus"]
            total += points
            risks.append(f"{prefix} {category.replace('_', ' ')} zone exposure")
        # 5. legacy incident proximity when the inventory family is not separated
        if hazards.historical_incidents_nearby >= HAZARD_RISK_POINTS["incidents_threshold"] and ls.historical_incidents_within_2km < prox["threshold"]:
            total += HAZARD_RISK_POINTS["incidents_points"]; risks.append(f"{prefix} incidents near route")
        return min(total, 40)

class AccessibilityEngine:
    def __init__(self, weights: dict[str, float]): self.weights = weights

    def calculate(self, road_quality: int, weather: Weather, terrain: Terrain, risk: Risk, vehicle_score: int, hazards: HazardExposure | None = None) -> Accessibility:
        factors = {
            "road_quality": road_quality,
            "weather": UNAVAILABLE_FACTOR_SCORES["weather"] if weather.data_status == "unavailable" else max(0, 100 - weather.rainfall_probability // 2 - (15 if weather.visibility_km < 5 else 0)),
            "terrain": UNAVAILABLE_FACTOR_SCORES["terrain"] if terrain.data_status == "unavailable" else max(0, 100 - round(terrain.average_slope * 4)),
            "historical_risk": max(0, 100 - risk.score),
            "current_disruption": max(0, 100 - risk.score // 2),
            "vehicle_suitability": vehicle_score,
        }
        score = round(sum(factors[k] * self.weights[k] for k in self.weights))
        status = "excellent" if score >= 85 else "good" if score >= 70 else "moderate" if score >= 50 else "high_risk" if score >= 30 else "potentially_inaccessible"
        ordered = sorted(factors, key=factors.get)
        return Accessibility(score=score, status=status, factors=factors, confidence=1.0, factor_weights=self.weights, main_negative_factors=ordered[:2], main_positive_factors=ordered[-2:],
                             explanations=explain(road_quality, weather, terrain, vehicle_score, hazards))

def explain(road_quality: int, weather: Weather, terrain: Terrain, vehicle_score: int, hazards: HazardExposure | None) -> dict[str, list[str]]:
    """Plain-language factor explanations built only from normalized values."""
    cfg = RISK_CONTRIBUTIONS
    negative, positive = [], []
    if weather.data_status == "unavailable": negative.append("Weather data unavailable (no live weather feed); rainfall risk not evaluated")
    elif weather.rainfall_mm >= cfg["rainfall"]["heavy_mm"]: negative.append(f"Heavy rainfall ({weather.rainfall_mm} mm) along the route")
    elif weather.rainfall_mm >= cfg["rainfall"]["moderate_mm"]: negative.append(f"Intermittent rainfall ({weather.rainfall_mm} mm)")
    else: positive.append(f"Sampled rainfall below risk threshold ({weather.rainfall_mm} mm; {weather.condition.lower()} reported at the wettest sample point)" if weather.rainfall_mm > 0 else "No rainfall in the sampled weather")
    if weather.data_status != "unavailable" and weather.visibility_km < cfg["visibility"]["threshold_km"]: negative.append(f"Low visibility ({weather.visibility_km} km)")
    if terrain.data_status == "unavailable": negative.append("Terrain data unavailable; slope risk not evaluated")
    elif terrain.average_slope >= cfg["terrain"]["steep_slope"]: negative.append(f"Steep terrain ({terrain.average_slope}° slope)")
    elif terrain.average_slope >= cfg["terrain"]["sustained_slope"]: negative.append(f"Sustained gradients ({terrain.average_slope}° slope)")
    else: positive.append(f"Lower slope ({terrain.average_slope}°)")
    if road_quality < cfg["road"]["poor_quality"]: negative.append(f"Variable road surface quality ({road_quality}/100)")
    else: positive.append(f"Good road surface quality ({road_quality}/100)")
    if vehicle_score >= 85: positive.append(f"Good vehicle suitability ({vehicle_score}/100)")
    if hazards and hazards.status != "unavailable":
        prefix = hazard_prefix(hazards)
        ls, fl = hazards.landslide, hazards.flood
        tag = "simulated demo data" if prefix == "Simulated" else "dataset coverage full"
        if ls.susceptibility_zones_crossed: negative.append(f"Route crosses {ls.highest_susceptibility} landslide-susceptibility area ({ls.susceptibility_zones_crossed} zone(s), {ls.susceptibility_affected_km} km{', simulated' if prefix == 'Simulated' else ''})")
        elif ls.susceptibility_coverage == "full": positive.append(f"No landslide-susceptibility zone crossed ({tag})")
        if ls.historical_incidents_within_2km: negative.append(f"{ls.historical_incidents_within_2km} {prefix.lower()} landslide incident(s) within 2 km")
        elif ls.inventory_coverage == "full": positive.append(f"No recorded landslide incident within 2 km ({'simulated demo data' if prefix == 'Simulated' else 'inventory coverage full'})")
        if fl.historical_zones_crossed: negative.append(f"{fl.affected_distance_km} km {prefix.lower()} flood-hazard exposure")
        elif fl.dataset_coverage == "full": positive.append(f"No {prefix.lower()} flood-hazard zone crossed ({tag})")
    else:
        negative.append("Hazard datasets unavailable for this route (exposure unknown, not zero)")
    return {"negative": negative, "positive": positive}

class VehicleService:
    """Scores every vehicle profile against terrain, road quality, risk and cargo; recommends the best and assesses the requested one."""
    @staticmethod
    def resolve(code: str | None) -> str | None:
        if not code:
            return None
        key = code.strip().lower().replace("-", "_").replace(" ", "_")
        if key in VEHICLE_PROFILES:
            return key
        return VEHICLE_ALIASES.get(code.strip().lower())

    def suitability(self, code: str, risk: Risk, terrain: Terrain, cargo: str, road_quality: int = 70) -> tuple[int, list[str]]:
        p = VEHICLE_PROFILES[code]; pen = SUITABILITY_PENALTIES; score = p["base_score"]; notes = []
        if terrain.average_slope > p["max_slope"]:
            score -= round(pen["slope_over"] * (terrain.average_slope - p["max_slope"])); notes.append(f"slope {terrain.average_slope}° exceeds {p['name']} limit {p['max_slope']}°")
        if road_quality < p["min_road_quality"]:
            score -= round(pen["road_under"] * (p["min_road_quality"] - road_quality) / 5); notes.append(f"road quality {road_quality} below {p['name']} minimum {p['min_road_quality']}")
        if cargo not in p["cargo"]:
            score -= pen["cargo_mismatch"]; notes.append(f"{p['name']} is not rated for {cargo.replace('_', ' ')}")
        if risk.level == "high" and code != "4x4_utility":
            score -= pen["high_risk_non_4x4"]; notes.append("high route risk favours a 4x4 utility vehicle")
        return max(pen["floor"], min(100, score)), notes

    def recommend(self, risk: Risk, terrain: Terrain, cargo: str, road_quality: int = 70, requested: str | None = None) -> tuple[str, int]:
        best = self.assess(risk, terrain, cargo, road_quality, requested)
        return best["recommended"], best["recommended_suitability"]

    def assess(self, risk: Risk, terrain: Terrain, cargo: str, road_quality: int = 70, requested: str | None = None) -> dict:
        scored = {code: self.suitability(code, risk, terrain, cargo, road_quality) for code in VEHICLE_PROFILES}
        best_code = max(scored, key=lambda c: (scored[c][0], -list(VEHICLE_PROFILES).index(c)))
        out = {"recommended": VEHICLE_PROFILES[best_code]["name"], "recommended_code": best_code, "recommended_suitability": scored[best_code][0],
               "options": [{"code": c, "name": VEHICLE_PROFILES[c]["name"], "suitability": scored[c][0], "notes": scored[c][1]} for c in VEHICLE_PROFILES]}
        req = self.resolve(requested)
        if req:
            score, notes = scored[req]
            out.update(requested=VEHICLE_PROFILES[req]["name"], requested_code=req, requested_suitability=score, requested_notes=notes,
                       warning=(f"Requested {VEHICLE_PROFILES[req]['name']} scores {score}/100 here; {VEHICLE_PROFILES[best_code]['name']} scores {scored[best_code][0]}/100." if score < scored[best_code][0] - 5 else None))
        return out

class DecisionService:
    def rank(self, routes: list, emergency: bool) -> list:
        def utility(r):
            safety = r.accessibility.score * (1.35 if emergency else 1.0)
            time_penalty = r.duration_minutes * (.08 if emergency else .14)
            return safety - time_penalty - r.risk.score * .15
        return sorted(routes, key=utility, reverse=True)
