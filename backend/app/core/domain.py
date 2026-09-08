"""Central, editable domain rules.

Everything here is intentionally plain data so operators can tune behaviour
without touching service code. Services import from this module instead of
declaring their own constants.
"""

# --- Delivery lifecycle -----------------------------------------------------
DELIVERY_STATUSES = ["planned", "in_transit", "delayed", "completed", "cancelled"]

# Source of truth for allowed status transitions. The frontend never assumes a
# transition is valid; it reads `allowed_transitions` from the API.
DELIVERY_TRANSITIONS: dict[str, list[str]] = {
    "planned": ["in_transit", "cancelled"],
    "in_transit": ["delayed", "completed", "cancelled"],
    "delayed": ["in_transit", "completed", "cancelled"],
    "completed": [],
    "cancelled": [],
}

# Transitions into these statuses require an explicit confirmation step in the UI.
SENSITIVE_DELIVERY_STATUSES = ["completed", "cancelled"]

DELIVERY_PRIORITIES = ["low", "medium", "high", "critical"]

# --- Hazard vocabulary ------------------------------------------------------
HAZARD_CATEGORIES = ["landslide", "flood", "road_closure", "construction", "bridge_risk", "other"]

# Numeric severity 1..5 -> label used in API responses and UI.
SEVERITY_LABELS = {1: "low", 2: "low", 3: "moderate", 4: "high", 5: "critical"}

# Normalisation tables used by the dataset importer (case-insensitive keys).
SEVERITY_MAPPING = {
    "very_low": 1, "very low": 1, "minor": 1, "low": 1, "l": 1,
    "medium": 3, "moderate": 3, "m": 3, "med": 3,
    "severe": 4, "high": 4, "h": 4,
    "extreme": 5, "very_high": 5, "very high": 5, "critical": 5, "vh": 5,
}
CATEGORY_MAPPING = {
    "landslide": "landslide", "landslides": "landslide", "slide": "landslide", "debris flow": "landslide",
    "rockfall": "landslide", "mudslide": "landslide", "slope failure": "landslide",
    "flood": "flood", "flooding": "flood", "inundation": "flood", "flash flood": "flood", "flood-prone": "flood",
    "road closure": "road_closure", "road_closure": "road_closure", "closure": "road_closure", "blocked": "road_closure",
    "bridge": "bridge_risk", "bridge_risk": "bridge_risk", "bridge damage": "bridge_risk",
    "construction": "construction", "roadwork": "construction", "roadworks": "construction",
}

# Human-facing labels: historical/static datasets must never read as live alerts.
HAZARD_LABELS = {
    "historical": {"landslide": "Historical Landslide Zone", "flood": "Historical Flood Zone", "road_closure": "Past Road Closure",
                    "construction": "Recorded Construction Zone", "bridge_risk": "Recorded Bridge Risk", "other": "Historical Hazard Zone"},
    "estimated": {"landslide": "Landslide-Susceptible Area", "flood": "Flood-Prone Area", "road_closure": "Closure-Prone Segment",
                   "construction": "Construction-Prone Segment", "bridge_risk": "Bridge Risk Area", "other": "Hazard-Prone Area"},
    "simulated": {"landslide": "Simulated Landslide Zone (demo)", "flood": "Simulated Flood Zone (demo)", "road_closure": "Simulated Closure (demo)",
                   "construction": "Simulated Construction (demo)", "bridge_risk": "Simulated Bridge Risk (demo)", "other": "Simulated Hazard (demo)"},
    "live": {"landslide": "Live Landslide Alert", "flood": "Current Flood", "road_closure": "Current Road Closure",
              "construction": "Active Construction", "bridge_risk": "Active Bridge Restriction", "other": "Live Hazard Alert"},
}

def hazard_label(category: str, provenance: str) -> str:
    table = HAZARD_LABELS.get(provenance, HAZARD_LABELS["historical"])
    return table.get(category, table["other"])

# --- Dataset registry -------------------------------------------------------
PROVENANCE_TYPES = ["live", "historical", "estimated", "simulated"]
DATASET_STATUSES = ["registered", "validated", "imported", "failed", "disabled"]
DATASET_DATA_TYPES = ["risk_zones", "incidents"]
# Only these provenance types may be flagged is_live; imported files never become live automatically.
LIVE_CAPABLE_PROVENANCE = ["live"]

