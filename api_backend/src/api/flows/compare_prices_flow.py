from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.api.adapters.db import DbPool, persist_query_and_offers
from src.api.core.config import AppConfig
from src.api.core.scrape_utils import NormalizedOffer, ScrapeContext
from src.api.scrapers.base import SiteScrapeError
from src.api.scrapers.registry import ScraperRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ComparePricesRequest:
    """Request contract for ComparePricesFlow."""

    query: Optional[str]
    url: Optional[str]
    query_type: str  # "text" or "url"
    sites: Optional[List[str]]  # list of site codes, or None for default
    max_results_per_site: int = 10


@dataclass(frozen=True)
class ComparePricesResult:
    """Result contract for ComparePricesFlow."""

    success: bool
    query_id: Optional[int]
    offers: List[Dict[str, Any]]
    site_errors: List[Dict[str, Any]]
    cheapest_offer: Optional[Dict[str, Any]]


def _offer_to_api_dict(o: NormalizedOffer) -> Dict[str, Any]:
    return {
        "site": {"code": o.site_code},
        "productName": o.product_name,
        "productUrl": o.product_url,
        "imageUrl": o.image_url,
        "currency": o.currency,
        "priceNumeric": o.price_numeric,
        "priceText": o.price_text,
        "availability": o.availability,
        "shippingText": o.shipping_text,
        "rawData": o.raw_data,
    }


def _error_to_api_dict(e: SiteScrapeError) -> Dict[str, Any]:
    return {
        "site": {"code": e.site_code},
        "message": e.message,
        "type": e.error_type,
        "url": e.url,
        "details": e.details or {},
    }


async def _scrape_one_site(
    scraper: Any, *, req: ComparePricesRequest, ctx: ScrapeContext
) -> Tuple[List[NormalizedOffer], Optional[SiteScrapeError]]:
    try:
        if req.query_type == "url" and req.url:
            offers = await scraper.from_url(req.url, ctx)
        else:
            offers = await scraper.search(req.query or "", ctx)
        return offers[: req.max_results_per_site], None
    except httpx.HTTPStatusError as exc:
        return [], SiteScrapeError(
            site_code=scraper.site_code,
            message=f"HTTP error {exc.response.status_code}",
            error_type="http_status",
            url=str(exc.request.url) if exc.request else None,
            details={"responseTextSample": (exc.response.text or "")[:500]},
        )
    except httpx.HTTPError as exc:
        return [], SiteScrapeError(
            site_code=scraper.site_code,
            message="Network/HTTP client error while fetching",
            error_type="http_error",
            url=getattr(exc.request, "url", None) if hasattr(exc, "request") else None,
            details={"error": str(exc)},
        )
    except Exception as exc:  # boundary: add context but don't swallow
        return [], SiteScrapeError(
            site_code=scraper.site_code,
            message="Unexpected error while parsing/scraping",
            error_type="unexpected",
            details={"error": str(exc)},
        )


def _pick_cheapest(offers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    priced = [o for o in offers if isinstance(o.get("priceNumeric"), (int, float))]
    if not priced:
        return None
    return sorted(priced, key=lambda x: x["priceNumeric"])[0]


# PUBLIC_INTERFACE
async def run_compare_prices_flow(
    *,
    cfg: AppConfig,
    db: Optional[DbPool],
    registry: ScraperRegistry,
    req: ComparePricesRequest,
) -> ComparePricesResult:
    """ComparePricesFlow: scrape offers across supported sites and persist results.

    Contract:
      - Inputs:
          - cfg: AppConfig (env-based)
          - db: optional DbPool (None allowed)
          - registry: ScraperRegistry
          - req: ComparePricesRequest
      - Outputs: ComparePricesResult with:
          - offers: list of normalized offers (best-effort)
          - site_errors: list of per-site structured errors
          - query_id: persisted query id if DB configured and persistence succeeds
      - Errors: does not raise on per-site scraping failures; only raises on
        programmer/configuration errors at boundary (should be rare).
      - Side effects:
          - network requests to target sites
          - optional inserts into Postgres tables (queries/offers/price_history)

    Observability:
      - logs start/end with key parameters and counts
      - per-site failures captured into site_errors
    """
    sites = req.sites or registry.all_site_codes()
    ctx = ScrapeContext(timeout_seconds=cfg.scrape_timeout_seconds, user_agent=cfg.scrape_user_agent)

    logger.info(
        "ComparePricesFlow:start query_type=%s sites=%s",
        req.query_type,
        ",".join(sites),
    )

    all_offers: List[NormalizedOffer] = []
    site_errors: List[SiteScrapeError] = []

    for site_code in sites:
        scraper = registry.get(site_code)
        if not scraper:
            site_errors.append(
                SiteScrapeError(
                    site_code=site_code,
                    message="Site not supported by scraper registry",
                    error_type="unsupported_site",
                )
            )
            continue

        offers, err = await _scrape_one_site(scraper, req=req, ctx=ctx)
        all_offers.extend(offers)
        if err:
            site_errors.append(err)

    api_offers = [_offer_to_api_dict(o) for o in all_offers]
    cheapest = _pick_cheapest(api_offers)

    persisted_query_id: Optional[int] = None
    if db is not None:
        try:
            persisted_query_id = await persist_query_and_offers(
                db,
                query_text=req.query if req.query_type == "text" else None,
                query_url=req.url if req.query_type == "url" else None,
                query_type=req.query_type,
                status="completed" if not site_errors else "partial",
                offers=[
                    {
                        "site_code": o.site_code,
                        "product_name": o.product_name,
                        "product_url": o.product_url,
                        "image_url": o.image_url,
                        "currency": o.currency,
                        "price_numeric": o.price_numeric,
                        "price_text": o.price_text,
                        "availability": o.availability,
                        "shipping_text": o.shipping_text,
                        "raw_data": o.raw_data,
                    }
                    for o in all_offers
                ],
            )
        except Exception as exc:
            # DB persistence is secondary; report as a structured site_error-like entry.
            site_errors.append(
                SiteScrapeError(
                    site_code="database",
                    message="Failed to persist results to Postgres",
                    error_type="db_error",
                    details={"error": str(exc)},
                )
            )

    success = len(api_offers) > 0 and (len(site_errors) == 0 or len(api_offers) > 0)

    logger.info(
        "ComparePricesFlow:end offers=%d site_errors=%d query_id=%s",
        len(api_offers),
        len(site_errors),
        persisted_query_id,
    )

    return ComparePricesResult(
        success=success,
        query_id=persisted_query_id,
        offers=api_offers,
        site_errors=[_error_to_api_dict(e) for e in site_errors],
        cheapest_offer=cheapest,
    )
