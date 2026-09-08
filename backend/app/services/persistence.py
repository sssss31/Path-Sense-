import logging,uuid
from geoalchemy2.elements import WKTElement
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AnalyzedRoute,Location,RouteAnalysis,WeatherSnapshot
from app.schemas.analysis import AnalysisRequest,AnalysisResponse
log=logging.getLogger("pathsense.persistence")
def point_wkt(lat,lng,spatial=True):
    wkt=f"POINT({lng} {lat})";return WKTElement(wkt,srid=4326) if spatial else wkt
def line_wkt(points,spatial=True):
    wkt="LINESTRING("+",".join(f"{p.lng} {p.lat}" for p in points)+")";return WKTElement(wkt,srid=4326) if spatial else wkt
class AnalysisPersistenceService:
    async def save(self,session:AsyncSession,request:AnalysisRequest,result:AnalysisResponse,user_id=None)->str:
        try:
            from app.database.types import is_spatial_dialect
            sp=is_spatial_dialect(session)
            source=Location(name=result.source.name,display_name=result.source.name,geometry=point_wkt(result.source.coordinate.lat,result.source.coordinate.lng,sp),bounding_box=None);destination=Location(name=result.destination.name,display_name=result.destination.name,geometry=point_wkt(result.destination.coordinate.lat,result.destination.coordinate.lng,sp),bounding_box=None);session.add_all([source,destination]);await session.flush()
            analysis=RouteAnalysis(id=uuid.UUID(result.analysis_id),user_id=user_id,source_id=source.id,destination_id=destination.id,cargo_type=request.cargo_type.value,requested_vehicle=request.vehicle_type,priority=request.priority,emergency_mode=request.emergency_mode,departure_time=request.departure_time,recommended_route_id=None,data_quality=result.data_quality,request_parameters=request.model_dump(mode="json"),response_snapshot=result.model_dump(mode="json"),status="completed");session.add(analysis);await session.flush();route_ids={}
            for rank,r in enumerate(result.routes,1):
                route=AnalyzedRoute(analysis_id=analysis.id,provider_route_id=r.id,name=r.name,geometry=line_wkt(r.geometry,sp),distance_km=r.distance_km,duration_minutes=r.duration_minutes,eta_minutes=r.eta_minutes,accessibility_score=r.accessibility.score,accessibility_status=r.accessibility.status,risk_score=r.risk.score,risk_level=r.risk.level,factors={"rank":rank,"scores":r.accessibility.factors,"weights":r.accessibility.factor_weights,"confidence":r.accessibility.confidence,"positive":r.accessibility.main_positive_factors,"negative":r.accessibility.main_negative_factors},warnings=r.risk.main_risks,terrain=r.terrain.model_dump(),recommended_vehicle=r.recommended_vehicle,is_recommended=r.recommended);session.add(route);await session.flush();route_ids[r.id]=route.id;session.add(WeatherSnapshot(analyzed_route_id=route.id,forecast_at=request.departure_time,normalized_data=r.weather.model_dump(),provider=result.data_quality.get("weather",{}).get("provider","unknown"),status=result.data_quality.get("weather",{}).get("status","unavailable")))
            analysis.recommended_route_id=route_ids.get(result.recommended_route_id);await session.commit()
            return "persisted"
        except Exception as exc:
            await session.rollback();log.warning("analysis_persistence_failed",extra={"analysis_id":result.analysis_id,"error_type":type(exc).__name__});return "failed"
