"""Geometry column type that degrades gracefully without PostGIS.

The process talks to one database. When it is PostgreSQL the models use the
real PostGIS ``Geometry`` (spatial index, ST_* functions, GeoAlchemy2 DDL
events). When it is SQLite (zero-setup demo/offline mode) the same columns are
plain TEXT holding WKT: GeoAlchemy2 never sees them, so no SpatiaLite is needed.
Every spatial query is already guarded by ``spatial_available`` and reports
hazard data as unavailable rather than zero.
"""
import os

from sqlalchemy import Text

from app.core.config import get_settings

def _postgres_configured() -> bool:
    urls = [get_settings().database_url, os.environ.get("TEST_DATABASE_URL", "")]
    return any(u.startswith("postgresql") for u in urls)

SPATIAL_BACKEND = "postgis" if _postgres_configured() else "sqlite-text"

def spatial(geometry_type: str):
    if SPATIAL_BACKEND == "postgis":
        from geoalchemy2 import Geometry
        return Geometry(geometry_type, srid=4326, spatial_index=True)
    return Text()

def is_spatial_dialect(session) -> bool:
    try:
        return session.get_bind().dialect.name == "postgresql"
    except Exception:
        return False
