from sqlalchemy import func,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import HistoricalIncident,RiskZone
class SpatialRiskRepository:
    def __init__(self,session:AsyncSession):self.session=session
    async def zones_for_route(self,route_geometry,limit=100):
        intersection=func.ST_Intersection(RiskZone.geometry,route_geometry)
        q=select(RiskZone,func.ST_Length(func.Geography(intersection)).label("intersection_m")).where(func.ST_Intersects(RiskZone.geometry,route_geometry)).order_by(RiskZone.severity.desc()).limit(limit)
        return (await self.session.execute(q)).all()
    async def incidents_near_route(self,route_geometry,distance_m=2000,limit=200):
        q=select(HistoricalIncident).where(func.ST_DWithin(func.Geography(HistoricalIncident.geometry),func.Geography(route_geometry),distance_m)).order_by(HistoricalIncident.occurred_at.desc()).limit(limit)
        return list((await self.session.scalars(q)).all())
