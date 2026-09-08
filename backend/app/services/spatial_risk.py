"""Route ↔ hazard spatial summary backed by PostGIS.

Returns explicit data-state semantics (see docs/risk-intelligence.md) and the
identifiers of the hazard zones/incidents related to the route so the map can
state a backend-confirmed relationship instead of inferring it visually.
"""
import logging
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.domain import HAZARD_NEAR_METRES, HAZARD_STATUS_UNAVAILABLE, INCIDENT_BUFFER_METRES, SEVERITY_LABELS
from app.models import AnalyzedRoute, DatasetSource, HistoricalIncident, RiskZone, RouteAnalysis
from app.schemas.analysis import Coordinate
from app.services.confidence import confidence_for, hazard_quality
from app.services.hazards import HazardIntelligenceService

log = logging.getLogger("pathsense.spatial")
SEVERITY = SEVERITY_LABELS

class SpatialRiskService:
    async def route_for(self, session: AsyncSession, user_id: uuid.UUID, analysis_id: uuid.UUID):
        return await session.scalar(select(AnalyzedRoute).join(RouteAnalysis).where(RouteAnalysis.id == analysis_id, RouteAnalysis.user_id == user_id, AnalyzedRoute.is_recommended))

    async def summary(self, session: AsyncSession, user_id: uuid.UUID, analysis_id: uuid.UUID):
        analysis = await session.scalar(select(RouteAnalysis).where(RouteAnalysis.id == analysis_id, RouteAnalysis.user_id == user_id))
        if not analysis:
            return None
        # Copy plain values first: a failed spatial query rolls the session back and expires ORM attributes.
        data_quality = dict(analysis.data_quality or {})
        snapshot_route = next((r for r in (analysis.response_snapshot or {}).get("routes", []) if r.get("recommended")), None)
        route = await self.route_for(session, user_id, analysis_id)
        route_id = route.id if route else None
        base = {"analysis_id": str(analysis_id), "route_id": str(route_id) if route_id else None}
        service = HazardIntelligenceService(session)
        if route is None or not service.spatial_available:
            return {**base, **self.unavailable(data_quality, "Spatial database unavailable; route geometry was not evaluated against hazard datasets.")}
        # Typed geometry reference (a scalar subquery) so PostGIS casts resolve unambiguously.
        geometry = select(AnalyzedRoute.geometry).where(AnalyzedRoute.id == route_id).scalar_subquery()
        try:
            points = [Coordinate(**p) for p in (snapshot_route or {}).get("geometry", [])]
            datasets = await service.datasets()
            exposure = await service.exposure_for_geometry(geometry, points, datasets)
            related = await self.related_features(session, geometry, service)
        except Exception as exc:
            log.warning("spatial_summary_failed", extra={"error_type": type(exc).__name__})
            await session.rollback()
            return {**base, **self.unavailable(data_quality, "Spatial hazard query failed; hazard exposure is unknown rather than zero.")}
        quality = {**data_quality, "landslide": hazard_quality(exposure)}
        confidence, reasons = confidence_for(quality)
        return {
            **base,
            "hazard_status": exposure.status,
            "provenance": exposure.provenance,
            "hazards": {k: v.model_dump() for k, v in exposure.categories.items()},
            "landslide_exposure_km": exposure.categories.get("landslide").affected_distance_km if "landslide" in exposure.categories else 0.0,
            "flood_exposure_km": exposure.categories.get("flood").affected_distance_km if "flood" in exposure.categories else 0.0,
            "historical_incidents_nearby": exposure.historical_incidents_nearby,
            "zones_crossed": exposure.zones_crossed,
            "affected_distance_km": exposure.affected_distance_km,
            "highest_severity": exposure.highest_severity,
            "coverage_ratio": exposure.coverage_ratio,
            "datasets": exposure.datasets,
            "confidence": confidence,
            "confidence_reasons": reasons,
            "reasons": exposure.reasons,
            **related,
        }

    def unavailable(self, data_quality, reason: str) -> dict:
        if not isinstance(data_quality, dict):
            data_quality = dict(getattr(data_quality, "data_quality", None) or {})
        quality = {**data_quality, "landslide": {"status": "unavailable", "provider": "none", "reason": reason}}
        confidence, reasons = confidence_for(quality)
        return {"hazard_status": HAZARD_STATUS_UNAVAILABLE, "provenance": "unavailable", "hazards": {}, "landslide_exposure_km": None, "flood_exposure_km": None,
                "historical_incidents_nearby": None, "zones_crossed": None, "affected_distance_km": None, "highest_severity": "unknown", "coverage_ratio": None,
                "datasets": [], "confidence": confidence, "confidence_reasons": reasons, "reasons": [reason],
                "intersecting_zone_ids": [], "nearby_zone_ids": [], "nearby_incident_ids": []}

    async def related_features(self, session: AsyncSession, geometry, service: HazardIntelligenceService) -> dict:
        """Backend-confirmed relationships: zones the route crosses, zones within the near buffer, incidents within the incident buffer."""
        zone_filter = service.zone_filter()
        intersects = select(RiskZone.id).where(func.ST_Intersects(geometry, RiskZone.geometry))
        near = select(RiskZone.id).where(func.ST_DWithin(func.Geography(RiskZone.geometry), func.Geography(geometry), HAZARD_NEAR_METRES), ~func.ST_Intersects(geometry, RiskZone.geometry))
        incidents = select(HistoricalIncident.id).where(func.ST_DWithin(func.Geography(HistoricalIncident.geometry), func.Geography(geometry), INCIDENT_BUFFER_METRES))
        if zone_filter is not None:
            intersects = intersects.where(zone_filter); near = near.where(zone_filter)
            simulated = select(DatasetSource.id).where(DatasetSource.provenance_type == "simulated")
            incidents = incidents.where(or_(HistoricalIncident.dataset_source_id.is_(None), HistoricalIncident.dataset_source_id.not_in(simulated)))
        return {
            "intersecting_zone_ids": [str(x) for x in (await session.scalars(intersects.limit(500))).all()],
            "nearby_zone_ids": [str(x) for x in (await session.scalars(near.limit(500))).all()],
            "nearby_incident_ids": [str(x) for x in (await session.scalars(incidents.limit(500))).all()],
        }
