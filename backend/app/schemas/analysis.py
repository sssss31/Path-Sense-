from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

class CargoType(str, Enum):
    general_goods="general_goods"; medicine="medicine"; food="food"
    emergency_supplies="emergency_supplies"; fragile_goods="fragile_goods"
    heavy_cargo="heavy_cargo"; other="other"

class LocationInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)

class AnalysisRequest(BaseModel):
    source: LocationInput
    destination: LocationInput
    cargo_type: CargoType = CargoType.medicine
    vehicle_type: str = "cargo_van"
    priority: str = "high"
    emergency_mode: bool = False
    departure_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Coordinate(BaseModel):
    lat: float
    lng: float

class Location(BaseModel):
    name: str
    coordinate: Coordinate

class Accessibility(BaseModel):
    score: int
    status: str
    factors: dict[str, int]
    confidence: float = 1.0
    confidence_reasons: list[str] = []
    confidence_factors: dict[str, float] = {}
    explanations: dict[str, list[str]] = {"negative": [], "positive": []}
    factor_weights: dict[str, float] = {}
    main_negative_factors: list[str] = []
    main_positive_factors: list[str] = []

class HazardCategoryExposure(BaseModel):
    zones_crossed: int = 0
    affected_distance_km: float = 0.0
    highest_severity: str = "none"
    label: str = ""

class LandslideFeatures(BaseModel):
    susceptibility_zones_crossed: int = 0
    highest_susceptibility: str = "none"
    susceptibility_affected_km: float = 0.0
    historical_incidents_within_2km: int = 0
    affected_distance_km: float = 0.0
    dataset_coverage: str = "unknown"
    inventory_coverage: str = "unknown"
    susceptibility_coverage: str = "unknown"

class FloodFeatures(BaseModel):
    historical_zones_crossed: int = 0
    affected_distance_km: float = 0.0
    highest_hazard: str = "none"
    dataset_coverage: str = "unknown"

class HazardExposure(BaseModel):
    """Normalized spatial hazard metrics for one route.

    `status` follows docs/risk-intelligence.md semantics: `intersections`,
    `no_intersection` (coverage confirmed none), `partial_coverage`,
    `unavailable` (no dataset/database) or `simulated` (demo mode).
    """
    status: str = "unavailable"
    provenance: str = "unavailable"
    zones_crossed: int = 0
    affected_distance_km: float = 0.0
    highest_severity: str = "none"
    historical_incidents_nearby: int = 0
    categories: dict[str, HazardCategoryExposure] = {}
    datasets: list[str] = []
    coverage_ratio: float | None = None
    reasons: list[str] = []
    landslide: LandslideFeatures = LandslideFeatures()
    flood: FloodFeatures = FloodFeatures()

class Risk(BaseModel):
    score: int
    level: str
    main_risks: list[str]

class Weather(BaseModel):
    temperature_c: float
    rainfall_mm: float
    rainfall_probability: int
    humidity: int
    wind_kph: float
    visibility_km: float
    condition: str
    data_status: str = "simulated"

class Terrain(BaseModel):
    elevation_m: int
    average_slope: float
    classification: str
    data_status: str = "simulated"

class DirectionStep(BaseModel):
    instruction: str
    road: str = ""
    distance_m: int = 0
    duration_s: int = 0
    location: Coordinate | None = None
    maneuver: str = ""

class RouteResult(BaseModel):
    id: str
    name: str
    distance_km: float
    duration_minutes: int
    eta_minutes: int
    geometry: list[Coordinate]
    road_quality: int
    accessibility: Accessibility
    risk: Risk
    weather: Weather
    terrain: Terrain
    recommended_vehicle: str
    vehicle_assessment: dict = {}
    directions: list[DirectionStep] = []
    hazards: HazardExposure = HazardExposure()
    recommended: bool = False
    rationale: str = ""

class DataSource(BaseModel):
    key: str
    name: str
    organization: str
    status: str                      # live | historical | estimated | simulated | unavailable | partial
    provenance: str
    coverage: str | None = None
    period: str | None = None
    updated_at: datetime | None = None
    attribution: str | None = None
    note: str | None = None

class AnalysisResponse(BaseModel):
    analysis_id: str
    generated_at: datetime
    source: Location
    destination: Location
    recommended_route_id: str
    routes: list[RouteResult]
    explanation: str
    data_disclaimer: str
    data_quality: dict[str, dict[str, str | None]] = {}
    data_sources: list[DataSource] = []
    mode: str = "demo"
    persistence_status: str = "not_requested"
