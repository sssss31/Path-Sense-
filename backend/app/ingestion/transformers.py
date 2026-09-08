"""Predefined, safe field transformers for dataset mapping configs.

Mapping files reference transformers by name (optionally with arguments).
There is deliberately no way to execute arbitrary code from a mapping file.

Spec forms accepted in a mapping file:
    "lowercase"                       -> plain name
    {"name": "null_replace", "value": "other"}
    {"name": "severity_map", "table": {"A": 5}}
"""
from datetime import datetime, timezone

from app.core.domain import CATEGORY_MAPPING, SEVERITY_MAPPING, SUSCEPTIBILITY_MAPPING

class TransformError(ValueError):
    pass

def _lower(value, **_):
    return value.lower() if isinstance(value, str) else value

def _upper(value, **_):
    return value.upper() if isinstance(value, str) else value

def _strip(value, **_):
    return value.strip() if isinstance(value, str) else value

def _to_int(value, **_):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise TransformError(f"cannot convert {value!r} to integer")

def _to_float(value, **_):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise TransformError(f"cannot convert {value!r} to float")

def _parse_date(value, formats=None, **_):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    for fmt in formats or []:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    if text.isdigit() and len(text) == 4:  # year only
        return datetime(int(text), 1, 1, tzinfo=timezone.utc)
    raise TransformError(f"unparseable date {value!r}")

def _severity_map(value, table=None, **_):
    """Text severity -> 1..5 using the central table plus optional overrides."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _clamp_severity(value)
    mapping = {**SEVERITY_MAPPING, **{str(k).strip().lower(): v for k, v in (table or {}).items()}}
    key = str(value).strip().lower()
    if key in mapping:
        return int(mapping[key])
    try:
        return _clamp_severity(float(key))
    except ValueError:
        raise TransformError(f"unknown severity {value!r}")

def _susceptibility_map(value, table=None, **_):
    """Susceptibility class (very_low..very_high) -> platform severity 1..5 (central table, optional overrides)."""
    if value in (None, ""):
        return None
    mapping = {**SUSCEPTIBILITY_MAPPING, **{str(k).strip().lower(): v for k, v in (table or {}).items()}}
    key = str(value).strip().lower().replace("-", " ").replace("_", " ")
    for candidate in (key, key.replace(" ", "_")):
        if candidate in mapping:
            return int(mapping[candidate])
    try:
        return _clamp_severity(float(key))
    except ValueError:
        raise TransformError(f"unknown susceptibility class {value!r}")

def _category_map(value, table=None, default="other", **_):
    if value in (None, ""):
        return default
    mapping = {**CATEGORY_MAPPING, **{str(k).strip().lower(): v for k, v in (table or {}).items()}}
    key = str(value).strip().lower()
    return mapping.get(key, default)

def _int_to_severity(value, scale=None, **_):
    """Map an integer class on an arbitrary scale onto 1..5. `scale` = [min, max] of the source classes."""
    if value in (None, ""):
        return None
    number = float(value)
    if scale:
        low, high = float(scale[0]), float(scale[1])
        if high <= low:
            raise TransformError("scale must be [min, max] with max > min")
        number = 1 + (number - low) / (high - low) * 4
    return _clamp_severity(number)

def _clamp_severity(value, **_):
    if value in (None, ""):
        return None
    return max(1, min(5, int(round(float(value)))))

def _null_replace(current, **kw):
    """Replace null/empty values. Argument in mapping file: {"name": "null_replace", "value": "other"}."""
    replacement = kw.get("value", kw.get("replacement"))
    return replacement if current in (None, "") else current

def _default(current, **kw):
    return _null_replace(current, **kw)

TRANSFORMERS = {
    "lowercase": _lower, "uppercase": _upper, "strip": _strip, "to_int": _to_int, "to_float": _to_float,
    "parse_date": _parse_date, "severity_map": _severity_map, "category_map": _category_map,
    "int_to_severity": _int_to_severity, "susceptibility_map": _susceptibility_map, "clamp_severity": _clamp_severity, "null_replace": _null_replace, "default": _default,
}

def apply_transforms(value, specs: list) -> object:
    for spec in specs or []:
        if isinstance(spec, str):
            name, args = spec, {}
        elif isinstance(spec, dict) and "name" in spec:
            name, args = spec["name"], {k: v for k, v in spec.items() if k != "name"}
        else:
            raise TransformError(f"invalid transform spec {spec!r}")
        fn = TRANSFORMERS.get(name)
        if fn is None:
            raise TransformError(f"unknown transformer {name!r}; allowed: {sorted(TRANSFORMERS)}")
        value = fn(value, **args)
    return value
