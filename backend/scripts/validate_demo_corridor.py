"""Pre-hackathon diagnostic: run the full pipeline for a corridor and report every evidence layer.

    cd backend && python scripts/validate_demo_corridor.py                       # Guwahati -> Shillong
    python scripts/validate_demo_corridor.py --source Guwahati --destination Tura --json

Uses the configured providers (demo or live) and the configured DATABASE_URL.
Reports providers, route count, dataset coverage, weather/terrain coverage,
historical incidents, hazard zones, accessibility scores, confidence and the
recommendation. Exit code 1 when the analysis itself fails.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.schemas.analysis import AnalysisRequest, CargoType, LocationInput  # noqa: E402
from app.services.analysis import RouteAnalysisService  # noqa: E402
from app.services.sources import readiness  # noqa: E402

async def run(source: str, destination: str, cargo: str) -> dict:
    settings = get_settings()
    session = None
    try:
        from app.database.session import SessionLocal
        session = SessionLocal()
    except Exception:
        session = None
    started = time.perf_counter()
    try:
        result = await RouteAnalysisService().analyze(AnalysisRequest(source=LocationInput(name=source), destination=LocationInput(name=destination), cargo_type=CargoType(cargo)), session)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)[:300], "mode": "demo" if settings.use_mock_data else "live"}
    ready = await readiness(session)
    if session is not None:
        await session.close()
    best = next(r for r in result.routes if r.recommended)
    return {
        "ok": True, "mode": result.mode, "elapsed_seconds": round(time.perf_counter() - started, 2), "corridor": f"{result.source.name} → {result.destination.name}",
        "providers": {k: v for k, v in result.data_quality.items()}, "route_count": len(result.routes),
        "data_sources": [{"name": s.name, "organization": s.organization, "status": s.status, "coverage": s.coverage, "period": s.period} for s in result.data_sources],
        "dataset_coverage": {"landslide_inventory": best.hazards.landslide.inventory_coverage, "landslide_susceptibility": best.hazards.landslide.susceptibility_coverage, "flood_hazard": best.hazards.flood.dataset_coverage, "overall_status": best.hazards.status},
        "weather_coverage": result.data_quality.get("weather", {}).get("status"), "terrain_coverage": result.data_quality.get("terrain", {}).get("status"),
        "historical_incidents_within_2km": best.hazards.landslide.historical_incidents_within_2km, "hazard_zones_crossed": best.hazards.zones_crossed,
        "hazard_features": {"landslide": best.hazards.landslide.model_dump(), "flood": best.hazards.flood.model_dump()},
        "routes": [{"id": r.id, "name": r.name, "distance_km": r.distance_km, "eta_minutes": r.eta_minutes, "accessibility": r.accessibility.score, "risk": r.risk.score, "risk_level": r.risk.level,
                    "confidence": r.accessibility.confidence, "hazard_status": r.hazards.status, "recommended": r.recommended} for r in result.routes],
        "confidence": best.accessibility.confidence, "confidence_factors": best.accessibility.confidence_factors, "confidence_reasons": best.accessibility.confidence_reasons,
        "explanations": best.accessibility.explanations, "recommendation": {"route": best.name, "vehicle": best.recommended_vehicle, "explanation": result.explanation},
        "readiness": {k: v for k, v in ready.items() if k in {"hazard_intelligence", "missing", "routing", "weather", "terrain", "database", "database_target", "database_reachable", "external_layers"}},
    }

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--source", default="Guwahati"); parser.add_argument("--destination", default="Shillong"); parser.add_argument("--cargo", default="medicine"); parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = asyncio.run(run(args.source, args.destination, args.cargo))
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        if not report["ok"]:
            print(f"ANALYSIS FAILED ({report['mode']} mode): {report['error']}: {report['detail']}"); sys.exit(1)
        print(f"Corridor: {report['corridor']}  mode={report['mode']}  routes={report['route_count']}  {report['elapsed_seconds']}s")
        print(f"  database: {report['readiness'].get('database')} {report['readiness'].get('database_target') or ''} reachable={report['readiness'].get('database_reachable')}")
        for k, v in report["providers"].items(): print(f"  provider {k:14s} {v.get('status'):12s} {v.get('provider')}")
        print("  dataset coverage:", report["dataset_coverage"])
        print(f"  historical incidents within 2 km: {report['historical_incidents_within_2km']}   hazard zones crossed: {report['hazard_zones_crossed']}")
        for r in report["routes"]: print(f"  {'*' if r['recommended'] else ' '} {r['name']:26s} acc={r['accessibility']:3d} risk={r['risk']:3d} ({r['risk_level']}) conf={r['confidence']} hazards={r['hazard_status']}")
        print("  confidence factors:", report["confidence_factors"])
        print("  negative:", report["explanations"]["negative"]); print("  positive:", report["explanations"]["positive"])
        print("  recommendation:", report["recommendation"]["route"], "/", report["recommendation"]["vehicle"])
        print("  readiness:", report["readiness"]["hazard_intelligence"], "missing:", report["readiness"]["missing"])
    sys.exit(0 if report["ok"] else 1)

if __name__ == "__main__":
    main()
