"""Hazard intelligence for route analysis (v3).

Consumes normalized spatial hazard metrics from PostGIS by *layer family*:

* landslide inventory        (HistoricalIncident, dataset.layer_type landslide_inventory / incidents)
* landslide susceptibility   (RiskZone, dataset.layer_type landslide_susceptibility)
* flood hazard / inundation  (RiskZone, dataset.layer_type flood_hazard / flood_inundation)
* legacy hazard zones        (RiskZone with any other layer type)

and reports the data state honestly per family through dataset coverage:

* ``intersections``     coverage exists and the route crosses hazard geometry
* ``no_intersection``   coverage exists and PostGIS confirmed no crossing
* ``partial_coverage``  the route extends beyond imported dataset coverage
* ``unavailable``       no spatial database or no imported dataset
* ``simulated``         demo mode deterministic seed (never used in live mode)
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.domain import (COVERAGE_FULL, COVERAGE_NONE, COVERAGE_PARTIAL, COVERAGE_UNKNOWN, HAZARD_STATUS_INTERSECTION, HAZARD_STATUS_NO_INTERSECTION,
                             HAZARD_STATUS_PARTIAL, HAZARD_STATUS_SIMULATED, HAZARD_STATUS_UNAVAILABLE, INCIDENT_BUFFER_METRES, SEVERITY_LABELS,
                             SUSCEPTIBILITY_LABELS, hazard_label)
from app.models import DatasetSource, HistoricalIncident, RiskZone
from app.schemas.analysis import Coordinate, FloodFeatures, HazardCategoryExposure, HazardExposure, LandslideFeatures
from app.services.coverage import combined_coverage

log = logging.getLogger("pathsense.hazards")

SUSCEPTIBILITY_TYPES = {"landslide_susceptibility"}
FLOOD_TYPES = {"flood_hazard", "flood_inundation"}
INVENTORY_TYPES = {"landslide_inventory", "incidents"}

def line_wkt(points: list[Coordinate]) -> str:
    return "LINESTRING(" + ",".join(f"{p.lng} {p.lat}" for p in points) + ")"

def route_geometry(points: list[Coordinate]):
    return func.ST_SetSRID(func.ST_GeomFromText(line_wkt(points)), 4326)

def coverage_ratio(points: list[Coordinate], boxes: list[list[float]]) -> float | None:
    """Share of route vertices inside at least one dataset bounding box (None when no bbox is declared)."""
    if not boxes or not points:
        return None
    inside = sum(1 for p in points if any(b[0] <= p.lng <= b[2] and b[1] <= p.lat <= b[3] for b in boxes))
    return round(inside / len(points), 3)

def simulated_exposure(variant: int) -> HazardExposure:
    """Deterministic demo seed. Explicitly labelled simulated; never used in live mode."""
    seed = {1: (2, 3.4, 4, 3, 1, 1.1), 2: (0, 0.0, 0, 0, 0, 0.0), 3: (1, 1.2, 3, 1, 0, 0.0)}.get(variant, (0, 0.0, 0, 0, 0, 0.0))
    zones, km, severity, incidents, flood_zones, flood_km = seed
    categories = {"landslide": HazardCategoryExposure(zones_crossed=zones, affected_distance_km=km, highest_severity=SEVERITY_LABELS.get(severity, "none"), label=hazard_label("landslide", "simulated"))} if zones else {}
    if flood_zones:
        categories["flood"] = HazardCategoryExposure(zones_crossed=flood_zones, affected_distance_km=flood_km, highest_severity="moderate", label=hazard_label("flood", "simulated"))
    return HazardExposure(status=HAZARD_STATUS_SIMULATED, provenance="simulated", zones_crossed=zones + flood_zones, affected_distance_km=round(km + flood_km, 2),
                          highest_severity=SEVERITY_LABELS.get(severity, "none"), historical_incidents_nearby=incidents, categories=categories, datasets=["demo-seed"], coverage_ratio=1.0,
                          reasons=["Hazard zones are simulated demo evidence, not an authoritative dataset."],
                          landslide=LandslideFeatures(susceptibility_zones_crossed=zones, highest_susceptibility=SUSCEPTIBILITY_LABELS.get(severity, "none"), susceptibility_affected_km=km,
                                                      historical_incidents_within_2km=incidents, affected_distance_km=km, dataset_coverage=COVERAGE_FULL, inventory_coverage=COVERAGE_FULL, susceptibility_coverage=COVERAGE_FULL),
                          flood=FloodFeatures(historical_zones_crossed=flood_zones, affected_distance_km=flood_km, highest_hazard="moderate" if flood_zones else "none", dataset_coverage=COVERAGE_FULL))

def family_of(dataset: DatasetSource) -> str:
    lt = dataset.layer_type or "hazard_zones"
    if lt in SUSCEPTIBILITY_TYPES: return "susceptibility"
    if lt in FLOOD_TYPES: return "flood"
    if lt in INVENTORY_TYPES or dataset.data_type == "incidents": return "inventory"
    if dataset.hazard_category == "flood": return "flood"
    return "zones"

class HazardIntelligenceService:
    def __init__(self, session: AsyncSession | None):
        self.session = session
        self.settings = get_settings()
        self._reachable: bool | None = None   # probed once per service instance
        self._unreachable_reason: str | None = None

    @property
    def spatial_available(self) -> bool:
        if self.session is None:
            return False
        try:
            bind = self.session.get_bind()
            return bool(bind) and bind.dialect.name == "postgresql"
        except Exception:
            return False

    async def ensure_reachable(self) -> bool:
        """One cheap probe per analysis so an unreachable database is reported once, not retried per route."""
        if self._reachable is not None:
            return self._reachable
        from sqlalchemy import text
        try:
            await self.session.execute(text("SELECT 1"))
            self._reachable = True
        except Exception as exc:
            self._reachable = False
            self._unreachable_reason = f"Spatial database unreachable ({type(exc).__name__}); hazard exposure was not evaluated."
            log.warning("hazard_database_unreachable: %s", type(exc).__name__)
            try:
                await self.session.rollback()
            except Exception:
                pass
        return self._reachable

    async def datasets(self) -> list[DatasetSource]:
        q = select(DatasetSource).where(DatasetSource.status == "imported")
        if not self.settings.use_mock_data:
            q = q.where(DatasetSource.provenance_type != "simulated")
        return list((await self.session.scalars(q)).all())

    def zone_filter(self):
        """Live mode must never consume simulated zones; demo mode may."""
        if self.settings.use_mock_data:
            return None
        simulated = select(DatasetSource.id).where(DatasetSource.provenance_type == "simulated")
        return or_(RiskZone.dataset_source_id.is_(None), RiskZone.dataset_source_id.not_in(simulated))

    def incident_filter(self):
        if self.settings.use_mock_data:
            return None
        simulated = select(DatasetSource.id).where(DatasetSource.provenance_type == "simulated")
        return or_(HistoricalIncident.dataset_source_id.is_(None), HistoricalIncident.dataset_source_id.not_in(simulated))

    async def _zone_rows(self, geometry, dataset_ids: list, exclude_ids: list | None = None):
        affected = func.ST_Length(func.Geography(func.ST_Intersection(geometry, RiskZone.geometry))) / 1000
        q = select(RiskZone.category, func.count(RiskZone.id), func.max(RiskZone.severity), func.sum(affected)).where(func.ST_Intersects(geometry, RiskZone.geometry))
        if dataset_ids:
            q = q.where(RiskZone.dataset_source_id.in_(dataset_ids))
        elif exclude_ids:
            q = q.where(or_(RiskZone.dataset_source_id.is_(None), RiskZone.dataset_source_id.not_in(exclude_ids)))
        if (flt := self.zone_filter()) is not None:
            q = q.where(flt)
        return (await self.session.execute(q.group_by(RiskZone.category))).all()

    async def exposure_for_geometry(self, geometry, points: list[Coordinate] | None = None, datasets: list[DatasetSource] | None = None) -> HazardExposure:
        """Compute exposure for a PostGIS geometry expression (route linestring)."""
        if datasets is None:
            datasets = await self.datasets()
        if not datasets:
            return HazardExposure(status=HAZARD_STATUS_UNAVAILABLE, provenance="unavailable", reasons=["No hazard dataset has been imported; hazard exposure cannot be evaluated."])
        points = points or []
        by_family: dict[str, list[DatasetSource]] = {"susceptibility": [], "flood": [], "inventory": [], "zones": []}
        for d in datasets:
            by_family[family_of(d)].append(d)
        sus_ids = [d.id for d in by_family["susceptibility"]]
        flood_ids = [d.id for d in by_family["flood"]]
        # susceptibility zones
        sus_rows = await self._zone_rows(geometry, sus_ids) if sus_ids else []
        flood_rows = await self._zone_rows(geometry, flood_ids) if flood_ids else []
        other_rows = await self._zone_rows(geometry, [], exclude_ids=sus_ids + flood_ids)
        # historical incidents within buffer (inventory family)
        incident_q = select(func.count(HistoricalIncident.id)).where(func.ST_DWithin(func.Geography(HistoricalIncident.geometry), func.Geography(geometry), INCIDENT_BUFFER_METRES))
        if (iflt := self.incident_filter()) is not None:
            incident_q = incident_q.where(iflt)
        incidents = int(await self.session.scalar(incident_q) or 0)

        kinds = {d.provenance_type for d in datasets}
        provenance = "simulated" if kinds == {"simulated"} else "live" if kinds == {"live"} else "estimated" if kinds == {"estimated"} else "historical"
        categories: dict[str, HazardCategoryExposure] = {}
        for rows in (sus_rows, flood_rows, other_rows):
            for r in rows:
                existing = categories.get(r[0])
                add = HazardCategoryExposure(zones_crossed=r[1], affected_distance_km=round(float(r[3] or 0), 2), highest_severity=SEVERITY_LABELS.get(r[2], "unknown"), label=hazard_label(r[0], provenance))
                if existing:
                    existing.zones_crossed += add.zones_crossed; existing.affected_distance_km = round(existing.affected_distance_km + add.affected_distance_km, 2)
                    if SEVERITY_ORDER.index(add.highest_severity) > SEVERITY_ORDER.index(existing.highest_severity): existing.highest_severity = add.highest_severity
                else:
                    categories[r[0]] = add
        # coverage per family
        cov_sus = combined_coverage(points, by_family["susceptibility"])
        cov_inv = combined_coverage(points, by_family["inventory"])
        cov_flood = combined_coverage(points, by_family["flood"])
        cov_all = combined_coverage(points, datasets)
        sus_max = max((r[2] for r in sus_rows), default=0)
        landslide = LandslideFeatures(
            susceptibility_zones_crossed=sum(r[1] for r in sus_rows), highest_susceptibility=SUSCEPTIBILITY_LABELS.get(sus_max, "none"),
            susceptibility_affected_km=round(sum(float(r[3] or 0) for r in sus_rows), 2), historical_incidents_within_2km=incidents,
            affected_distance_km=round(sum(float(r[3] or 0) for r in sus_rows) + sum(float(r[3] or 0) for r in other_rows if r[0] == "landslide"), 2),
            dataset_coverage=best_coverage(cov_sus["status"], cov_inv["status"]), inventory_coverage=cov_inv["status"], susceptibility_coverage=cov_sus["status"],
        )
        flood_max = max((r[2] for r in flood_rows), default=0)
        flood = FloodFeatures(historical_zones_crossed=sum(r[1] for r in flood_rows), affected_distance_km=round(sum(float(r[3] or 0) for r in flood_rows), 2),
                              highest_hazard=SEVERITY_LABELS.get(flood_max, "none"), dataset_coverage=cov_flood["status"])
        all_rows = sus_rows + flood_rows + other_rows
        highest = max((r[2] for r in all_rows), default=0)
        ratio = (cov_all["coverage_percent"] / 100) if cov_all["coverage_percent"] is not None else None
        reasons: list[str] = []
        if ratio is not None and ratio < 0.98:
            status = HAZARD_STATUS_PARTIAL
            reasons.append("Historical landslide dataset does not cover the full route.")
        elif all_rows:
            status = HAZARD_STATUS_INTERSECTION
        else:
            status = HAZARD_STATUS_NO_INTERSECTION
        if ratio is None:
            reasons.append("Dataset coverage extent is not declared; coverage assumed from imported geometry.")
        for label, cov in (("Landslide susceptibility", cov_sus), ("Landslide inventory", cov_inv), ("Flood hazard", cov_flood)):
            if cov["status"] == COVERAGE_NONE:
                reasons.append(f"{label} dataset is not imported for this route; that exposure is unknown, not zero.")
            elif cov["status"] == COVERAGE_PARTIAL:
                reasons.append(f"{label} dataset covers only part of the route ({cov['coverage_percent']}%).")
        return HazardExposure(status=status, provenance=provenance, zones_crossed=sum(r[1] for r in all_rows), affected_distance_km=round(sum(float(r[3] or 0) for r in all_rows), 2),
                              highest_severity=SEVERITY_LABELS.get(highest, "none"), historical_incidents_nearby=incidents, categories=categories,
                              datasets=[d.name for d in datasets], coverage_ratio=ratio, reasons=reasons, landslide=landslide, flood=flood)

    async def exposure_for_points(self, points: list[Coordinate], variant: int | None = None) -> HazardExposure:
        if self.settings.use_mock_data and not self.spatial_available:
            return simulated_exposure(variant or 1)
        if not self.spatial_available:
            return HazardExposure(status=HAZARD_STATUS_UNAVAILABLE, provenance="unavailable", reasons=["Spatial hazard database is unavailable (not PostgreSQL/PostGIS); hazard exposure was not evaluated."])
        if not await self.ensure_reachable():
            if self.settings.use_mock_data:
                return simulated_exposure(variant or 1)
            return HazardExposure(status=HAZARD_STATUS_UNAVAILABLE, provenance="unavailable", reasons=[self._unreachable_reason or "Spatial database unreachable; hazard exposure was not evaluated."])
        try:
            datasets = await self.datasets()
            if not datasets and self.settings.use_mock_data:
                return simulated_exposure(variant or 1)
            return await self.exposure_for_geometry(route_geometry(points), points, datasets)
        except Exception as exc:
            log.warning("hazard_query_failed: %s", type(exc).__name__)
            try:
                await self.session.rollback()
            except Exception:
                pass
            if self.settings.use_mock_data:
                return simulated_exposure(variant or 1)
            return HazardExposure(status=HAZARD_STATUS_UNAVAILABLE, provenance="unavailable", reasons=["Spatial hazard query failed; hazard exposure was not evaluated."])

SEVERITY_ORDER = ["none", "unknown", "low", "moderate", "high", "critical"]

def best_coverage(*statuses: str) -> str:
    order = [COVERAGE_FULL, COVERAGE_PARTIAL, COVERAGE_UNKNOWN, COVERAGE_NONE]
    present = [s for s in statuses if s in order]
    return min(present, key=order.index) if present else COVERAGE_NONE

def hazard_sentence(exposure: HazardExposure) -> str:
    """Deterministic, honest wording for explanations and Gemini context."""
    if exposure.status == HAZARD_STATUS_SIMULATED or exposure.provenance == "simulated":
        return f"Simulated demo hazard data indicates {exposure.zones_crossed} risk-zone intersection(s) over {exposure.affected_distance_km} km; this is not authoritative evidence."
    if exposure.status == HAZARD_STATUS_UNAVAILABLE:
        return "Historical hazard data is unavailable for this route, so hazard exposure is unknown rather than zero."
    ls, fl = exposure.landslide, exposure.flood
    parts = []
    if ls.susceptibility_coverage in {COVERAGE_FULL, COVERAGE_PARTIAL}:
        parts.append(f"landslide susceptibility: {ls.susceptibility_zones_crossed} zone(s) crossed (highest {ls.highest_susceptibility}, coverage {ls.susceptibility_coverage})")
    if ls.inventory_coverage in {COVERAGE_FULL, COVERAGE_PARTIAL}:
        parts.append(f"landslide inventory: {ls.historical_incidents_within_2km} recorded incident(s) within 2 km (coverage {ls.inventory_coverage})")
    if fl.dataset_coverage in {COVERAGE_FULL, COVERAGE_PARTIAL}:
        parts.append(f"flood hazard: {fl.historical_zones_crossed} zone(s), {fl.affected_distance_km} km exposure (coverage {fl.dataset_coverage})")
    missing = [n for n, c in (("landslide susceptibility", ls.susceptibility_coverage), ("landslide inventory", ls.inventory_coverage), ("flood hazard", fl.dataset_coverage)) if c in {COVERAGE_NONE, COVERAGE_UNKNOWN}]
    if exposure.status == HAZARD_STATUS_PARTIAL and not parts:
        return f"Historical hazard datasets cover only part of this route ({round((exposure.coverage_ratio or 0) * 100)}%); {exposure.zones_crossed} intersection(s) were found within covered sections. Uncovered sections are unknown, not zero."
    if exposure.status == HAZARD_STATUS_NO_INTERSECTION and not parts:
        return "Historical hazard datasets cover the route and indicate no risk-zone intersections."
    text = "Historical hazard datasets: " + ("; ".join(parts) if parts else f"{exposure.zones_crossed} risk-zone intersection(s) over {exposure.affected_distance_km} km") + "."
    if exposure.status == HAZARD_STATUS_PARTIAL:
        text += f" Datasets cover only part of this route ({round((exposure.coverage_ratio or 0) * 100)}%); uncovered sections are unknown, not zero."
    if missing:
        text += " Not covered (unknown, not zero): " + ", ".join(missing) + "."
    return text

def generated_now() -> datetime:
    return datetime.now(timezone.utc)