# --- Hazard data-state semantics (see docs/risk-intelligence.md) -------------
HAZARD_STATUS_INTERSECTION = "intersections"      # coverage exists and the route crosses hazard geometry
HAZARD_STATUS_NO_INTERSECTION = "no_intersection"  # coverage exists and the query confirmed none
HAZARD_STATUS_PARTIAL = "partial_coverage"         # route extends beyond imported dataset coverage
HAZARD_STATUS_UNAVAILABLE = "unavailable"          # no spatial database / no dataset at all
HAZARD_STATUS_SIMULATED = "simulated"              # demo mode deterministic seed

# --- Confidence -------------------------------------------------------------
CONFIDENCE_STATUS_SCORE = {"live": 1.0, "cached": 0.9, "historical": 0.72, "partial": 0.5, "estimated": 0.62, "simulated": 0.55, "unavailable": 0.0}
CONFIDENCE_WEIGHTS = {"routing": 0.25, "weather": 0.20, "terrain": 0.15, "landslide": 0.18, "road_condition": 0.22}
CONFIDENCE_LABELS = {"routing": "routing coverage", "weather": "route weather coverage", "terrain": "terrain coverage",
                     "landslide": "hazard dataset coverage", "road_condition": "current road-condition feed"}

# --- Reports ----------------------------------------------------------------
REPORT_RANGES = {"7d": 7, "30d": 30, "90d": 90, "365d": 365}
DEFAULT_REPORT_RANGE = "30d"
# Persisted risk warnings (AnalyzedRoute.warnings) are normalised into these factor labels.
RISK_FACTOR_LABELS = {
    "Heavy rainfall along exposed sections": "Heavy rainfall",
    "Intermittent rainfall may reduce traction": "Intermittent rainfall",
    "Steep landslide-prone terrain": "Steep terrain",
    "Sustained mountain gradients": "Steep terrain",
    "Variable road surface quality": "Poor road suitability",
    "Low visibility": "Low visibility",
    "Historical landslide zone exposure": "Landslide exposure",
    "Historical flood zone exposure": "Flood exposure",
    "Historical incidents near route": "Historical incidents",
    "No material route risks detected": None,
    "No material risk factors detected from available data": None,
}

# --- Spatial ----------------------------------------------------------------
INCIDENT_BUFFER_METRES = 2000
HAZARD_NEAR_METRES = 2000

# --- Phase 3: authoritative hazard integration ------------------------------
# Layer families a dataset can belong to. Inventory (observed events) and
# susceptibility (terrain classification) are deliberately separate layers.
LAYER_TYPES = ["landslide_inventory", "landslide_susceptibility", "flood_hazard", "flood_inundation", "hazard_zones", "incidents", "current_events"]
LAYER_TYPE_LABELS = {
    "landslide_inventory": "Historical Landslide Inventory", "landslide_susceptibility": "Landslide Susceptibility",
    "flood_hazard": "Historical Flood Hazard", "flood_inundation": "Historical Flood Inundation",
    "hazard_zones": "Historical Hazard Zones", "incidents": "Historical Incidents", "current_events": "Current Event Observation",
}
# Susceptibility source classes -> platform severity (1..5). Original class is always kept in metadata.
SUSCEPTIBILITY_MAPPING = {
    "very_low": 1, "very low": 1, "vl": 1, "1": 1,
    "low": 2, "l": 2, "2": 2,
    "moderate": 3, "medium": 3, "m": 3, "3": 3,
    "high": 4, "h": 4, "4": 4,
    "very_high": 5, "very high": 5, "vh": 5, "critical": 5, "5": 5,
}
SUSCEPTIBILITY_LABELS = {1: "low", 2: "low", 3: "moderate", 4: "high", 5: "critical"}

# Coverage status of a dataset relative to a route.
COVERAGE_FULL, COVERAGE_PARTIAL, COVERAGE_NONE, COVERAGE_UNKNOWN = "full", "partial", "none", "unknown"
COVERAGE_FULL_THRESHOLD = 0.98
COVERAGE_PARTIAL_THRESHOLD = 0.05

