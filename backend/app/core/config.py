from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "PathSense API"
    app_env: str = "development"
    use_mock_data: bool = True
    database_url: str = "sqlite+aiosqlite:///./pathsense.db"
    jwt_secret: str = "development-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    gemini_timeout_seconds: float = 60.0
    openweather_api_key: str = ""
    osrm_base_url: str = "https://router.project-osrm.org"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    redis_url: str = ""
    demo_user_email: str = "demo@smartlogistics.local"
    demo_user_password: str = "Demo123!"
    persist_analyses: bool = True
    provider_timeout_seconds: float = 8.0
    allowed_origins: list[str] = ["http://localhost:3000"]
    # Production policy: SQLite cannot persist geometry. "fail" aborts startup, "warn" logs loudly.
    sqlite_in_production_policy: str = "fail"
    # External geospatial layers (remote WMS). Only hosts in this allowlist may ever be used.
    external_layer_allowed_hosts: list[str] = ["bhuvan-ras2.nrsc.gov.in", "bhuvan-vec1.nrsc.gov.in", "bhuvan-vec2.nrsc.gov.in", "bhuvan-app1.nrsc.gov.in"]
    bhuvan_flood_wms_url: str = "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe"
    bhuvan_flood_layers: list[str] = ["as_fld_2010", "as_fld_2009", "as_fld_2008", "as_fld_2007", "as_fld_2006", "as_fld_2005", "as_fld_2004", "as_fld_2003", "as_fld_2002", "as_fld_2001", "as_fld_2000", "as_fld_1999", "as_fld_1998"]
    bhuvan_flood_attribution: str = "Flood layers © NRSC/ISRO Bhuvan (Bhuvan OGC Web Service of Disaster Datasets - Flood)"
    external_layer_timeout_seconds: float = 20.0
    external_layers_enabled: bool = True
    scoring_weights: dict[str, float] = {
        "road_quality": .25, "weather": .20, "terrain": .20,
        "historical_risk": .15, "current_disruption": .10,
        "vehicle_suitability": .10,
    }
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Accept managed-database URLs (Render/Neon/Supabase/Heroku style) and convert them for asyncpg.

        postgres://... or postgresql://... -> postgresql+asyncpg://...; `sslmode=require` -> `ssl=require`.
        """
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value[len("postgres://"):]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://"):]
        if "+asyncpg" in value and "sslmode=" in value:
            value = value.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer").replace("sslmode=disable", "ssl=disable")
        return value

@lru_cache
def get_settings() -> Settings:
    return Settings()
