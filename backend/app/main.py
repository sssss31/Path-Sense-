import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.routes import router
from app.core.config import get_settings

log = logging.getLogger("pathsense.startup")
settings = get_settings()

def startup_diagnostics(s=None) -> dict:
    """Deployment-profile checks. Production with SQLite cannot persist geometry: fail or warn per policy."""
    s = s or get_settings()
    is_sqlite = s.database_url.startswith("sqlite")
    problems, warnings = [], []
    if s.app_env == "production":
        if is_sqlite:
            problems.append("APP_ENV=production with a SQLite DATABASE_URL: PostgreSQL/PostGIS is required for geospatial persistence.")
        if s.use_mock_data:
            warnings.append("APP_ENV=production with USE_MOCK_DATA=true: analyses will use simulated providers.")
        if s.jwt_secret in {"development-only-change-me", "replace-with-a-long-random-secret"}:
            problems.append("APP_ENV=production with a default JWT_SECRET.")
        if not s.openweather_api_key and not s.use_mock_data:
            warnings.append("OPENWEATHER_API_KEY missing: live weather will be unavailable.")
    elif is_sqlite:
        warnings.append("SQLite in use: route analyses will not persist and hazard intelligence is unavailable (demo mode only).")
    return {"profile": "production" if s.app_env == "production" else "demo" if s.use_mock_data else "live-development", "database": "sqlite" if is_sqlite else "postgresql", "problems": problems, "warnings": warnings}

async def bootstrap_database(diag: dict) -> dict:
    """Zero-setup demo: create tables on SQLite (Alembic targets PostGIS) and ensure the demo operator exists.

    On PostgreSQL nothing is created here (run `alembic upgrade head`); only the demo user is bootstrapped.
    """
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.database.base import Base
    from app.database.session import SessionLocal, engine
    from app.models import User
    state = {"tables_created": False, "demo_user": "skipped"}
    try:
        if diag["database"] == "sqlite" and settings.app_env != "production":
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            state["tables_created"] = True
        if settings.demo_user_email and settings.demo_user_password:
            async with SessionLocal() as session:
                existing = await session.scalar(select(User).where(User.email == settings.demo_user_email.lower()))
                if existing is None:
                    session.add(User(email=settings.demo_user_email.lower(), password_hash=hash_password(settings.demo_user_password), role="operator"))
                    await session.commit()
                    state["demo_user"] = "created"
                else:
                    state["demo_user"] = "exists"
    except Exception as exc:
        state["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        log.warning("startup_bootstrap_skipped: %s", state["error"])
    return state

@asynccontextmanager
async def lifespan(app: FastAPI):
    diag = startup_diagnostics()
    for w in diag["warnings"]:
        log.warning("startup_warning: %s", w)
    for p in diag["problems"]:
        log.error("startup_problem: %s", p)
    if diag["problems"] and settings.sqlite_in_production_policy == "fail":
        raise RuntimeError("Startup blocked: " + " | ".join(diag["problems"]))
    diag["bootstrap"] = await bootstrap_database(diag)
    log.info("startup_bootstrap: %s", diag["bootstrap"])
    app.state.diagnostics = diag
    yield

app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"name": settings.app_name, "docs": "/docs", "mode": "demo" if settings.use_mock_data else "live"}
