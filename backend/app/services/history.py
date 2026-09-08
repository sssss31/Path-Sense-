import uuid
from datetime import datetime
from sqlalchemy import func,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RouteAnalysis
class HistoryService:
    async def list(self,session:AsyncSession,user_id:uuid.UUID,page=1,page_size=20,risk_level=None,cargo_type=None,date_from:datetime|None=None,date_to:datetime|None=None,sort="desc"):
        q=select(RouteAnalysis).where(RouteAnalysis.user_id==user_id)
        if cargo_type:q=q.where(RouteAnalysis.cargo_type==cargo_type)
        if date_from:q=q.where(RouteAnalysis.created_at>=date_from)
        if date_to:q=q.where(RouteAnalysis.created_at<=date_to)
        if risk_level:q=q.where(RouteAnalysis.response_snapshot["routes"].contains([{"risk":{"level":risk_level}}]))
        total=await session.scalar(select(func.count()).select_from(q.subquery()));order=RouteAnalysis.created_at.asc() if sort=="asc" else RouteAnalysis.created_at.desc();rows=list((await session.scalars(q.order_by(order).offset((page-1)*page_size).limit(page_size))).all())
        return {"items":[self.summary(x) for x in rows],"page":page,"page_size":page_size,"total":total or 0}
    async def get(self,session,user_id,analysis_id):return await session.scalar(select(RouteAnalysis).where(RouteAnalysis.id==analysis_id,RouteAnalysis.user_id==user_id))
    async def delete(self,session,user_id,analysis_id):
        row=await self.get(session,user_id,analysis_id)
        if not row:return False
        await session.delete(row);await session.commit();return True
    def summary(self,row):
        s=row.response_snapshot;best=next((x for x in s.get("routes",[]) if x.get("recommended")),{})
        return {"analysis_id":str(row.id),"source":s.get("source",{}).get("name"),"destination":s.get("destination",{}).get("name"),"cargo_type":row.cargo_type,"accessibility":best.get("accessibility",{}).get("score"),"risk_level":best.get("risk",{}).get("level"),"recommended_route":best.get("name"),"created_at":row.created_at}
