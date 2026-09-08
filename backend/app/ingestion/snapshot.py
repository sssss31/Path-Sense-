"""Corridor-scoped hazard snapshot (historical authoritative snapshot, never simulated).

Extracts the subset of imported PostGIS hazard data that lies within a buffer
around a corridor (default Guwahati → Shillong) into GeoJSON files plus a
metadata file that retains the original dataset, organisation, version/period,
extract date, coverage, provenance, licence and attribution. The snapshot keeps
the demo working when upstream portals are unreachable and can be re-imported
with the same mapping configs (`snapshot_of` is recorded in metadata).

    python -m app.ingestion.snapshot --output data/snapshots/guwahati_shillong --buffer-km 15
    python -m app.ingestion.snapshot --output data/snapshots/guwahati_shillong --include-simulated   # demo/test only
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.models import DatasetSource, HistoricalIncident, RiskZone

DEFAULT_CORRIDOR = "LINESTRING(91.7362 26.1445, 91.78 26.0, 91.82 25.9, 91.86 25.8, 91.88 25.7, 91.8933 25.5788)"

def dataset_metadata(d: DatasetSource) -> dict:
    return {"slug": d.slug, "name": d.name, "organization": d.source_organization, "provider": d.provider, "source_url": d.source_url, "dataset_version": d.dataset_version,
            "published_at": d.published_at.isoformat() if d.published_at else None, "period_start": d.period_start.isoformat() if d.period_start else None, "period_end": d.period_end.isoformat() if d.period_end else None,
            "downloaded_at": d.downloaded_at.isoformat() if d.downloaded_at else None, "ingested_at": d.ingested_at.isoformat() if d.ingested_at else None, "provenance_type": d.provenance_type,
            "layer_type": d.layer_type, "hazard_category": d.hazard_category, "data_type": d.data_type, "coverage_area": d.coverage_area, "coverage_bbox": d.coverage_bbox, "crs": d.crs,
            "license": d.license, "attribution": d.attribution, "record_count": d.record_count, "access_method": (d.metadata_json or {}).get("access_method")}

async def build_snapshot(session_factory, output: str, corridor_wkt: str = DEFAULT_CORRIDOR, buffer_km: float = 15.0, include_simulated: bool = False) -> dict:
    out = Path(output); out.mkdir(parents=True, exist_ok=True)
    corridor = func.ST_SetSRID(func.ST_GeomFromText(corridor_wkt), 4326)
    buffer = func.Geography(corridor)
    summary = {"snapshot_type": "historical authoritative snapshot" if not include_simulated else "demo snapshot (may include simulated datasets)", "corridor_wkt": corridor_wkt, "buffer_km": buffer_km,
               "extracted_at": datetime.now(timezone.utc).isoformat(), "datasets": [], "files": []}
    async with session_factory() as session:
        q = select(DatasetSource).where(DatasetSource.status == "imported")
        if not include_simulated:
            q = q.where(DatasetSource.provenance_type != "simulated")
        datasets = list((await session.scalars(q)).all())
        for d in datasets:
            model = RiskZone if d.data_type == "risk_zones" else HistoricalIncident
            rows = (await session.execute(select(model.category, model.severity, model.fingerprint, model.metadata_json, func.ST_AsGeoJSON(model.geometry), *( [model.occurred_at] if model is HistoricalIncident else [] ))
                                          .where(model.dataset_source_id == d.id, func.ST_DWithin(func.Geography(model.geometry), buffer, buffer_km * 1000)))).all()
            features = []
            for r in rows:
                meta = r[3] or {}
                props = {"category": r[0], "severity": r[1], "fingerprint": r[2], "external_id": meta.get("external_id"), "original_severity": meta.get("original_severity"),
                         "original_category": meta.get("original_category"), "description": meta.get("description"), "event_date": r[5].isoformat() if model is HistoricalIncident and r[5] else meta.get("event_date"),
                         "snapshot_of": d.slug, "provenance_type": d.provenance_type, "attribution": d.attribution}
                features.append({"type": "Feature", "geometry": json.loads(r[4]), "properties": props})
            path = out / f"{d.slug}.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "name": f"{d.name} — corridor snapshot", "snapshot_metadata": dataset_metadata(d), "features": features}))
            summary["datasets"].append({**dataset_metadata(d), "features_in_snapshot": len(features), "file": path.name})
            summary["files"].append(path.name)
    (out / "snapshot.json").write_text(json.dumps(summary, indent=2))
    return summary

def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract a corridor-scoped hazard snapshot from PostGIS")
    parser.add_argument("--output", required=True); parser.add_argument("--corridor-wkt", default=DEFAULT_CORRIDOR); parser.add_argument("--buffer-km", type=float, default=15.0)
    parser.add_argument("--include-simulated", action="store_true", help="demo/test only; the result is then NOT an authoritative snapshot")
    args = parser.parse_args(argv)
    from app.database.session import SessionLocal
    summary = asyncio.run(build_snapshot(SessionLocal, args.output, args.corridor_wkt, args.buffer_km, args.include_simulated))
    print(json.dumps({k: v for k, v in summary.items() if k != "datasets"}, indent=2)); print(f"datasets: {[(d['slug'], d['features_in_snapshot']) for d in summary['datasets']]}")

if __name__ == "__main__":
    main()
