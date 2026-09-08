"""Data-source transparency: per-analysis source panel, readiness and hazard dataset summaries.

Everything reported here comes from configuration, the dataset registry and
provider interfaces; nothing is inferred from the absence of data. A missing
feed is reported as ``unavailable`` so it can never read as "no hazard".
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.domain import COVERAGE_FULL, COVERAGE_NONE, COVERAGE_PARTIAL, COVERAGE_UNKNOWN, LAYER_TYPE_LABELS
from app.models import DatasetSource
from app.providers.current_hazards import current_hazard_provider, road_closure_provider
from app.providers.geospatial_layers.bhuvan_wms import external_layer_registry
from app.schemas.analysis import Coordinate, DataSource, HazardExposure
from app.services.coverage import calculate_dataset_route_coverage
from app.services.datasets import period_text

FAMILY_OF_LAYER = {"landslide_inventory": "landslide_inventory", "incidents": "landslide_inventory", "landslide_susceptibility": "landslide_susceptibility",
                   "flood_hazard": "flood_hazard", "flood_inundation": "flood_hazard", "hazard_zones": "hazard_zones"}

def mode_name() -> str:
    return "demo" if get_settings().use_mock_data else "live"

def provider_sources(simulated: bool, weather_updated: datetime | None = None, weather_status: str = "live", terrain_status: str = "estimated", weather_reason: str | None = None, terrain_reason: str | None = None) -> list[DataSource]:
    now = datetime.now(timezone.utc)
    if simulated:
        return [DataSource(key="routing", name="Routing", organization="PathSense demo", status="simulated", provenance="simulated", note="Deterministic demo routes"),
                DataSource(key="geocoding", name="Geocoding", organization="PathSense demo", status="simulated", provenance="simulated"),
                DataSource(key="weather", name="Weather", organization="PathSense demo", status="simulated", provenance="simulated", note="Pre-generated demo weather scenario"),
                DataSource(key="terrain", name="Terrain", organization="PathSense demo", status="simulated", provenance="simulated")]
    return [DataSource(key="routing", name="Routing", organization="OSRM (OpenStreetMap)", status="live", provenance="live", updated_at=now, attribution="© OpenStreetMap contributors"),
            DataSource(key="geocoding", name="Geocoding", organization="Nominatim (OpenStreetMap)", status="live", provenance="live", updated_at=now, attribution="© OpenStreetMap contributors"),
            DataSource(key="weather", name="Weather", organization="OpenWeather", status=weather_status, provenance=weather_status, updated_at=None if weather_status == "unavailable" else (weather_updated or now), note=weather_reason if weather_status == "unavailable" else "Sampled at five route points"),
            DataSource(key="terrain", name="Terrain", organization="Open-Elevation", status=terrain_status, provenance=terrain_status, note=terrain_reason if terrain_status == "unavailable" else "Elevation sampled; slope estimated")]

def dataset_sources_for_route(datasets: list[DatasetSource], points: list[Coordinate], exposure: HazardExposure | None) -> list[DataSource]:
    """One source row per hazard layer family, using registry facts and route coverage."""
    families: dict[str, list[DatasetSource]] = {}
    for d in datasets:
        families.setdefault(FAMILY_OF_LAYER.get(d.layer_type or "hazard_zones", "hazard_zones"), []).append(d)
    out = []
    for family, label in (("landslide_inventory", "Landslide Inventory"), ("landslide_susceptibility", "Landslide Susceptibility"), ("flood_hazard", "Flood Hazard"), ("hazard_zones", "Hazard Zones")):
        rows = families.get(family, [])
        if not rows:
            if family != "hazard_zones":
                out.append(DataSource(key=family, name=label, organization="—", status="unavailable", provenance="unavailable", coverage=COVERAGE_NONE, note="No dataset imported; exposure unknown, not zero"))
            continue
        coverages = [calculate_dataset_route_coverage(points, d) for d in rows] if points else []
        statuses = [c["status"] for c in coverages]
        coverage = COVERAGE_FULL if COVERAGE_FULL in statuses else COVERAGE_PARTIAL if COVERAGE_PARTIAL in statuses else COVERAGE_UNKNOWN if COVERAGE_UNKNOWN in statuses or not statuses else COVERAGE_NONE
        provenance = "simulated" if all(d.provenance_type == "simulated" for d in rows) else "historical" if any(d.provenance_type == "historical" for d in rows) else rows[0].provenance_type
        status = provenance if coverage in {COVERAGE_FULL, COVERAGE_UNKNOWN} else "partial" if coverage == COVERAGE_PARTIAL else "unavailable"
        periods = [period_text(d.period_start, d.period_end) for d in rows if d.period_start or d.period_end]
        out.append(DataSource(key=family, name=label, organization=", ".join(sorted({d.source_organization for d in rows})), status=status, provenance=provenance, coverage=coverage,
                              period=", ".join(p for p in periods if p) or None, updated_at=max((d.ingested_at for d in rows if d.ingested_at), default=None),
                              attribution="; ".join(sorted({d.attribution for d in rows if d.attribution})) or None,
                              note=f"{len(rows)} dataset(s): " + ", ".join(d.name for d in rows)))
    return out

def current_feed_sources() -> list[DataSource]:
    return [DataSource(key="road_closure", name="Road Closure", organization="—", status="unavailable", provenance="unavailable", note="No verified road-closure feed connected"),
            DataSource(key="current_flood", name="Current Flood Events", organization="—", status="unavailable", provenance="unavailable", note="No verified current flood-event feed connected")]

def database_target(session: AsyncSession | None) -> dict:
    """Dialect + host/database without credentials, so diagnostics show what was actually targeted."""
    if session is None:
        return {"dialect": "none", "target": None}
    try:
        url = session.get_bind().url
        return {"dialect": url.get_backend_name(), "target": f"{url.host or 'local'}:{url.port or ''}/{url.database or ''}" if url.get_backend_name() != "sqlite" else str(url.database)}
    except Exception:
        return {"dialect": "unknown", "target": None}

async def database_reachable(session: AsyncSession | None) -> bool:
    if session is None:
        return False
    from sqlalchemy import text
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        return False

async def imported_datasets(session: AsyncSession | None, include_simulated: bool) -> list[DatasetSource]:
    if session is None:
        return []
    try:
        if session.get_bind().dialect.name != "postgresql":
            return []
        q = select(DatasetSource).where(DatasetSource.status == "imported")
        if not include_simulated:
            q = q.where(DatasetSource.provenance_type != "simulated")
        return list((await session.scalars(q)).all())
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        return []

def hazard_dataset_summary(datasets: list[DatasetSource]) -> list[dict]:
    """Cheap registry-only summary for health/readiness (no GIS operations)."""
    return [{"slug": d.slug, "name": d.name, "layer_type": d.layer_type, "layer_label": LAYER_TYPE_LABELS.get(d.layer_type or "hazard_zones"), "provenance": d.provenance_type,
             "records": d.record_count, "coverage_area": d.coverage_area, "coverage_status": "declared" if d.coverage_bbox else "observed" if (d.metadata_json or {}).get("last_import", {}).get("coverage_bbox_observed") else "unknown",
             "period": period_text(d.period_start, d.period_end), "last_imported": d.ingested_at} for d in datasets]

async def readiness(session: AsyncSession | None) -> dict:
    settings = get_settings()
    simulated = settings.use_mock_data
    datasets = await imported_datasets(session, include_simulated=simulated)
    families = {FAMILY_OF_LAYER.get(d.layer_type or "hazard_zones", "hazard_zones") for d in datasets}
    authoritative = [d for d in datasets if d.provenance_type != "simulated"]
    missing = []
    if not simulated and not settings.openweather_api_key:
        missing.append("OpenWeather API key")
    if "landslide_inventory" not in families: missing.append("landslide inventory dataset")
    if "landslide_susceptibility" not in families: missing.append("landslide susceptibility dataset")
    if "flood_hazard" not in families: missing.append("flood hazard dataset (PostGIS); Bhuvan WMS provides remote inundation layers only")
    missing.append("current road closure provider")
    missing.append("current flood/landslide event feed")
    if simulated and not authoritative:
        hazard = "simulated"
    elif {"landslide_inventory", "landslide_susceptibility", "flood_hazard"} <= families:
        hazard = "full"
    elif families:
        hazard = "partial"
    else:
        hazard = "unavailable"
    target = database_target(session)
    reachable = await database_reachable(session)
    database = target["dialect"]
    if database == "postgresql" and not reachable:
        hazard = "unavailable"
        missing.insert(0, f"database unreachable at {target['target']}")
    return {"ready": reachable, "mode": mode_name(), "database": database, "database_target": target["target"], "database_reachable": reachable, "routing": "simulated" if simulated else "live", "geocoding": "simulated" if simulated else "live",
            "weather": "simulated" if simulated else ("live" if settings.openweather_api_key else "unavailable"), "terrain": "simulated" if simulated else "estimated",
            "hazard_intelligence": hazard, "hazard_datasets": hazard_dataset_summary(datasets), "external_layers": [l.id for p in external_layer_registry() for l in p.layers()],
            "current_hazards": "unavailable", "road_closures": "unavailable", "gemini": "configured" if settings.gemini_api_key else "unconfigured", "missing": missing,
            "checked_at": datetime.now(timezone.utc)}

async def current_feeds_status() -> dict:
    flood = await current_hazard_provider().get_active_flood_events()
    slides = await current_hazard_provider().get_active_landslide_events()
    closures = await road_closure_provider().get_road_closures()
    return {"flood_events": flood, "landslide_events": slides, "road_closures": closures}
