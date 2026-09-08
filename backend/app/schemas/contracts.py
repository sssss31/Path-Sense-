"""Response contracts used by API contract tests (and as documentation of shapes).

Endpoints return plain dicts for flexibility; these models pin the important
fields and types so tests fail on shape regressions, not only status codes.
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

class HazardCategoryContract(BaseModel):
    zones_crossed: int
    affected_distance_km: float
    highest_severity: str
    label: str

class SpatialRiskSummaryContract(BaseModel):
    analysis_id: str
    route_id: str | None
    hazard_status: str = Field(pattern="^(intersections|no_intersection|partial_coverage|unavailable|simulated)$")
    provenance: str
    hazards: dict[str, HazardCategoryContract]
    landslide_exposure_km: float | None
    flood_exposure_km: float | None
    historical_incidents_nearby: int | None
    zones_crossed: int | None
    affected_distance_km: float | None
    highest_severity: str
    coverage_ratio: float | None
    datasets: list[str]
    confidence: float = Field(ge=0, le=1)
    confidence_reasons: list[str]
    reasons: list[str]
    intersecting_zone_ids: list[str]
    nearby_zone_ids: list[str]
    nearby_incident_ids: list[str]

class DatasetContract(BaseModel):
    id: str
    name: str
    slug: str
    organization: str
    category: str
    data_type: str
    version: str
    records: int
    last_imported: datetime | None
    provenance: str = Field(pattern="^(live|historical|estimated|simulated)$")
    coverage: str | None
    coverage_bbox: list[float] | None
    status: str = Field(pattern="^(registered|validated|imported|failed|disabled)$")
    is_live: bool
    last_import: dict[str, Any] | None

class DatasetListContract(BaseModel):
    items: list[DatasetContract]
    total: int

class NamedValue(BaseModel):
    name: str
    value: int

class TrendPoint(BaseModel):
    date: str
    average_accessibility: float
    analyses: int

class ReportsSummaryContract(BaseModel):
    range: dict[str, Any]
    risk_distribution: list[NamedValue]
    cargo_distribution: list[NamedValue]
    delivery_status: list[NamedValue]
    accessibility_trend: list[TrendPoint]
    risk_factors: list[NamedValue]

class AnalysisMapContract(BaseModel):
    analysis_id: str
    created_at: datetime
    source: dict[str, Any]
    destination: dict[str, Any]
    recommended_route: dict[str, Any] | None
    alternatives: list[dict[str, Any]]
    hazards: dict[str, Any] | None
    data_quality: dict[str, Any]

class HistoryItemContract(BaseModel):
    analysis_id: str
    source: str | None
    destination: str | None
    cargo_type: str
    accessibility: int | None
    risk_level: str | None
    recommended_route: str | None
    created_at: datetime

class HistoryContract(BaseModel):
    items: list[HistoryItemContract]
    page: int
    page_size: int
    total: int

class HealthProvider(BaseModel):
    name: str
    provider: str
    status: str
    mode: str

class HealthContract(BaseModel):
    status: str
    mode: str
    providers: list[HealthProvider]
    services: dict[str, str]
