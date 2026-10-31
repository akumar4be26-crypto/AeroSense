from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_config
from app.core.env import get_env
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.database.session import init_db

logger = logging.getLogger("aeris")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    config = get_config()  # raises ConfigError on invalid config: fail fast at startup
    env = get_env()
    init_db()
    logger.info("%s %s started (%s)", config.settings.app.name, config.settings.app.version, env.environment)
    yield


def create_app() -> FastAPI:
    config = get_config()
    app = FastAPI(
        title=f"{config.settings.app.name} API",
        description=config.settings.app.full_name,
        version=config.settings.app.version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_env().cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
