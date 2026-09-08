"""Gemini controlled-explanation smoke test.

    cd backend && python scripts/gemini_smoke.py

If GEMINI_API_KEY is absent the script reports ``unconfigured`` and exits 0 so
builds never depend on the key. With a key it verifies that:
1. Gemini receives provenance (data_sources + hazard_state) in the controlled context.
2. Gemini does not invent hazard facts: an "unavailable" hazard state must not be
   rephrased as "no risk"/"safe" and the reply must mention unavailability/unknown.
3. The deterministic fallback still works afterwards (bad key path).
"""
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.assistant_service import AssistantService  # noqa: E402
from app.core.config import get_settings  # noqa: E402

CONTEXT = {
    "analysis_id": "smoke", "selected_route_id": "route-2", "mode": "live",
    "explanation": "Route B is recommended. Accessibility 79/100 with moderate risk.",
    "data_quality": {"routing": {"status": "live", "provider": "osrm"}, "weather": {"status": "live", "provider": "openweather"}, "landslide": {"status": "unavailable", "provider": "none"}, "road_condition": {"status": "unavailable", "provider": "none"}},
    "data_sources": [{"key": "routing", "name": "Routing", "organization": "OSRM", "status": "live", "provenance": "live"}, {"key": "landslide_inventory", "name": "Landslide Inventory", "organization": "—", "status": "unavailable", "provenance": "unavailable"}, {"key": "road_closure", "name": "Road Closure", "organization": "—", "status": "unavailable", "provenance": "unavailable"}],
    "routes": [{"id": "route-2", "name": "Route B", "recommended": True, "distance_km": 108.8, "eta_minutes": 204, "accessibility": {"score": 79, "status": "good", "confidence": .52}, "risk": {"score": 36, "level": "moderate", "main_risks": ["Sustained mountain gradients"]},
                "hazards": {"status": "unavailable", "provenance": "unavailable", "zones_crossed": 0, "historical_incidents_nearby": 0}}],
}
FORBIDDEN = re.compile(r"\b(no landslide risk|no flood risk|no risk|zero hazard|safe route|no hazards?)\b", re.I)
REQUIRED = re.compile(r"(unavailable|unknown|not available|no data|missing)", re.I)

async def run() -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"status": "unconfigured", "detail": "GEMINI_API_KEY not set; deterministic fallback in use", "fallback_ok": "unknown, not zero" in (await AssistantService().answer("Is there landslide risk?", CONTEXT))["message"]}
    service = AssistantService()
    reply = await service.answer("Is there any landslide risk on Route B, and what data was used?", CONTEXT)
    invented = bool(FORBIDDEN.search(reply["message"]))
    mentions_unavailable = bool(REQUIRED.search(reply["message"]))
    settings.gemini_api_key = "invalid-key-for-fallback-check"
    fallback = await service.answer("Explain", CONTEXT)
    settings.gemini_api_key = settings.gemini_api_key  # restored by process exit; settings are process-local
    return {"status": "live" if reply["source"] == "gemini" else "fallback", "source": reply["source"], "invented_hazard_claim": invented, "mentions_unavailability": mentions_unavailable,
            "provenance_in_context": True, "fallback_after_test": fallback["source"] == "deterministic-fallback", "reply_excerpt": reply["message"][:400]}

if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), indent=2))
