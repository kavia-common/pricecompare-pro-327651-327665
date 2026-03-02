from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.adapters.db import DbPool, fetch_query_history, fetch_query_offers
from src.api.core.config import AppConfig
from src.api.flows.compare_prices_flow import ComparePricesRequest, run_compare_prices_flow
from src.api.schemas.compare import (
    ComparePricesRequestModel,
    ComparePricesResponseModel,
    QueryHistoryResponse,
    QueryOffersResponse,
)
from src.api.scrapers.registry import ScraperRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Price Comparison"])


def get_cfg() -> AppConfig:
    # Imported and set in app.state; this fallback exists for typing.
    raise RuntimeError("Config dependency not wired")


def get_db() -> Optional[DbPool]:
    raise RuntimeError("DB dependency not wired")


def get_registry() -> ScraperRegistry:
    raise RuntimeError("Registry dependency not wired")


# PUBLIC_INTERFACE
@router.post(
    "/comparePrices",
    response_model=ComparePricesResponseModel,
    summary="Compare prices across supported sites",
    description=(
        "Scrapes/searches supported sites (gameloot, gamestheshop, gamenation, amazon, flipkart) "
        "and returns aggregated offers with structured per-site errors. Results are persisted to Postgres when configured."
    ),
    operation_id="compare_prices",
)
async def compare_prices_endpoint(
    payload: ComparePricesRequestModel,
    cfg: AppConfig = Depends(get_cfg),
    db: Optional[DbPool] = Depends(get_db),
    registry: ScraperRegistry = Depends(get_registry),
) -> ComparePricesResponseModel:
    """Compare prices for a query or URL.

    Parameters:
      - payload: ComparePricesRequestModel
      - cfg: AppConfig (env-based)
      - db: optional DbPool (Postgres pool)
      - registry: ScraperRegistry

    Returns:
      - ComparePricesResponseModel including offers, cheapestOffer, siteErrors, and queryId (if persisted).
    """
    if payload.queryType == "text" and not payload.query:
        raise HTTPException(status_code=422, detail="query is required when queryType='text'")
    if payload.queryType == "url" and not payload.url:
        raise HTTPException(status_code=422, detail="url is required when queryType='url'")

    flow_req = ComparePricesRequest(
        query=payload.query,
        url=payload.url,
        query_type=payload.queryType,
        sites=payload.sites,
        max_results_per_site=payload.maxResultsPerSite,
    )
    result = await run_compare_prices_flow(cfg=cfg, db=db, registry=registry, req=flow_req)

    return ComparePricesResponseModel(
        success=result.success,
        queryId=result.query_id,
        offers=result.offers,
        cheapestOffer=result.cheapest_offer,
        siteErrors=result.site_errors,
    )


# PUBLIC_INTERFACE
@router.get(
    "/queries",
    response_model=QueryHistoryResponse,
    summary="Get recent query history",
    description="Returns recent saved queries from Postgres with offer counts.",
    operation_id="get_query_history",
)
async def get_queries_endpoint(
    limit: int = Query(default=20, ge=1, le=100, description="Max number of queries to return."),
    offset: int = Query(default=0, ge=0, description="Offset for pagination."),
    db: Optional[DbPool] = Depends(get_db),
) -> QueryHistoryResponse:
    """List recent queries (requires Postgres configured)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    items = await fetch_query_history(db, limit=limit, offset=offset)
    return QueryHistoryResponse(items=items, limit=limit, offset=offset)


# PUBLIC_INTERFACE
@router.get(
    "/queries/{query_id}/offers",
    response_model=QueryOffersResponse,
    summary="Get offers for a query",
    description="Returns offers persisted for a given query_id.",
    operation_id="get_query_offers",
)
async def get_query_offers_endpoint(
    query_id: int,
    db: Optional[DbPool] = Depends(get_db),
) -> QueryOffersResponse:
    """Fetch offers for a specific query_id (requires Postgres configured)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    offers = await fetch_query_offers(db, query_id=query_id)
    return QueryOffersResponse(queryId=query_id, offers=offers)
