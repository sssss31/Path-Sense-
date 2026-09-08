import uuid
from datetime import datetime
from sqlalchemy import or_,select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.models import Delivery,Location,RouteAnalysis
class DeliveryRepository:
    def query(self,user_id):
        source=aliased(Location);destination=aliased(Location)
        return select(Delivery,source.name.label("source"),destination.name.label("destination"),RouteAnalysis.response_snapshot).join(source,Delivery.source_location_id==source.id).join(destination,Delivery.destination_location_id==destination.id).outerjoin(RouteAnalysis,Delivery.analysis_id==RouteAnalysis.id).where(Delivery.user_id==user_id)
    async def list(self,session,user_id,page,page_size,status=None,priority=None,cargo_type=None,date_from=None,date_to=None,search=None,sort="desc"):
        q=self.query(user_id)
        if status:q=q.where(Delivery.status==status)
        if priority:q=q.where(Delivery.priority==priority)
        if cargo_type:q=q.where(Delivery.cargo_type==cargo_type)
        if date_from:q=q.where(Delivery.created_at>=date_from)
        if date_to:q=q.where(Delivery.created_at<=date_to)
        if search:q=q.where(or_(Delivery.identifier.ilike(f"%{search}%"),Location.name.ilike(f"%{search}%")))
        order=Delivery.created_at.asc() if sort=="asc" else Delivery.created_at.desc();return (await session.execute(q.order_by(order).offset((page-1)*page_size).limit(page_size))).all()
    def filtered(self,user_id,status=None,priority=None,cargo_type=None,date_from=None,date_to=None,search=None):
        q=self.query(user_id)
        if status:q=q.where(Delivery.status==status)
        if priority:q=q.where(Delivery.priority==priority)
        if cargo_type:q=q.where(Delivery.cargo_type==cargo_type)
        if date_from:q=q.where(Delivery.created_at>=date_from)
        if date_to:q=q.where(Delivery.created_at<=date_to)
        if search:q=q.where(or_(Delivery.identifier.ilike(f"%{search}%"),Location.name.ilike(f"%{search}%")))
        return q
    async def count(self,session,user_id,status=None,priority=None,cargo_type=None,date_from=None,date_to=None,search=None):
        from sqlalchemy import func
        q=self.filtered(user_id,status,priority,cargo_type,date_from,date_to,search)
        return int(await session.scalar(select(func.count()).select_from(q.subquery())) or 0)
    async def get(self,session,user_id,delivery_id):return (await session.execute(self.query(user_id).where(Delivery.id==delivery_id))).first()
    async def get_analysis(self,session,user_id,analysis_id):return await session.scalar(select(RouteAnalysis).where(RouteAnalysis.id==analysis_id,RouteAnalysis.user_id==user_id))
