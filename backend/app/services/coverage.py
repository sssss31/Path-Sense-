"""Dataset ↔ route coverage.

`calculate_dataset_route_coverage` answers whether a registered dataset
actually covers a route before any hazard claim is made about it. Coverage is
derived from the dataset's declared or observed bounding box (cheap, no GIS
round trip); status thresholds live in app.core.domain.
"""
from app.core.domain import COVERAGE_FULL, COVERAGE_FULL_THRESHOLD, COVERAGE_NONE, COVERAGE_PARTIAL, COVERAGE_PARTIAL_THRESHOLD, COVERAGE_UNKNOWN
from app.schemas.analysis import Coordinate

def dataset_bbox(dataset) -> list[float] | None:
    """Declared coverage_bbox, else the bbox observed at import time, else None."""
    bbox = getattr(dataset, "coverage_bbox", None)
    if bbox:
        return list(bbox)
    meta = getattr(dataset, "metadata_json", None) or {}
    observed = (meta.get("last_import") or {}).get("coverage_bbox_observed")
    return list(observed) if observed else None

def _inside(p: Coordinate, box: list[float]) -> bool:
    return box[0] <= p.lng <= box[2] and box[1] <= p.lat <= box[3]

def coverage_percent(points: list[Coordinate], boxes: list[list[float]]) -> float | None:
    if not points or not boxes:
        return None
    inside = sum(1 for p in points if any(_inside(p, b) for b in boxes))
    return round(inside / len(points) * 100, 1)

def status_for_percent(percent: float | None) -> str:
    if percent is None:
        return COVERAGE_UNKNOWN
    if percent >= COVERAGE_FULL_THRESHOLD * 100:
        return COVERAGE_FULL
    if percent >= COVERAGE_PARTIAL_THRESHOLD * 100:
        return COVERAGE_PARTIAL
    return COVERAGE_NONE

def calculate_dataset_route_coverage(route_geometry: list[Coordinate], dataset_source) -> dict:
    """Return {"status": full|partial|none|unknown, "coverage_percent": float|None, "dataset": slug}."""
    box = dataset_bbox(dataset_source)
    percent = coverage_percent(route_geometry, [box]) if box else None
    return {"status": status_for_percent(percent), "coverage_percent": percent, "dataset": getattr(dataset_source, "slug", None)}

def combined_coverage(route_geometry: list[Coordinate], datasets: list) -> dict:
    """Coverage of a route by the union of several datasets (same layer family)."""
    boxes = [b for b in (dataset_bbox(d) for d in datasets) if b]
    if not datasets:
        return {"status": COVERAGE_NONE, "coverage_percent": 0.0, "datasets": []}
    percent = coverage_percent(route_geometry, boxes) if boxes else None
    return {"status": status_for_percent(percent), "coverage_percent": percent, "datasets": [getattr(d, "slug", None) for d in datasets]}