# Risk engine v3: separate, centrally editable contributions (points added to the 0-100 risk score).
RISK_CONTRIBUTIONS = {
    "rainfall": {"heavy_mm": 20, "heavy_points": 28, "moderate_mm": 10, "moderate_points": 15},
    "visibility": {"threshold_km": 5, "points": 12},
    "terrain": {"steep_slope": 12, "steep_points": 24, "sustained_slope": 9, "sustained_points": 12},
    "road": {"poor_quality": 70, "points": 18},
    "landslide_susceptibility": {"per_zone": 3, "critical": 14, "high": 10, "moderate": 5, "low": 1, "cap": 22},
    "historical_landslide_proximity": {"per_incident": 2, "threshold": 1, "cap": 12},
    "historical_flood_exposure": {"base": 4, "per_km": 2, "cap": 14},
    "base": 8, "cap": 100,
}
# Confidence v3: factor-specific weights and the score for each data state.
CONFIDENCE_FACTORS = {
    "routing": 0.20, "weather": 0.18, "terrain": 0.12,
    "landslide_inventory": 0.14, "landslide_susceptibility": 0.14, "flood_hazard": 0.10, "road_condition": 0.12,
}
CONFIDENCE_FACTOR_LABELS = {
    "routing": "Routing", "weather": "Weather", "terrain": "Terrain", "landslide_inventory": "Landslide inventory",
    "landslide_susceptibility": "Landslide susceptibility", "flood_hazard": "Flood hazard", "road_condition": "Road condition",
}
# Provenance -> base confidence, then multiplied by coverage (full 1.0, partial 0.5, none/unknown 0).
CONFIDENCE_PROVENANCE_BASE = {"live": 1.0, "cached": 0.9, "historical": 0.9, "estimated": 0.75, "simulated": 0.55, "unavailable": 0.0}
CONFIDENCE_COVERAGE_FACTOR = {COVERAGE_FULL: 1.0, COVERAGE_PARTIAL: 0.5, COVERAGE_NONE: 0.0, COVERAGE_UNKNOWN: 0.35}
DATASET_AGE_PENALTY_YEARS = 10   # historical datasets older than this lose a little confidence
DATASET_AGE_PENALTY = 0.15

# Human wording for flood layers (claim rule). Only current, timestamped observations may use alert wording.
FLOOD_LAYER_WORDING = {"flood_hazard": "Historical Flood Hazard", "flood_inundation": "Historical Flood Inundation", "current_events": "Current Flood/Inundation Observation"}

# User reports are never treated as verified closures until confirmed.
USER_REPORT_VERIFICATION = ["unverified", "verified", "expired"]
USER_REPORT_LABEL = {"unverified": "Reported Road Issue", "verified": "Verified Road Issue", "expired": "Expired Report"}

# --- Vehicles (used for requested-vehicle assessment and recommendations) ----
VEHICLE_PROFILES = {
    "cargo_van": {"name": "Cargo Van", "max_slope": 9, "min_road_quality": 70, "base_score": 88, "cargo": ["general_goods", "food", "fragile_goods", "medicine", "other"]},
    "emergency_cargo_van": {"name": "Emergency Cargo Van", "max_slope": 11, "min_road_quality": 65, "base_score": 90, "cargo": ["medicine", "emergency_supplies", "fragile_goods"]},
    "pickup_truck": {"name": "Pickup Truck", "max_slope": 12, "min_road_quality": 55, "base_score": 86, "cargo": ["general_goods", "food", "heavy_cargo", "other", "emergency_supplies"]},
    "4x4_utility": {"name": "4x4 Utility Vehicle", "max_slope": 18, "min_road_quality": 40, "base_score": 92, "cargo": ["medicine", "emergency_supplies", "general_goods", "food", "fragile_goods", "other"]},
    "light_truck": {"name": "Light Truck", "max_slope": 8, "min_road_quality": 72, "base_score": 84, "cargo": ["heavy_cargo", "general_goods", "food"]},
}
VEHICLE_ALIASES = {"4x4 utility vehicle": "4x4_utility", "4x4": "4x4_utility", "emergency cargo van": "emergency_cargo_van", "cargo van": "cargo_van", "pickup truck": "pickup_truck", "light truck": "light_truck", "auto": None, "auto-select": None}
SUITABILITY_PENALTIES = {"slope_over": 6, "road_under": 4, "cargo_mismatch": 12, "high_risk_non_4x4": 10, "floor": 20}

# --- Notifications -----------------------------------------------------------
NOTIFICATION_RULES = {"departing_within_hours": 6, "recent_high_risk_days": 3, "max_items": 20}

# --- Geocoding --------------------------------------------------------------
# Search bias for the North-East India corridor (min_lon, min_lat, max_lon, max_lat). Results outside are still accepted.
GEOCODE_VIEWBOX = [88.0, 21.5, 97.5, 29.5]
GEOCODE_FALLBACK_SUFFIXES = [", India", ", Assam, India", ", Meghalaya, India"]
GEOCODE_SUGGEST_LIMIT = 6
