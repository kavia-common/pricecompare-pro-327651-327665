import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.adapters.db import DbPool, close_db_pool, create_db_pool
from src.api.core.config import AppConfig, load_config
from src.api.routes.compare import router as compare_router
from src.api.scrapers.registry import ScraperRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

openapi_tags = [
    {
        "name": "System",
        "description": "Health and documentation endpoints.",
    },
    {
        "name": "Price Comparison",
        "description": "Compare prices across supported sites, plus query history endpoints.",
    },
]


def create_app() -> FastAPI:
    cfg = load_config()

    app = FastAPI(
        title="PriceCompare API",
        description=(
            "Backend for PriceCompare: scrapes supported sites and persists query/offer history in Postgres.\n\n"
            "Supported sites: gameloot.in, gamestheshop.com, gamenation.in, amazon.com, flipkart.com."
        ),
        version="1.0.0",
        openapi_tags=openapi_tags,
    )

    # CORS
    allow_origins = cfg.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins if allow_origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global singletons (flow dependencies)
    app.state.cfg = cfg
    app.state.registry = ScraperRegistry.default()
    app.state.db = None  # created on startup if configured

    # Routers
    app.include_router(compare_router)

    @app.on_event("startup")
    async def _startup() -> None:
        """Initialize DB pool if configured.

        Returns: None
        Side effects: opens DB connections.
        """
        app.state.db = await create_db_pool(app.state.cfg)

        # Wire dependencies for routes (avoid importing app inside routes)
        from src.api.routes import compare as compare_routes  # local import to avoid cycles

        def _get_cfg() -> AppConfig:
            return app.state.cfg

        def _get_registry() -> ScraperRegistry:
            return app.state.registry

        def _get_db() -> Optional[DbPool]:
            return app.state.db

        compare_routes.get_cfg = _get_cfg
        compare_routes.get_registry = _get_registry
        compare_routes.get_db = _get_db

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        """Gracefully close DB pool."""
        await close_db_pool(app.state.db)

    @app.get("/", tags=["System"], summary="Health check", operation_id="health_check")
    def health_check():
        """Simple health check.

        Returns a JSON object indicating the service is running.
        """
        return {"message": "Healthy"}

    return app


app = create_app()
