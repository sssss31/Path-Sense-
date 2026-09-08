import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.assistant_service import AssistantService
from app.api.auth import current_user, optional_user
from app.core.config import get_settings
from app.core.domain import DELIVERY_PRIORITIES, DELIVERY_STATUSES, DELIVERY_TRANSITIONS, FLOOD_LAYER_WORDING, LAYER_TYPE_LABELS, SENSITIVE_DELIVERY_STATUSES, SUSCEPTIBILITY_LABELS, USER_REPORT_LABEL, USER_REPORT_VERIFICATION, hazard_label
from app.providers.geospatial_layers.bhuvan_wms import external_layer_registry
from app.services.sources import current_feeds_status, hazard_dataset_summary, imported_datasets, readiness
from app.database.session import get_session
from app.models import AnalyzedRoute, DatasetSource, Delivery, HistoricalIncident, RiskZone, RouteAnalysis, User, UserReport
from app.repositories.delivery import DeliveryRepository
from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.delivery import DeliveryCreate, DeliveryDetailResponse, DeliveryResponse, DeliveryUpdate, TransitionRules
from app.services.analysis import RouteAnalysisService
from app.services.datasets import DatasetRegistryService, serialize_dataset
from app.services.delivery import DeliveryService, allowed_transitions, recommended_route, serialize, serialize_detail
from app.services.history import HistoryService
from app.services.persistence import AnalysisPersistenceService
from app.services.reports import ReportsService
from app.services.spatial_risk import SpatialRiskService

router = APIRouter()

def analysis_service():
    return RouteAnalysisService()

# --- Route analysis ---------------------------------------------------------
@router.post("/analysis/route", response_model=AnalysisResponse)
async def analyze_route(payload: AnalysisRequest, service: RouteAnalysisService = Depends(analysis_service), session: AsyncSession = Depends(get_session), user: User | None = Depends(optional_user)):
    try:
        result = await service.analyze(payload, session)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=503, detail="Routing or provider services are temporarily unavailable")
    result.persistence_status = await AnalysisPersistenceService().save(session, payload, result, user.id if user else None)
    return result

@router.get("/analysis")
async def analysis_history(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), risk_level: str | None = None, cargo_type: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None, sort: str = "desc", session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    return await HistoryService().list(session, user.id, page, page_size, risk_level, cargo_type, date_from, date_to, sort)

