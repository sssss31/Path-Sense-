"""Gemini explanation with a deterministic fallback.

The model only ever sees a controlled context built server-side. Hazard data
state is always included so unavailable data is never rephrased as safety.
"""
import asyncio
import json
import logging

from app.core.config import get_settings
from app.core.domain import HAZARD_STATUS_INTERSECTION, HAZARD_STATUS_NO_INTERSECTION, HAZARD_STATUS_PARTIAL, HAZARD_STATUS_SIMULATED, HAZARD_STATUS_UNAVAILABLE

log = logging.getLogger("pathsense.assistant")

SYSTEM_RULES = (
    "You are PathSense, a logistics accessibility assistant. Explain only the supplied backend facts. "
    "Never invent route, weather, risk, score, closure, hazard or accessibility facts. "
    "Explicitly label simulated, estimated, historical and unavailable data. "
    "If hazard_state says data is unavailable or partial, say so plainly and never describe conditions as safe or clear because data is missing. "
    "Historical hazard datasets describe past or susceptible zones, never live alerts. "
    "Never infer 'no landslide risk' or 'no flood risk' from a missing or unavailable feed; only a dataset with full coverage and zero intersections may be described as no detected exposure. "
    "Distinguish landslide inventory (observed past events) from landslide susceptibility (terrain classification). Cite data_sources when describing evidence."
)

def hazard_state(hazards: dict | None) -> str:
    if not hazards:
        return "Hazard data unavailable: hazard exposure is unknown, not zero."
    status = hazards.get("status") or (hazards.get("summary") or {}).get("hazard_status") or HAZARD_STATUS_UNAVAILABLE
    zones = hazards.get("zones_crossed") or 0
    incidents = hazards.get("historical_incidents_nearby") or 0
    if status == HAZARD_STATUS_UNAVAILABLE:
        return "Hazard data unavailable: hazard exposure is unknown, not zero."
    if status == HAZARD_STATUS_SIMULATED or hazards.get("provenance") == "simulated" or (hazards.get("summary") or {}).get("provenance") == "simulated":
        return f"Simulated demo hazard data (not authoritative) indicates {zones} risk-zone intersection(s) and {incidents} nearby incident(s)."
    if status == HAZARD_STATUS_PARTIAL:
        return f"Historical hazard datasets cover only part of the route; {zones} intersection(s) found within covered sections. Uncovered sections are unknown."
    if status == HAZARD_STATUS_NO_INTERSECTION:
        return f"Historical hazard datasets cover the route and confirm no risk-zone intersections; {incidents} historical incident(s) within 2 km."
    return f"Historical hazard data indicates {zones} risk-zone intersection(s) over {hazards.get('affected_distance_km', 0)} km and {incidents} historical incident(s) within 2 km."

class AssistantService:
    async def answer(self, message: str, context: dict) -> dict:
        settings = get_settings()
        routes = context.get("routes", [])[:3]
        selected = next((r for r in routes if r.get("id") == context.get("selected_route_id")), routes[0] if routes else {})
        safe = {
            "analysis_id": context.get("analysis_id"), "selected_route_id": context.get("selected_route_id"), "mode": context.get("mode"),
            "routes": [self.route_facts(r) for r in routes], "data_quality": context.get("data_quality", {}),
            "data_sources": [{k: s.get(k) for k in ("key", "name", "organization", "status", "provenance", "coverage", "period")} for s in context.get("data_sources", [])][:12],
            "hazard_state": hazard_state(selected.get("hazards")), "explanation": context.get("explanation", ""),
        }
        fallback = self.fallback(context, safe["hazard_state"])
        return await self.generate(message, safe, fallback)

    async def explain_delivery(self, message: str, delivery: dict) -> dict:
        """Controlled delivery context: summary, associated analysis facts, hazards, status. Nothing else."""
        safe = {
            "delivery": {k: delivery.get(k) for k in ["identifier", "source", "destination", "cargo_type", "vehicle", "priority", "status", "planned_departure", "estimated_arrival", "actual_arrival", "allowed_transitions"]},
            "route": delivery.get("route"), "accessibility": delivery.get("accessibility_detail"), "risk": delivery.get("risk"),
            "weather": delivery.get("weather"), "terrain": delivery.get("terrain"), "hazard_state": hazard_state(delivery.get("hazards")),
            "data_quality": delivery.get("data_quality", {}), "analysis": {k: v for k, v in (delivery.get("analysis") or {}).items() if k in {"analysis_id", "created_at", "explanation", "data_disclaimer"}},
        }
        safe = json.loads(json.dumps(safe, default=str))
        fallback = self.delivery_fallback(delivery, safe["hazard_state"])
        return await self.generate(message, safe, fallback)

    async def generate(self, message: str, safe: dict, fallback: str) -> dict:
        settings = get_settings()
        if not settings.gemini_api_key:
            return {"message": fallback, "source": "deterministic-fallback", "status": "unavailable"}
        prompt = SYSTEM_RULES + "\nQUESTION: " + message + "\nCONTEXT:" + json.dumps(safe, default=str)
        try:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
            response = await asyncio.wait_for(asyncio.to_thread(client.models.generate_content, model=settings.gemini_model, contents=prompt), timeout=settings.gemini_timeout_seconds)
            return {"message": response.text, "source": "gemini", "status": "live"}
        except Exception as exc:
            detail = f"{type(exc).__name__}: {str(exc)[:160]}"
            log.warning("gemini_unavailable: %s", detail)
            return {"message": fallback, "source": "deterministic-fallback", "status": "unavailable", "detail": detail}

    @staticmethod
    def route_facts(r: dict) -> dict:
        hazards = r.get("hazards") or {}
        return {"id": r.get("id"), "name": r.get("name"), "distance_km": r.get("distance_km"), "eta_minutes": r.get("eta_minutes"),
                "accessibility": {k: v for k, v in (r.get("accessibility") or {}).items() if k in {"score", "status", "confidence", "confidence_factors", "explanations"}},
                "risk": r.get("risk"), "weather": r.get("weather"), "terrain": r.get("terrain"),
                "recommended_vehicle": r.get("recommended_vehicle"), "recommended": r.get("recommended"), "hazard_state": hazard_state(hazards),
                "hazard_features": {"landslide": hazards.get("landslide"), "flood": hazards.get("flood"), "status": hazards.get("status"), "provenance": hazards.get("provenance")}}

    def fallback(self, context: dict, state: str) -> str:
        base = context.get("explanation") or "Run or select a route analysis first. I will explain backend-calculated evidence without inventing operational data."
        return base if state in base else f"{base} {state}"

    def delivery_fallback(self, d: dict, state: str) -> str:
        access = (d.get("accessibility_detail") or {}).get("score", d.get("accessibility"))
        risk = (d.get("risk") or {}).get("level", d.get("risk_level"))
        route = (d.get("route") or {}).get("name", "the recommended route")
        return (f"Delivery {d.get('identifier')} from {d.get('source')} to {d.get('destination')} is {str(d.get('status','')).replace('_',' ')} with {d.get('priority')} priority. "
                f"It follows {route} with an accessibility score of {access} and {risk} risk, using a {str(d.get('vehicle','')).lower()}. {state} "
                "Weather and terrain figures are the snapshot recorded at analysis time, not a live update.")
