import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.core.config import get_settings
from app.core.domain import COVERAGE_FULL, COVERAGE_NONE
from app.providers.live import NominatimGeocodingProvider, OSRMRoutingProvider, OpenWeatherProvider, OpenElevationTerrainProvider
from app.providers.mock import MockGeocodingProvider, MockRoutingProvider, MockWeatherProvider, MockTerrainProvider
from app.schemas.analysis import AnalysisRequest, AnalysisResponse, HazardExposure, RouteResult
from app.services.confidence import confidence_for, confidence_v3, hazard_quality
from app.services.engines import AccessibilityEngine, DecisionService, RuleBasedRiskModel, VehicleService
from app.services.hazards import HazardIntelligenceService, hazard_sentence
from app.services.sources import current_feed_sources, dataset_sources_for_route, imported_datasets, mode_name, provider_sources

def confidence_inputs(exposure: HazardExposure, simulated: bool, datasets: list) -> dict:
    """Map provider states + hazard coverage into the factor spec consumed by confidence_v3."""
    ls, fl = exposure.landslide, exposure.flood
    if exposure.status == "unavailable":
        hazard = {"provenance": "unavailable", "coverage": COVERAGE_NONE}
        inv, sus, flood = hazard, hazard, hazard
    else:
        prov = exposure.provenance
        def period_end(layer_types):
            ends = [d.period_end for d in datasets if d.layer_type in layer_types and d.period_end]
            return max(ends) if ends else None
        inv = {"provenance": prov if ls.inventory_coverage != COVERAGE_NONE else "unavailable", "coverage": ls.inventory_coverage, "period_end": period_end({"landslide_inventory", "incidents"}), "reason": "Landslide inventory does not cover this route." if ls.inventory_coverage != COVERAGE_FULL else None}
        sus = {"provenance": prov if ls.susceptibility_coverage != COVERAGE_NONE else "unavailable", "coverage": ls.susceptibility_coverage, "period_end": period_end({"landslide_susceptibility"}), "reason": "Landslide susceptibility dataset does not cover the full route." if ls.susceptibility_coverage != COVERAGE_FULL else None}
        flood = {"provenance": prov if fl.dataset_coverage != COVERAGE_NONE else "unavailable", "coverage": fl.dataset_coverage, "period_end": period_end({"flood_hazard", "flood_inundation"}), "reason": "Flood hazard dataset does not cover this route." if fl.dataset_coverage != COVERAGE_FULL else None}
    return {
        "routing": {"provenance": "simulated" if simulated else "live", "coverage": COVERAGE_FULL},
        "weather": {"provenance": "simulated" if simulated else "live", "coverage": COVERAGE_FULL},
        "terrain": {"provenance": "simulated" if simulated else "estimated", "coverage": COVERAGE_FULL},
        "landslide_inventory": inv, "landslide_susceptibility": sus, "flood_hazard": flood,
        "road_condition": {"provenance": "simulated" if simulated else "unavailable", "coverage": COVERAGE_FULL if simulated else COVERAGE_NONE, "reason": None if simulated else "Current road-closure data is unavailable."},
    }

