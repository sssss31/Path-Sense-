"""Aggregation queries for the dashboard and reports.

All aggregation happens in SQL; the API never ships individual route
geometries for charts. Range presets live in app.core.domain.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import cast, func, select, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import DEFAULT_REPORT_RANGE, REPORT_RANGES, RISK_FACTOR_LABELS
from app.models import AnalyzedRoute, Delivery, RouteAnalysis

RISK_ORDER = ["low", "moderate", "high", "critical"]

def resolve_range(range_key: str | None, date_from: datetime | None, date_to: datetime | None) -> tuple[datetime, datetime, str]:
    now = datetime.now(timezone.utc)
    end = date_to or now
    if date_from:
        return date_from, end, "custom"
    key = range_key if range_key in REPORT_RANGES else DEFAULT_REPORT_RANGE
    return end - timedelta(days=REPORT_RANGES[key]), end, key

def factor_label(warning: str) -> str | None:
    if warning in RISK_FACTOR_LABELS:
        return RISK_FACTOR_LABELS[warning]
    lowered = warning.lower()
    if "landslide" in lowered and "exposure" in lowered: return "Landslide exposure"
    if "flood" in lowered and "exposure" in lowered: return "Flood exposure"
    if "incident" in lowered: return "Historical incidents"
    if "rain" in lowered: return "Heavy rainfall"
    if "terrain" in lowered or "gradient" in lowered or "slope" in lowered: return "Steep terrain"
    if "road" in lowered: return "Poor road suitability"
    return warning

class ReportsService:
    def owned(self, user_id: uuid.UUID, start: datetime, end: datetime):
        return (RouteAnalysis.user_id == user_id, RouteAnalysis.created_at >= start, RouteAnalysis.created_at <= end)

    async def risk_distribution(self, session: AsyncSession, user_id, start, end) -> list[dict]:
        rows = (await session.execute(select(AnalyzedRoute.risk_level, func.count()).join(RouteAnalysis).where(*self.owned(user_id, start, end), AnalyzedRoute.is_recommended).group_by(AnalyzedRoute.risk_level))).all()
        counts = {level: n for level, n in rows}
        return [{"name": level, "value": counts.get(level, 0)} for level in RISK_ORDER if level in counts or level != "critical"]

    async def accessibility_trend(self, session: AsyncSession, user_id, start, end) -> list[dict]:
        day = func.date(RouteAnalysis.created_at)  # portable: DATE on PostgreSQL, 'YYYY-MM-DD' text on SQLite
        rows = (await session.execute(select(day, func.avg(AnalyzedRoute.accessibility_score), func.count()).join(RouteAnalysis).where(*self.owned(user_id, start, end), AnalyzedRoute.is_recommended).group_by(day).order_by(day))).all()
        return [{"date": str(d), "average_accessibility": round(float(avg or 0), 1), "analyses": n} for d, avg, n in rows]

    async def risk_factors(self, session: AsyncSession, user_id, start, end, limit=8) -> list[dict]:
        rows = (await session.execute(select(AnalyzedRoute.warnings).join(RouteAnalysis).where(*self.owned(user_id, start, end), AnalyzedRoute.is_recommended))).all()
        counts: dict[str, int] = {}
        for (warnings,) in rows:
            for w in warnings or []:
                label = factor_label(str(w))
                if label:
                    counts[label] = counts.get(label, 0) + 1
        return [{"name": k, "value": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]

    async def cargo_distribution(self, session: AsyncSession, user_id, start, end) -> list[dict]:
        rows = (await session.execute(select(RouteAnalysis.cargo_type, func.count()).where(*self.owned(user_id, start, end)).group_by(RouteAnalysis.cargo_type))).all()
        return [{"name": a, "value": b} for a, b in rows]

    async def delivery_status(self, session: AsyncSession, user_id, start, end) -> list[dict]:
        rows = (await session.execute(select(Delivery.status, func.count()).where(Delivery.user_id == user_id, Delivery.created_at >= start, Delivery.created_at <= end).group_by(Delivery.status))).all()
        return [{"name": a, "value": b} for a, b in rows]

    async def data_availability(self, session: AsyncSession, user_id, start, end) -> list[dict]:
        """Analyses grouped by evidence state, from persisted data_quality + recommended-route confidence."""
        rows = (await session.execute(select(RouteAnalysis.data_quality, AnalyzedRoute.factors).join(AnalyzedRoute, AnalyzedRoute.analysis_id == RouteAnalysis.id).where(*self.owned(user_id, start, end), AnalyzedRoute.is_recommended))).all()
        buckets = {"Full data coverage": 0, "Partial hazard coverage": 0, "Hazard data unavailable": 0, "Simulated demo data": 0, "Weather unavailable": 0}
        for quality, factors in rows:
            quality = quality or {}
            hazard = (quality.get("landslide") or {}).get("status", "unavailable")
            weather = (quality.get("weather") or {}).get("status", "unavailable")
            if weather == "unavailable": buckets["Weather unavailable"] += 1
            if hazard == "simulated" or (quality.get("routing") or {}).get("status") == "simulated": buckets["Simulated demo data"] += 1
            elif hazard == "partial": buckets["Partial hazard coverage"] += 1
            elif hazard == "unavailable": buckets["Hazard data unavailable"] += 1
            else: buckets["Full data coverage"] += 1
        return [{"name": k, "value": v} for k, v in buckets.items() if v]

    async def summary(self, session: AsyncSession, user_id, range_key=None, date_from=None, date_to=None) -> dict:
        start, end, key = resolve_range(range_key, date_from, date_to)
        return {
            "range": {"key": key, "from": start, "to": end, "available": list(REPORT_RANGES)},
            "risk_distribution": await self.risk_distribution(session, user_id, start, end),
            "cargo_distribution": await self.cargo_distribution(session, user_id, start, end),
            "delivery_status": await self.delivery_status(session, user_id, start, end),
            "accessibility_trend": await self.accessibility_trend(session, user_id, start, end),
            "risk_factors": await self.risk_factors(session, user_id, start, end),
            "data_availability": await self.data_availability(session, user_id, start, end),
        }
