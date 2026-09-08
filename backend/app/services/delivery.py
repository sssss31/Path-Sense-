"""Delivery lifecycle service.

Transition rules come from app.core.domain (single editable source of truth).
Status changes append a lightweight event to `status_history`; no event
sourcing beyond that.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.core.domain import DELIVERY_TRANSITIONS, SENSITIVE_DELIVERY_STATUSES
from app.models import Delivery
from app.repositories.delivery import DeliveryRepository
from app.schemas.delivery import DeliveryCreate, DeliveryUpdate

TRANSITIONS = {k: set(v) for k, v in DELIVERY_TRANSITIONS.items()}

def allowed_transitions(status: str) -> list[str]:
    return list(DELIVERY_TRANSITIONS.get(status, []))

def recommended_route(snapshot: dict | None) -> dict:
    routes = (snapshot or {}).get("routes", [])
    return next((r for r in routes if r.get("recommended")), routes[0] if routes else {})

class DeliveryService:
    def __init__(self):
        self.repo = DeliveryRepository()

    async def create(self, session, user_id, data: DeliveryCreate):
        analysis = await self.repo.get_analysis(session, user_id, data.analysis_id)
        if not analysis:
            return None
        best = recommended_route(analysis.response_snapshot)
        if not best:
            raise ValueError("Analysis has no route to dispatch")
        departure = data.planned_departure or analysis.departure_time
        now = datetime.now(timezone.utc)
        row = Delivery(
            identifier=f"DLV-{uuid.uuid4().hex[:8].upper()}", user_id=user_id, analysis_id=analysis.id,
            source_location_id=analysis.source_id, destination_location_id=analysis.destination_id, cargo_type=analysis.cargo_type,
            vehicle=data.vehicle or best.get("recommended_vehicle") or analysis.requested_vehicle, status="planned",
            priority=data.priority or analysis.priority, planned_departure=departure,
            eta=departure + timedelta(minutes=int(best.get("eta_minutes", 0))) if departure else None, actual_arrival=None, notes=data.notes,
            status_history=[{"from_status": None, "to_status": "planned", "note": "Created from route analysis", "at": now.isoformat()}],
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def update(self, session, row: Delivery, data: DeliveryUpdate, eta_minutes: int | None = None):
        if data.status and data.status != row.status:
            if data.status not in TRANSITIONS.get(row.status, set()):
                raise ValueError(f"Invalid transition: {row.status} → {data.status}")
            previous = row.status
            row.status = data.status
            history = list(row.status_history or [])
            history.append({"from_status": previous, "to_status": data.status, "note": data.status_note, "at": datetime.now(timezone.utc).isoformat()})
            row.status_history = history
            if data.status == "completed" and data.actual_arrival is None and row.actual_arrival is None:
                row.actual_arrival = datetime.now(timezone.utc)
        elif data.status and data.status_note:
            raise ValueError(f"Delivery is already {row.status}")
        for field in ["planned_departure", "actual_arrival", "notes"]:
            if (value := getattr(data, field)) is not None:
                setattr(row, field, value)
        if data.planned_departure is not None and eta_minutes:
            row.eta = data.planned_departure + timedelta(minutes=int(eta_minutes))
        await session.commit()
        return row

def serialize(record):
    row, source, destination, snapshot = record
    best = recommended_route(snapshot)
    return {
        "id": row.id, "identifier": row.identifier, "analysis_id": row.analysis_id, "source": source, "destination": destination,
        "cargo_type": row.cargo_type, "vehicle": row.vehicle, "priority": row.priority, "status": row.status,
        "planned_departure": row.planned_departure, "estimated_arrival": row.eta, "actual_arrival": row.actual_arrival, "notes": row.notes,
        "accessibility": best.get("accessibility", {}).get("score"), "risk_level": best.get("risk", {}).get("level"),
        "allowed_transitions": allowed_transitions(row.status), "created_at": row.created_at,
    }

def serialize_detail(record, analysis_row=None, hazard_summary: dict | None = None):
    """Detail payload: everything the delivery page needs without re-running providers."""
    row, source, destination, snapshot = record
    base = serialize(record)
    best = recommended_route(snapshot)
    snapshot = snapshot or {}
    hazards = best.get("hazards") or None
    if hazard_summary and hazard_summary.get("hazard_status") not in {None, "unavailable"}:
        hazards = {**(hazards or {}), "summary": hazard_summary}
    elif hazard_summary:
        hazards = {**(hazards or {"status": "unavailable"}), "summary": hazard_summary}
    return {
        **base,
        "updated_at": row.updated_at,
        "status_history": list(row.status_history or []),
        "sensitive_transitions": list(SENSITIVE_DELIVERY_STATUSES),
        "route": {"id": best.get("id"), "name": best.get("name"), "distance_km": best.get("distance_km"), "duration_minutes": best.get("duration_minutes"),
                  "eta_minutes": best.get("eta_minutes"), "road_quality": best.get("road_quality"), "recommended_vehicle": best.get("recommended_vehicle"), "rationale": best.get("rationale")} if best else None,
        "accessibility_detail": best.get("accessibility"), "risk": best.get("risk"), "weather": best.get("weather"), "terrain": best.get("terrain"),
        "hazards": hazards, "geometry": best.get("geometry", []),
        "source_coordinate": snapshot.get("source", {}).get("coordinate"), "destination_coordinate": snapshot.get("destination", {}).get("coordinate"),
        "data_quality": snapshot.get("data_quality", {}),
        "analysis": {"analysis_id": str(analysis_row.id), "created_at": analysis_row.created_at, "requested_vehicle": analysis_row.requested_vehicle,
                     "emergency_mode": analysis_row.emergency_mode, "explanation": snapshot.get("explanation"), "data_disclaimer": snapshot.get("data_disclaimer"),
                     "route_count": len(snapshot.get("routes", []))} if analysis_row else None,
    }