class RouteAnalysisService:
    def __init__(self):
        settings = get_settings()
        if settings.use_mock_data:
            self.geocoder = MockGeocodingProvider(); self.router = MockRoutingProvider(); self.weather = MockWeatherProvider(); self.terrain = MockTerrainProvider()
        else:
            self.geocoder = NominatimGeocodingProvider(); self.router = OSRMRoutingProvider(); self.weather = OpenWeatherProvider(); self.terrain = OpenElevationTerrainProvider()
        self.risk = RuleBasedRiskModel(); self.accessibility = AccessibilityEngine(settings.scoring_weights)
        self.vehicles = VehicleService(); self.decisions = DecisionService()

    async def analyze(self, request: AnalysisRequest, session=None) -> AnalysisResponse:
        """Run the pipeline. Without a PostGIS session hazard exposure is reported as unavailable (or simulated in demo mode)."""
        settings = get_settings()
        simulated = settings.use_mock_data
        source, destination = await asyncio.gather(self.geocoder.geocode(request.source.name), self.geocoder.geocode(request.destination.name))
        candidates = await self.router.routes(source, destination)
        hazard_service = HazardIntelligenceService(session)
        datasets = await imported_datasets(session, include_simulated=simulated)

        async def enrich(raw):
            weather, terrain = await asyncio.gather(self.weather.weather_for_route(raw), self.terrain.terrain_for_route(raw))
            hazards = await hazard_service.exposure_for_points(raw["geometry"], raw.get("variant"))
            risk = self.risk.evaluate(weather, terrain, raw["road_quality"], hazards)
            assessment = self.vehicles.assess(risk, terrain, request.cargo_type.value, raw["road_quality"], request.vehicle_type)
            vehicle, suitability = assessment["recommended"], assessment["recommended_suitability"]
            accessibility = self.accessibility.calculate(raw["road_quality"], weather, terrain, risk, assessment.get("requested_suitability", suitability), hazards)
            overall, per_factor, reasons = confidence_v3(confidence_inputs(hazards, simulated, datasets))
            accessibility.confidence = overall; accessibility.confidence_factors = per_factor; accessibility.confidence_reasons = reasons
            delay = round(risk.score * .28)
            return RouteResult(**{k: v for k, v in raw.items() if k not in {"variant", "legs"}}, eta_minutes=raw["duration_minutes"] + delay, weather=weather, terrain=terrain, risk=risk, accessibility=accessibility, recommended_vehicle=vehicle, vehicle_assessment=assessment, hazards=hazards)

        routes = [await enrich(r) for r in candidates] if session is not None else list(await asyncio.gather(*(enrich(r) for r in candidates)))
        ranked = self.decisions.rank(routes, request.emergency_mode); best = ranked[0]; best.recommended = True
        best.rationale = f"{best.name} offers the strongest reliability balance with {best.accessibility.score}/100 accessibility and {best.risk.level} risk."
        quality = {"routing": {"status": "simulated" if simulated else "live", "provider": "demo" if simulated else "osrm"},
                   "weather": {"status": "simulated" if simulated else "live", "provider": "demo" if simulated else "openweather"},
                   "terrain": {"status": "simulated" if simulated else "estimated", "provider": "demo" if simulated else "open-elevation"},
                   "landslide": hazard_quality(best.hazards),
                   "road_condition": {"status": "simulated" if simulated else "unavailable", "provider": "demo" if simulated else "none", "reason": None if simulated else "Current road-closure data is unavailable."}}
        sources = provider_sources(simulated) + dataset_sources_for_route(datasets, best.geometry, best.hazards) + current_feed_sources()
        negatives = best.accessibility.explanations.get("negative", [])
        positives = best.accessibility.explanations.get("positive", [])
        explanation = (f"{best.name} is recommended: accessibility score {best.accessibility.score}/100 with {best.risk.level} risk."
                       + (f" Main concerns: {'; '.join(negatives[:2]).lower()}." if negatives else "") + (f" In its favour: {'; '.join(positives[:2]).lower()}." if positives else "")
                       + f" {hazard_sentence(best.hazards)} "
                       + ("Routing, weather and terrain are simulated demo providers. " if simulated else "Routing and weather are live; terrain is estimated. ")
                       + ("Current road-closure data is simulated in demo mode. " if simulated else "Current road-closure information is unavailable. ")
                       + f"Use a {best.recommended_vehicle.lower()} and retain a weather check before dispatch.")
        return AnalysisResponse(analysis_id=str(uuid4()), generated_at=datetime.now(timezone.utc), source=source, destination=destination, recommended_route_id=best.id, routes=routes,
                                explanation=explanation, data_disclaimer="Demo providers are clearly simulated." if simulated else "Live and estimated sources are identified per source; historical datasets are never live alerts.",
                                data_quality=quality, data_sources=sources, mode=mode_name())
