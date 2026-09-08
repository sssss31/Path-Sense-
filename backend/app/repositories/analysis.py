import uuid
from sqlalchemy import delete,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RouteAnalysis
class AnalysisRepository:
    def __init__(self,session:AsyncSession):self.session=session
    async def list(self,user_id=None,limit=50):
        q=select(RouteAnalysis).order_by(RouteAnalysis.created_at.desc()).limit(limit)
        if user_id:q=q.where(RouteAnalysis.user_id==user_id)
        return list((await self.session.scalars(q)).all())
    async def get(self,analysis_id:uuid.UUID):return await self.session.get(RouteAnalysis,analysis_id)
    async def add(self,analysis):self.session.add(analysis);await self.session.flush();return analysis
    async def delete(self,analysis_id):await self.session.execute(delete(RouteAnalysis).where(RouteAnalysis.id==analysis_id));await self.session.commit()
