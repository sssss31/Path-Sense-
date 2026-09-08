"""Confidence engine v3.

Confidence measures evidence coverage per factor and is deliberately
independent from the accessibility score: missing, partial or old data lowers
confidence, never the score. Factor weights, provenance bases and coverage
multipliers live in app.core.domain so they stay editable in one place.

`confidence_for(data_quality)` keeps the v2 signature used by persisted
analyses; `confidence_v3(...)` returns per-factor values.
"""
from datetime import datetime, timezone

from app.core.domain import (CONFIDENCE_COVERAGE_FACTOR, CONFIDENCE_FACTOR_LABELS, CONFIDENCE_FACTORS, CONFIDENCE_LABELS, CONFIDENCE_PROVENANCE_BASE,
                             CONFIDENCE_STATUS_SCORE, CONFIDENCE_WEIGHTS, COVERAGE_FULL, COVERAGE_NONE, COVERAGE_UNKNOWN, DATASET_AGE_PENALTY, DATASET_AGE_PENALTY_YEARS)

DEGRADED = {"unavailable", "simulated", "estimated", "partial"}

def confidence_for(data_quality: dict) -> tuple[float, list[str]]:
    """v2-compatible overall confidence from a data_quality mapping."""
    score = 0.0
    reasons: list[str] = []
    for key, weight in CONFIDENCE_WEIGHTS.items():
        entry = data_quality.get(key, {}) or {}
        status = entry.get("status", "unavailable")
        score += CONFIDENCE_STATUS_SCORE.get(status, 0.0) * weight
        if status in DEGRADED:
            reasons.append(entry.get("reason") or CONFIDENCE_LABELS[key])
    return round(score, 2), reasons

def hazard_quality(exposure) -> dict:
    """Translate a HazardExposure into a data_quality entry for the landslide/hazard key."""
    status = exposure.status
    if status == "simulated":
        return {"status": "simulated", "provider": "demo", "reason": "Hazard zones are simulated demo evidence."}
    if status == "unavailable":
        return {"status": "unavailable", "provider": "none", "reason": exposure.reasons[0] if exposure.reasons else "Hazard data unavailable."}
    if status == "partial_coverage":
        return {"status": "partial", "provider": ", ".join(exposure.datasets) or "dataset registry", "reason": "Historical landslide dataset does not cover the full route."}
    return {"status": exposure.provenance if exposure.provenance in CONFIDENCE_STATUS_SCORE else "historical", "provider": ", ".join(exposure.datasets) or "dataset registry"}

def factor_confidence(provenance: str, coverage: str = COVERAGE_FULL, period_end: datetime | None = None) -> float:
    """Confidence of one factor: provenance base × coverage multiplier, minus an age penalty for old historical data."""
    base = CONFIDENCE_PROVENANCE_BASE.get(provenance, 0.0)
    value = base * CONFIDENCE_COVERAGE_FACTOR.get(coverage, 0.0)
    if provenance == "historical" and period_end is not None:
        age_years = (datetime.now(timezone.utc) - period_end).days / 365.25
        if age_years > DATASET_AGE_PENALTY_YEARS:
            value = max(0.0, value - DATASET_AGE_PENALTY)
    return round(value, 2)

def confidence_v3(factors: dict[str, dict]) -> tuple[float, dict[str, float], list[str]]:
    """factors: {key: {"provenance": str, "coverage": str, "period_end": datetime|None, "reason": str|None}}.

    Returns (overall, per-factor confidence, reasons). Unknown factors count as unavailable.
    """
    per_factor: dict[str, float] = {}
    reasons: list[str] = []
    overall = 0.0
    for key, weight in CONFIDENCE_FACTORS.items():
        spec = factors.get(key) or {"provenance": "unavailable", "coverage": COVERAGE_NONE}
        value = factor_confidence(spec.get("provenance", "unavailable"), spec.get("coverage", COVERAGE_FULL), spec.get("period_end"))
        per_factor[key] = value
        overall += value * weight
        if value < 0.6:
            reasons.append(spec.get("reason") or f"{CONFIDENCE_FACTOR_LABELS[key]} evidence is {spec.get('provenance', 'unavailable')} with {spec.get('coverage', COVERAGE_UNKNOWN)} coverage.")
    return round(overall, 2), per_factor, reasons
