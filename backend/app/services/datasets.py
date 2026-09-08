"""Dataset registry service.

A DatasetSource records where hazard evidence came from, its provenance type,
approximate coverage and import history. Imported files are never promoted to
live automatically: only `provenance_type == "live"` may set `is_live`.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain import DATASET_DATA_TYPES, DATASET_STATUSES, HAZARD_CATEGORIES, LAYER_TYPES, LAYER_TYPE_LABELS, LIVE_CAPABLE_PROVENANCE, PROVENANCE_TYPES
from app.models import DatasetSource

def normalize_provenance(value: str | None) -> str:
    value = (value or "historical").strip().lower()
    aliases = {"realtime": "live", "real-time": "live", "current": "live", "static": "historical", "archive": "historical",
               "susceptibility": "estimated", "model": "estimated", "modelled": "estimated", "demo": "simulated", "synthetic": "simulated"}
    value = aliases.get(value, value)
    if value not in PROVENANCE_TYPES:
        raise ValueError(f"provenance_type must be one of {PROVENANCE_TYPES}")
    return value

def validate_bbox(bbox) -> list[float] | None:
    if bbox is None:
        return None
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("coverage_bbox must be [min_lon, min_lat, max_lon, max_lat]")
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        raise ValueError("coverage_bbox is outside WGS84 bounds or inverted")
    return [min_lon, min_lat, max_lon, max_lat]

def serialize_dataset(x: DatasetSource) -> dict:
    meta = x.metadata_json or {}
    return {
        "id": str(x.id), "name": x.name, "slug": x.slug, "provider": x.provider, "organization": x.source_organization,
        "category": x.hazard_category, "data_type": x.data_type, "version": x.dataset_version, "records": x.record_count,
        "published_at": x.published_at, "downloaded_at": x.downloaded_at, "last_imported": x.ingested_at,
        "provenance": x.provenance_type, "coverage": x.coverage_area, "coverage_bbox": x.coverage_bbox, "crs": x.crs,
        "status": x.status, "is_live": x.is_live, "license": x.license, "source_url": x.source_url,
        "layer_type": x.layer_type or "hazard_zones", "layer_label": LAYER_TYPE_LABELS.get(x.layer_type or "hazard_zones", "Hazard Zones"),
        "attribution": x.attribution, "period_start": x.period_start, "period_end": x.period_end,
        "dataset_period": period_text(x.period_start, x.period_end), "access_method": meta.get("access_method"), "source_metadata": meta.get("source_metadata"),
        "last_import": meta.get("last_import"), "created_at": x.created_at, "updated_at": x.updated_at,
    }

def period_text(start, end) -> str | None:
    if not start and not end:
        return None
    fmt = lambda d: d.strftime("%Y-%m") if d else "…"
    return f"{fmt(start)} → {fmt(end)}" if start and end and start != end else fmt(end or start)

class DatasetRegistryService:
    async def list(self, session: AsyncSession) -> list[DatasetSource]:
        return list((await session.scalars(select(DatasetSource).order_by(DatasetSource.name))).all())

    async def get(self, session: AsyncSession, dataset_id: uuid.UUID) -> DatasetSource | None:
        return await session.get(DatasetSource, dataset_id)

    async def by_slug(self, session: AsyncSession, slug: str) -> DatasetSource | None:
        return await session.scalar(select(DatasetSource).where(DatasetSource.slug == slug))

    async def register(self, session: AsyncSession, spec: dict) -> DatasetSource:
        """Create or update a registry entry from a mapping-config `dataset` block. Idempotent by slug."""
        provenance = normalize_provenance(spec.get("provenance_type"))
        if spec.get("hazard_category", "other") not in HAZARD_CATEGORIES:
            raise ValueError(f"hazard_category must be one of {HAZARD_CATEGORIES}")
        if spec.get("data_type", "risk_zones") not in DATASET_DATA_TYPES:
            raise ValueError(f"data_type must be one of {DATASET_DATA_TYPES}")
        is_live = bool(spec.get("is_live")) and provenance in LIVE_CAPABLE_PROVENANCE
        layer_type = spec.get("layer_type") or ("incidents" if spec.get("data_type") == "incidents" else "hazard_zones")
        if layer_type not in LAYER_TYPES:
            raise ValueError(f"layer_type must be one of {LAYER_TYPES}")
        if layer_type == "current_events" and provenance != "live":
            raise ValueError("current_events layers require provenance_type live")
        row = await self.by_slug(session, spec["slug"])
        values = dict(
            name=spec["name"], provider=spec.get("provider", spec.get("source_organization", "unknown")), hazard_category=spec.get("hazard_category", "other"),
            data_type=spec.get("data_type", "risk_zones"), source_url=spec.get("source_url"), source_organization=spec.get("source_organization", "unknown"),
            dataset_version=str(spec.get("dataset_version", "unversioned")), published_at=parse_dt(spec.get("published_at")), downloaded_at=parse_dt(spec.get("downloaded_at")),
            crs=spec.get("crs", "EPSG:4326"), coverage_area=spec.get("coverage_area"), coverage_bbox=validate_bbox(spec.get("coverage_bbox")),
            is_live=is_live, provenance_type=provenance, license=spec.get("license"), layer_type=layer_type, attribution=spec.get("attribution"),
            period_start=parse_dt(spec.get("period_start")), period_end=parse_dt(spec.get("period_end")),
        )
        if row is None:
            row = DatasetSource(slug=spec["slug"], status="registered", record_count=0, metadata_json={"description": spec.get("description"), "access_method": spec.get("access_method"), "source_metadata": spec.get("source_metadata")}, **values)
            session.add(row)
        else:
            for k, v in values.items():
                setattr(row, k, v)
            row.metadata_json = {**(row.metadata_json or {}), "description": spec.get("description"), "access_method": spec.get("access_method"), "source_metadata": spec.get("source_metadata")}
            if row.status not in DATASET_STATUSES:
                row.status = "registered"
        await session.flush()
        return row

    async def record_import(self, session: AsyncSession, row: DatasetSource, report: dict, record_count: int, status: str):
        row.record_count = record_count
        row.status = status
        row.ingested_at = datetime.now(timezone.utc) if status == "imported" else row.ingested_at
        row.metadata_json = {**(row.metadata_json or {}), "last_import": report}
        await session.flush()

def parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
