import asyncio
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.core.config import get_settings
from app.database.base import Base
from app.models import *
config=context.config;config.set_main_option("sqlalchemy.url",get_settings().database_url);target_metadata=Base.metadata
def offline():context.configure(url=config.get_main_option("sqlalchemy.url"),target_metadata=target_metadata,literal_binds=True,dialect_opts={"paramstyle":"named"})
def run_migrations(connection):
    context.configure(connection=connection,target_metadata=target_metadata)
    with context.begin_transaction():context.run_migrations()
async def online_run():
    engine=async_engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    async with engine.connect() as connection:await connection.run_sync(run_migrations)
    await engine.dispose()
if context.is_offline_mode():
    offline()
    with context.begin_transaction():context.run_migrations()
else:asyncio.run(online_run())