@router.get("/analysis/{analysis_id}")
async def historical_analysis(analysis_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    row = await HistoryService().get(session, user.id, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {**row.response_snapshot, "persistence_status": "persisted", "historical_snapshot": True, "snapshot_created_at": row.created_at}

@router.get("/analysis/{analysis_id}/map")
async def analysis_map(analysis_id: uuid.UUID, alternatives: bool = False, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    """Lightweight map payload: source/destination + recommended geometry (+ alternatives on request). No providers are re-run."""
    row = await HistoryService().get(session, user.id, analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found")
    snapshot = row.response_snapshot or {}
    best = recommended_route(snapshot)
    def slim(r):
        return {"id": r.get("id"), "name": r.get("name"), "geometry": r.get("geometry", []), "accessibility": (r.get("accessibility") or {}).get("score"), "risk_level": (r.get("risk") or {}).get("level"), "distance_km": r.get("distance_km"), "eta_minutes": r.get("eta_minutes"), "recommended": bool(r.get("recommended"))}
    return {"analysis_id": str(row.id), "created_at": row.created_at, "source": snapshot.get("source"), "destination": snapshot.get("destination"), "recommended_route": slim(best) if best else None,
            "alternatives": [slim(r) for r in snapshot.get("routes", []) if not r.get("recommended")] if alternatives else [], "hazards": best.get("hazards") if best else None, "data_quality": snapshot.get("data_quality", {})}

@router.delete("/analysis/{analysis_id}", status_code=204)
async def delete_analysis(analysis_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    if not await HistoryService().delete(session, user.id, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found")

@router.get("/analysis/{analysis_id}/spatial-risk-summary")
async def spatial_risk_summary(analysis_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    result = await SpatialRiskService().summary(session, user.id, analysis_id)
    if not result:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return result

# --- Dashboard & reports -----------------------------------------------------
@router.get("/dashboard/summary")
async def dashboard_summary(session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    owned = RouteAnalysis.user_id == user.id
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    total = await session.scalar(select(func.count(RouteAnalysis.id)).where(owned))
    last7 = await session.scalar(select(func.count(RouteAnalysis.id)).where(owned, RouteAnalysis.created_at >= week_ago))
    avg = await session.scalar(select(func.avg(AnalyzedRoute.accessibility_score)).join(RouteAnalysis).where(owned, AnalyzedRoute.is_recommended))
    high = await session.scalar(select(func.count(AnalyzedRoute.id)).join(RouteAnalysis).where(owned, AnalyzedRoute.is_recommended, AnalyzedRoute.risk_level == "high"))
    active = await session.scalar(select(func.count(Delivery.id)).where(Delivery.user_id == user.id, Delivery.status.in_(["planned", "in_transit", "delayed"])))
    recent = (await HistoryService().list(session, user.id, 1, 5))["items"]
    reports = ReportsService()
    start, end = datetime.now(timezone.utc) - timedelta(days=14), datetime.now(timezone.utc)
    active_rows = await DeliveryRepository().list(session, user.id, 1, 5, None, None, None, None, None, None, "desc")
    return {
        "metrics": {"total_analyses": total or 0, "average_accessibility": round(float(avg or 0), 1), "high_risk": high or 0, "active_deliveries": active or 0, "last_7_days": last7 or 0},
        "recent_analyses": recent,
        "risk_distribution": [{"level": x["name"], "count": x["value"]} for x in await reports.risk_distribution(session, user.id, datetime(2000, 1, 1, tzinfo=timezone.utc), end)],
        "accessibility_trend": await reports.accessibility_trend(session, user.id, start, end),
        "delivery_status": await reports.delivery_status(session, user.id, datetime(2000, 1, 1, tzinfo=timezone.utc), end),
        "active_deliveries": [serialize(x) for x in active_rows if x[0].status in {"planned", "in_transit", "delayed"}],
        "recent_high_risk": [x for x in recent if x["risk_level"] == "high"],
    }

@router.get("/reports/summary")
async def reports_summary(range: str | None = Query(None, alias="range"), date_from: datetime | None = None, date_to: datetime | None = None, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    return await ReportsService().summary(session, user.id, range, date_from, date_to)

# --- Dataset registry --------------------------------------------------------
@router.get("/datasets")
async def datasets(session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    rows = await DatasetRegistryService().list(session)
    return {"items": [serialize_dataset(x) for x in rows], "total": len(rows)}

@router.get("/datasets/{dataset_id}")
async def dataset_detail(dataset_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    row = await DatasetRegistryService().get(session, dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return serialize_dataset(row)

# --- Viewport layers ---------------------------------------------------------
def _provenance_filter(model, settings):
    if settings.use_mock_data:
        return None
    simulated = select(DatasetSource.id).where(DatasetSource.provenance_type == "simulated")
    return or_(model.dataset_source_id.is_(None), model.dataset_source_id.not_in(simulated))

def _dataset_filter(model, dataset: str | None):
    """`dataset` = registry slug, or "simulated"/"authoritative" pseudo-filters."""
    if not dataset or dataset == "all":
        return None
    if dataset == "simulated":
        return model.dataset_source_id.in_(select(DatasetSource.id).where(DatasetSource.provenance_type == "simulated"))
    if dataset == "authoritative":
        return model.dataset_source_id.in_(select(DatasetSource.id).where(DatasetSource.provenance_type != "simulated"))
    return model.dataset_source_id.in_(select(DatasetSource.id).where(DatasetSource.slug == dataset))

def _zone_label(category: str, provenance: str, layer_type: str | None, severity: int) -> str:
    if layer_type == "landslide_susceptibility":
        return f"Landslide Susceptibility · {SUSCEPTIBILITY_LABELS.get(severity, 'unknown').title()}" + (" (simulated)" if provenance == "simulated" else "")
    if layer_type in FLOOD_LAYER_WORDING and provenance != "simulated":
        return FLOOD_LAYER_WORDING[layer_type] if provenance == "historical" or layer_type == "current_events" else "Flood-Prone Area"
    return hazard_label(category, provenance)

@router.get("/risk-zones")
async def risk_zones(min_lat: float = Query(..., ge=-90, le=90), min_lon: float = Query(..., ge=-180, le=180), max_lat: float = Query(..., ge=-90, le=90), max_lon: float = Query(..., ge=-180, le=180), category: str | None = None, severity: int | None = Query(None, ge=1, le=5), dataset: str | None = None, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    q = select(RiskZone.id, RiskZone.category, RiskZone.severity, RiskZone.status, RiskZone.source, func.ST_AsGeoJSON(func.ST_SimplifyPreserveTopology(RiskZone.geometry, .0001)), DatasetSource.provenance_type, DatasetSource.name, DatasetSource.layer_type, DatasetSource.slug, DatasetSource.attribution, RiskZone.metadata_json).outerjoin(DatasetSource, RiskZone.dataset_source_id == DatasetSource.id).where(func.ST_Intersects(RiskZone.geometry, envelope)).limit(500)
    if category: q = q.where(RiskZone.category == category)
    if severity: q = q.where(RiskZone.severity >= severity)
    if (flt := _provenance_filter(RiskZone, get_settings())) is not None: q = q.where(flt)
    if (dflt := _dataset_filter(RiskZone, dataset)) is not None: q = q.where(dflt)
    try:
        rows = (await session.execute(q)).all()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Spatial database unavailable")
    features = []
    for r in rows:
        provenance = r[6] or ("live" if r.status == "live" else "historical")
        meta = r[11] or {}
        features.append({"type": "Feature", "id": str(r.id), "geometry": json.loads(r[5]), "properties": {"category": r.category, "severity": r.severity, "status": r.status, "source": r.source, "provenance": provenance, "dataset": r[7], "dataset_slug": r[9],
                         "layer_type": r[8] or "hazard_zones", "layer_label": LAYER_TYPE_LABELS.get(r[8] or "hazard_zones"), "label": _zone_label(r.category, provenance, r[8], r.severity), "attribution": r[10],
                         "original_class": meta.get("original_severity"), "external_id": meta.get("external_id"), "event_date": meta.get("event_date")}})
    return {"type": "FeatureCollection", "features": features}

@router.get("/incidents")
async def incidents(min_lat: float = Query(..., ge=-90, le=90), min_lon: float = Query(..., ge=-180, le=180), max_lat: float = Query(..., ge=-90, le=90), max_lon: float = Query(..., ge=-180, le=180), category: str | None = None, severity: int | None = Query(None, ge=1, le=5), dataset: str | None = None, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    q = select(HistoricalIncident.id, HistoricalIncident.category, HistoricalIncident.severity, HistoricalIncident.occurred_at, HistoricalIncident.source, func.ST_AsGeoJSON(HistoricalIncident.geometry), DatasetSource.provenance_type, DatasetSource.name, DatasetSource.layer_type, DatasetSource.slug, DatasetSource.attribution, HistoricalIncident.description, HistoricalIncident.metadata_json).outerjoin(DatasetSource, HistoricalIncident.dataset_source_id == DatasetSource.id).where(func.ST_Intersects(HistoricalIncident.geometry, envelope)).limit(500)
    if category: q = q.where(HistoricalIncident.category == category)
    if severity: q = q.where(HistoricalIncident.severity >= severity)
    if (flt := _provenance_filter(HistoricalIncident, get_settings())) is not None: q = q.where(flt)
    if (dflt := _dataset_filter(HistoricalIncident, dataset)) is not None: q = q.where(dflt)
    try:
        rows = (await session.execute(q)).all()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Spatial database unavailable")
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": str(r.id), "geometry": json.loads(r[5]), "properties": {"category": r.category, "severity": r.severity, "occurred_at": r.occurred_at, "source": r.source, "status": "historical", "provenance": r[6] or "historical", "dataset": r[7], "dataset_slug": r[9],
                     "layer_type": r[8] or "incidents", "layer_label": LAYER_TYPE_LABELS.get(r[8] or "incidents"), "attribution": r[10], "description": r[11], "external_id": (r[12] or {}).get("external_id"), "severity_known": (r[12] or {}).get("original_severity") is not None}} for r in rows]}

# --- External map layers, readiness, user reports ---------------------------------
@router.get("/map-layers")
async def map_layers(user: User = Depends(current_user)):
    """Remote official layers (WMS) the client may render directly. URLs come only from trusted configuration."""
    layers = [l.to_dict() for p in external_layer_registry() for l in p.layers()]
    return {"items": layers, "total": len(layers), "note": "Remote layers are rendered from official services; historical inundation is never a current flood alert."}

@router.get("/system/readiness")
async def system_readiness(session: AsyncSession = Depends(get_session)):
    return await readiness(session)

@router.get("/system/current-hazards")
async def system_current_hazards(user: User = Depends(current_user)):
    return await current_feeds_status()

@router.post("/user-reports", status_code=201)
async def create_user_report(payload: dict, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    """MVP road-issue report. Always stored as unverified; never treated as a confirmed closure."""
    try:
        lat, lon = float(payload["lat"]), float(payload["lon"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=422, detail="lat and lon are required")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=422, detail="coordinates out of range")
    category = str(payload.get("category") or "road_issue")[:40]
    row = UserReport(user_id=user.id, category=category, status="unverified", geometry=func.ST_SetSRID(func.ST_Point(lon, lat), 4326), description=str(payload.get("description") or "")[:1000],
                     metadata_json={"source": "user_report", "reported_at": datetime.now(timezone.utc).isoformat(), "verification_status": "unverified", "route_or_location": payload.get("location")})
    session.add(row); await session.commit(); await session.refresh(row)
    return {"id": str(row.id), "category": row.category, "verification_status": "unverified", "label": USER_REPORT_LABEL["unverified"], "reported_at": row.created_at}

@router.get("/user-reports")
async def list_user_reports(min_lat: float = Query(..., ge=-90, le=90), min_lon: float = Query(..., ge=-180, le=180), max_lat: float = Query(..., ge=-90, le=90), max_lon: float = Query(..., ge=-180, le=180), session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
    try:
        rows = (await session.execute(select(UserReport.id, UserReport.category, UserReport.status, UserReport.description, UserReport.created_at, func.ST_AsGeoJSON(UserReport.geometry)).where(func.ST_Intersects(UserReport.geometry, envelope), UserReport.status.in_(USER_REPORT_VERIFICATION)).limit(300))).all()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Spatial database unavailable")
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "id": str(r.id), "geometry": json.loads(r[5]), "properties": {"category": r.category, "verification_status": r.status, "label": USER_REPORT_LABEL.get(r.status, "Reported Road Issue"), "description": r.description, "reported_at": r.created_at, "source": "user_report"}} for r in rows]}

# --- Live workspace endpoints (weather widget, notifications, config) ------------
@router.get("/system/weather")
async def system_weather(lat: float = Query(25.5788, ge=-90, le=90), lon: float = Query(91.8933, ge=-180, le=180), name: str | None = None, user: User | None = Depends(optional_user)):
    """Current weather at a point via the configured provider (OpenWeather live, deterministic demo otherwise). Cached 15 min."""
    from app.services.analysis import RouteAnalysisService
    from app.schemas.analysis import Coordinate
    service = RouteAnalysisService()
    point = Coordinate(lat=lat, lng=lon)
    try:
        weather = await service.weather.weather_for_route({"geometry": [point, point], "variant": 2})
        return {"location": name or f"{lat:.2f}, {lon:.2f}", "temperature_c": weather.temperature_c, "condition": weather.condition, "rainfall_mm": weather.rainfall_mm, "visibility_km": weather.visibility_km,
                "status": weather.data_status, "provider": "demo" if get_settings().use_mock_data else "openweather", "updated_at": datetime.now(timezone.utc)}
    except Exception as exc:
        return {"location": name or f"{lat:.2f}, {lon:.2f}", "status": "unavailable", "provider": "demo" if get_settings().use_mock_data else "openweather", "detail": type(exc).__name__, "updated_at": datetime.now(timezone.utc)}

@router.get("/geocode/suggest")
async def geocode_suggest(q: str = Query(..., min_length=1, max_length=120), user: User | None = Depends(optional_user)):
    """Place suggestions for the analysis form (Nominatim with NE-India bias, cached; demo names in demo mode)."""
    from app.services.analysis import RouteAnalysisService
    try:
        return {"items": await RouteAnalysisService().geocoder.suggest(q), "provider": "demo" if get_settings().use_mock_data else "nominatim"}
    except Exception as exc:
        return {"items": [], "provider": "demo" if get_settings().use_mock_data else "nominatim", "detail": type(exc).__name__}

@router.get("/notifications")
async def notifications(session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    """Operational alerts derived from persisted records: delayed deliveries, imminent departures, recent high-risk analyses."""
    from app.core.domain import NOTIFICATION_RULES as R
    now = datetime.now(timezone.utc)
    aware = lambda v: (v.replace(tzinfo=timezone.utc) if isinstance(v, datetime) and v.tzinfo is None else v)  # SQLite returns naive datetimes
    items = []
    rows = await DeliveryRepository().list(session, user.id, 1, 50, None, None, None, None, None, None, "desc")
    for record in rows:
        d = {k: aware(v) for k, v in serialize(record).items()}
        if d["status"] == "delayed":
            items.append({"kind": "delivery_delayed", "severity": "high", "title": f"{d['identifier']} is delayed", "detail": f"{d['source']} → {d['destination']}", "href": f"/deliveries/{d['id']}", "at": d["created_at"]})
        elif d["status"] == "planned" and d["planned_departure"] and now <= d["planned_departure"] <= now + timedelta(hours=R["departing_within_hours"]):
            items.append({"kind": "departure_due", "severity": "moderate", "title": f"{d['identifier']} departs within {R['departing_within_hours']} h", "detail": f"{d['source']} → {d['destination']} · {d['vehicle']}", "href": f"/deliveries/{d['id']}", "at": d["planned_departure"]})
        elif d["status"] == "planned" and d["planned_departure"] and d["planned_departure"] < now:
            items.append({"kind": "departure_overdue", "severity": "moderate", "title": f"{d['identifier']} planned departure has passed", "detail": "Still marked planned", "href": f"/deliveries/{d['id']}", "at": d["planned_departure"]})
    recent = (await HistoryService().list(session, user.id, 1, 20, date_from=now - timedelta(days=R["recent_high_risk_days"])))["items"]
    for a in recent:
        if a["risk_level"] == "high":
            items.append({"kind": "high_risk_analysis", "severity": "high", "title": f"High-risk corridor: {a['source']} → {a['destination']}", "detail": f"Accessibility {a['accessibility']} · {a['recommended_route']}", "href": f"/risk-map?analysis={a['analysis_id']}", "at": a["created_at"]})
    items.sort(key=lambda x: aware(x["at"]) or now, reverse=True)
    return {"items": items[:R["max_items"]], "count": len(items[:R["max_items"]]), "generated_at": now}

@router.get("/system/config")
async def system_config(user: User = Depends(current_user)):
    """Editable rule tables as the backend actually uses them (never duplicated in the frontend)."""
    from app.core import domain
    s = get_settings()
    return {"mode": "demo" if s.use_mock_data else "live", "scoring_weights": s.scoring_weights, "risk_contributions": domain.RISK_CONTRIBUTIONS, "confidence_factors": domain.CONFIDENCE_FACTORS,
            "confidence_provenance_base": domain.CONFIDENCE_PROVENANCE_BASE, "coverage_thresholds": {"full": domain.COVERAGE_FULL_THRESHOLD, "partial": domain.COVERAGE_PARTIAL_THRESHOLD},
            "susceptibility_mapping": domain.SUSCEPTIBILITY_MAPPING, "delivery_transitions": domain.DELIVERY_TRANSITIONS, "vehicle_profiles": domain.VEHICLE_PROFILES, "report_ranges": domain.REPORT_RANGES,
            "spatial": {"incident_buffer_m": domain.INCIDENT_BUFFER_METRES, "hazard_near_m": domain.HAZARD_NEAR_METRES}}

# --- System health -----------------------------------------------------------
@router.get("/system/health")
async def health(session: AsyncSession = Depends(get_session)):
    """Provider status plus a cheap registry-only hazard dataset summary (no GIS operations)."""
    s = get_settings()
    simulated = s.use_mock_data
    database, postgis = "unavailable", "unavailable"
    try:
        await session.execute(text("SELECT 1"))
        database = "online"
        if session.get_bind().dialect.name == "postgresql":
            postgis = "online" if (await session.execute(text("SELECT count(*) FROM pg_extension WHERE extname='postgis'"))).scalar() else "not_installed"
        else:
            postgis = "not_applicable"
    except Exception:
        await session.rollback()
    redis_status = "not_configured"
    if s.redis_url:
        try:
            from app.services.cache import get_cache
            cache = get_cache(); await cache.set("health:ping", 1, 30); redis_status = "healthy" if await cache.get("health:ping") else "degraded"
        except Exception:
            redis_status = "unavailable"
    datasets = await imported_datasets(session, include_simulated=True)
    external = [await p.health() for p in external_layer_registry()]
    providers = [
        {"name": "Routing", "provider": "demo" if simulated else "OSRM", "status": "healthy", "mode": "simulated" if simulated else "live"},
        {"name": "Geocoding", "provider": "demo" if simulated else "Nominatim", "status": "healthy", "mode": "simulated" if simulated else "live"},
        {"name": "Weather", "provider": "demo" if simulated else "OpenWeather", "status": "healthy" if simulated or s.openweather_api_key else "not_configured", "mode": "simulated" if simulated else "live"},
        {"name": "Terrain", "provider": "demo" if simulated else "Open Elevation", "status": "healthy", "mode": "simulated" if simulated else "estimated"},
        {"name": "Gemini", "provider": s.gemini_model, "status": "configured" if s.gemini_api_key else "not_configured", "mode": "live" if s.gemini_api_key else "deterministic-fallback"},
        {"name": "Cache", "provider": "Redis" if s.redis_url else "memory", "status": redis_status if s.redis_url else "healthy", "mode": "live" if s.redis_url else "fallback"},
        {"name": "External flood WMS", "provider": "NRSC/ISRO Bhuvan", "status": external[0]["status"] if external else "disabled", "mode": "historical"},
        {"name": "Current hazard feeds", "provider": "none", "status": "unavailable", "mode": "unavailable"},
        {"name": "Road closures", "provider": "none", "status": "unavailable", "mode": "unavailable"},
        {"name": "Database", "provider": session.get_bind().dialect.name, "status": database, "mode": "live"},
        {"name": "PostGIS", "provider": "postgis", "status": postgis, "mode": "live"},
    ]
    return {"status": "healthy" if database == "online" else "degraded", "mode": "development-mock" if simulated else "live", "providers": providers,
            "services": {p["name"].lower(): p["status"] for p in providers},
            "hazard_datasets": {"available": hazard_dataset_summary(datasets), "authoritative": sum(1 for d in datasets if d.provenance_type != "simulated"), "simulated": sum(1 for d in datasets if d.provenance_type == "simulated"),
                                "coverage_status": "declared" if any(d.coverage_bbox for d in datasets) else "unknown"},
            "external_layers": external}

# --- Deliveries --------------------------------------------------------------
@router.get("/deliveries/transitions", response_model=TransitionRules)
async def delivery_transitions(user: User = Depends(current_user)):
    return TransitionRules(statuses=DELIVERY_STATUSES, transitions=DELIVERY_TRANSITIONS, sensitive=SENSITIVE_DELIVERY_STATUSES, priorities=DELIVERY_PRIORITIES)

@router.get("/deliveries")
async def deliveries(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status: str | None = None, priority: str | None = None, cargo_type: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None, search: str | None = None, sort: str = "desc", session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    rows = await DeliveryRepository().list(session, user.id, page, page_size, status, priority, cargo_type, date_from, date_to, search, sort)
    total = await DeliveryRepository().count(session, user.id, status, priority, cargo_type, date_from, date_to, search)
    return {"items": [serialize(x) for x in rows], "page": page, "page_size": page_size, "total": total}

@router.post("/deliveries", status_code=201, response_model=DeliveryResponse)
async def create_delivery(data: DeliveryCreate, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    try:
        row = await DeliveryService().create(session, user.id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found or not owned by you")
    return serialize(await DeliveryRepository().get(session, user.id, row.id))

async def _detail(session, user, delivery_id):
    record = await DeliveryRepository().get(session, user.id, delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail="Delivery not found")
    analysis_id = record[0].analysis_id
    # Spatial summary first: a failed spatial query rolls back and expires loaded rows, so re-fetch afterwards.
    summary = await SpatialRiskService().summary(session, user.id, analysis_id) if analysis_id else None
    record = await DeliveryRepository().get(session, user.id, delivery_id)
    analysis = await session.get(RouteAnalysis, analysis_id) if analysis_id else None
    return serialize_detail(record, analysis, summary)

@router.get("/deliveries/{delivery_id}", response_model=DeliveryDetailResponse)
async def delivery_detail(delivery_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    return await _detail(session, user, delivery_id)

@router.get("/deliveries/{delivery_id}/transitions")
async def delivery_allowed_transitions(delivery_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    record = await DeliveryRepository().get(session, user.id, delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return {"status": record[0].status, "allowed_transitions": allowed_transitions(record[0].status), "sensitive": SENSITIVE_DELIVERY_STATUSES}

@router.patch("/deliveries/{delivery_id}", response_model=DeliveryDetailResponse)
async def update_delivery(delivery_id: uuid.UUID, data: DeliveryUpdate, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    record = await DeliveryRepository().get(session, user.id, delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail="Delivery not found")
    eta_minutes = recommended_route(record[3]).get("eta_minutes")
    try:
        await DeliveryService().update(session, record[0], data, eta_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return await _detail(session, user, delivery_id)

@router.delete("/deliveries/{delivery_id}", status_code=204)
async def delete_delivery(delivery_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    record = await DeliveryRepository().get(session, user.id, delivery_id)
    if not record:
        raise HTTPException(status_code=404, detail="Delivery not found")
    await session.delete(record[0])
    await session.commit()

@router.post("/deliveries/{delivery_id}/explain")
async def explain_delivery(delivery_id: uuid.UUID, payload: dict | None = None, session: AsyncSession = Depends(get_session), user: User = Depends(current_user)):
    """Assistant explanation from a controlled, server-built delivery context."""
    detail = await _detail(session, user, delivery_id)
    return await AssistantService().explain_delivery((payload or {}).get("message") or "Explain this delivery", json.loads(json.dumps(detail, default=str)))

# --- Assistant ---------------------------------------------------------------
@router.post("/assistant/chat")
async def assistant(payload: dict):
    return await AssistantService().answer(payload.get("message", "Explain this analysis"), payload.get("context", {}))
