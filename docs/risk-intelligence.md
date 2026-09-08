# Risk intelligence

`Route geometry → dataset-registry coverage check → PostGIS risk-zone intersection → historical-incident proximity → sampled weather → terrain → vehicle suitability → risk engine → accessibility score → confidence → decision engine`

Risk zones use `ST_Intersects`; affected distance uses the geography length of `ST_Intersection`; incidents use `ST_DWithin` with a two-kilometre buffer. Results are normalized into counts, category, highest severity and affected kilometres (`HazardExposure`) before entering business logic. Confirmed exposure adds bounded points to the rule-based risk score (`HAZARD_RISK_POINTS` in `app/services/engines.py`); unavailable data adds nothing and is surfaced through confidence instead.

## Route hazard features (v3)
Hazard exposure is normalized per layer family before it reaches the risk engine:

```json
{"landslide": {"susceptibility_zones_crossed": 2, "highest_susceptibility": "high", "historical_incidents_within_2km": 5, "affected_distance_km": 4.3, "inventory_coverage": "full", "susceptibility_coverage": "full"},
 "flood": {"historical_zones_crossed": 1, "affected_distance_km": 2.1, "dataset_coverage": "full"}}
```

Inventory (observed events) and susceptibility (terrain classification) are separate intelligence layers with separate, centrally configured contributions (`RISK_CONTRIBUTIONS`): landslide susceptibility, historical landslide proximity, historical flood exposure, rainfall, visibility, terrain slope and road quality; vehicle suitability enters the accessibility score. Explanations (`accessibility.explanations.negative/positive`) are generated from the same normalized values.

Coverage (`calculate_dataset_route_coverage`) returns `full`, `partial`, `none` or `unknown` per dataset and feeds confidence v3, which is factor-specific (`accessibility.confidence_factors`: routing, weather, terrain, landslide_inventory, landslide_susceptibility, flood_hazard, road_condition) and applies an age penalty to historical datasets older than ten years. Confidence never changes the accessibility score.

## Data-state semantics
| `hazard_status` | Meaning |
|---|---|
| `intersections` | dataset coverage exists and the route crosses hazard geometry |
| `no_intersection` | coverage exists and PostGIS confirmed no crossing |
| `partial_coverage` | the route extends beyond every imported dataset's `coverage_bbox`; confidence drops with the reason "Historical landslide dataset does not cover the full route." |
| `unavailable` | no PostGIS session or no imported dataset — exposure is unknown, not zero |
| `simulated` | demo mode deterministic seed; never used in live mode |

Accessibility measures modeled reachability; confidence separately measures evidence coverage and never reduces the accessibility score merely because data is missing. Historical incidents indicate prior exposure, not current closure. Explanations (deterministic or Gemini) always include the hazard data state and never rephrase unavailable data as safe conditions. Labels follow provenance: "Historical Landslide Zone", "Flood-Prone Area", and alert wording only for live sources. Vocabulary, severity/category mappings, transitions and confidence weights are centralized in `app/core/domain.py`.
