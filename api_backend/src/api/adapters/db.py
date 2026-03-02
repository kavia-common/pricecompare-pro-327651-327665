from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse, urlunparse

import asyncpg

from src.api.core.config import AppConfig


@dataclass(frozen=True)
class DbPool:
    """Wrapper around asyncpg pool for dependency injection."""

    pool: asyncpg.Pool


def _build_dsn(cfg: AppConfig) -> Optional[str]:
    """Build a Postgres DSN from environment-driven config.

    Why this exists:
      - In the platform runtime, we may receive POSTGRES_URL as a host/db-only URL
        like `postgresql://localhost:5000/myapp` (no credentials).
      - asyncpg, when given a DSN without userinfo, falls back to the OS username.
        That commonly fails in container environments (e.g., role "kavia" does not exist).
      - Therefore: if POSTGRES_URL lacks credentials but POSTGRES_USER/PASSWORD are
        provided, we inject them into the DSN.

    Precedence rules:
      1) If POSTGRES_URL includes username/password, use it as-is.
      2) If POSTGRES_URL exists but has no username/password and POSTGRES_USER/PASSWORD
         exist, inject them.
      3) Otherwise, if POSTGRES_* parts are sufficient, build a DSN from parts.
    """
    if cfg.postgres_url:
        parsed = urlparse(cfg.postgres_url)

        # Only attempt to inject creds for postgres schemes.
        if parsed.scheme.startswith("postgres"):
            has_userinfo = bool(parsed.username) or bool(parsed.password)
            if (not has_userinfo) and cfg.postgres_user and cfg.postgres_password:
                # Preserve host/port/path/query/fragment; inject userinfo.
                netloc = parsed.hostname or ""
                if parsed.port:
                    netloc = f"{netloc}:{parsed.port}"
                netloc = f"{cfg.postgres_user}:{cfg.postgres_password}@{netloc}"

                return urlunparse(
                    (
                        parsed.scheme,
                        netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    )
                )

        return cfg.postgres_url

    if cfg.postgres_user and cfg.postgres_password and cfg.postgres_db and cfg.postgres_port:
        return f"postgresql://{cfg.postgres_user}:{cfg.postgres_password}@localhost:{cfg.postgres_port}/{cfg.postgres_db}"

    return None


# PUBLIC_INTERFACE
async def create_db_pool(cfg: AppConfig) -> Optional[DbPool]:
    """Create a database pool, or return None if DB is not configured.

    Contract:
      - Inputs: AppConfig with POSTGRES_* values.
      - Outputs: DbPool if configuration is present; otherwise None.
      - Errors: raises asyncpg.PostgresError on connectivity/auth issues.
      - Side effects: opens connections to Postgres.

    This optional behavior allows the backend to run in a limited mode without DB.
    """
    dsn = _build_dsn(cfg)
    if not dsn:
        return None

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5, command_timeout=30)
    return DbPool(pool=pool)


async def close_db_pool(db: Optional[DbPool]) -> None:
    if db is None:
        return
    await db.pool.close()


async def _fetchval(pool: asyncpg.Pool, sql: str, *args: Any) -> Any:
    async with pool.acquire() as conn:
        return await conn.fetchval(sql, *args)


async def _execute(pool: asyncpg.Pool, sql: str, *args: Any) -> str:
    async with pool.acquire() as conn:
        return await conn.execute(sql, *args)


async def _executemany(pool: asyncpg.Pool, sql: str, args_seq: Sequence[Sequence[Any]]) -> None:
    async with pool.acquire() as conn:
        await conn.executemany(sql, args_seq)


async def _fetch(pool: asyncpg.Pool, sql: str, *args: Any) -> List[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(sql, *args)


async def get_site_id_by_code(pool: asyncpg.Pool, code: str) -> Optional[int]:
    row = await _fetchval(pool, "SELECT id FROM public.sites WHERE code=$1 AND enabled=TRUE", code)
    return int(row) if row is not None else None


async def get_default_parser_id(pool: asyncpg.Pool, site_id: int) -> Optional[int]:
    row = await _fetchval(
        pool,
        """
        SELECT id FROM public.parsers
        WHERE site_id=$1 AND enabled=TRUE
        ORDER BY id ASC
        LIMIT 1
        """,
        site_id,
    )
    return int(row) if row is not None else None


# PUBLIC_INTERFACE
async def persist_query_and_offers(
    db: DbPool,
    *,
    query_text: Optional[str],
    query_url: Optional[str],
    query_type: str,
    status: str,
    offers: List[Dict[str, Any]],
) -> Optional[int]:
    """Persist a query and its offers to the database.

    Contract:
      - Inputs:
          - query_text/query_url: user input (one may be None)
          - query_type: "text" or "url"
          - status: query status string
          - offers: list of dicts with keys:
              site_code, product_name, product_url, image_url, currency,
              price_numeric, price_text, availability, shipping_text, raw_data
      - Outputs: query_id (int) on success; None if DB unavailable
      - Errors: raises asyncpg.PostgresError on DB failure
      - Side effects: inserts into queries, offers, price_history
    """
    pool = db.pool
    query_id = await _fetchval(
        pool,
        """
        INSERT INTO public.queries (query_text, query_url, query_type, status)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        query_text,
        query_url,
        query_type,
        status,
    )
    if query_id is None:
        return None
    query_id_int = int(query_id)

    # We insert offers one by one because each needs site_id lookup and returns offer_id
    async with pool.acquire() as conn:
        async with conn.transaction():
            for offer in offers:
                site_id = await conn.fetchval(
                    "SELECT id FROM public.sites WHERE code=$1",
                    offer["site_code"],
                )
                if site_id is None:
                    # If seed is missing for a site, skip persistence for that offer.
                    continue
                parser_id = await conn.fetchval(
                    """
                    SELECT id FROM public.parsers
                    WHERE site_id=$1 AND enabled=TRUE
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    int(site_id),
                )

                offer_id = await conn.fetchval(
                    """
                    INSERT INTO public.offers (
                        query_id, site_id, parser_id,
                        product_name, product_url, image_url,
                        currency, price_numeric, price_text,
                        availability, shipping_text, raw_data
                    )
                    VALUES (
                        $1, $2, $3,
                        $4, $5, $6,
                        $7, $8, $9,
                        $10, $11, $12
                    )
                    RETURNING id
                    """,
                    query_id_int,
                    int(site_id),
                    int(parser_id) if parser_id is not None else None,
                    offer.get("product_name"),
                    offer["product_url"],
                    offer.get("image_url"),
                    offer.get("currency", "INR"),
                    offer.get("price_numeric"),
                    offer.get("price_text"),
                    offer.get("availability"),
                    offer.get("shipping_text"),
                    offer.get("raw_data") or {},
                )

                # price_history entry (even if price is null, keep observation)
                await conn.execute(
                    """
                    INSERT INTO public.price_history (site_id, product_url, price_numeric, currency, query_id, offer_id)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    int(site_id),
                    offer["product_url"],
                    offer.get("price_numeric"),
                    offer.get("currency", "INR"),
                    query_id_int,
                    int(offer_id) if offer_id is not None else None,
                )

    return query_id_int


# PUBLIC_INTERFACE
async def fetch_query_history(
    db: DbPool,
    *,
    limit: int = 20,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch recent query history.

    Returns a list of query rows with offer counts.
    """
    rows = await _fetch(
        db.pool,
        """
        SELECT
          q.id,
          q.query_text,
          q.query_url,
          q.query_type,
          q.status,
          q.created_at,
          q.updated_at,
          (SELECT count(*) FROM public.offers o WHERE o.query_id = q.id) AS offer_count
        FROM public.queries q
        ORDER BY q.created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )

    result: List[Dict[str, Any]] = []
    for r in rows:
        result.append(
            {
                "id": int(r["id"]),
                "queryText": r["query_text"],
                "queryUrl": r["query_url"],
                "queryType": r["query_type"],
                "status": r["status"],
                "createdAt": r["created_at"].isoformat() if isinstance(r["created_at"], datetime) else r["created_at"],
                "updatedAt": r["updated_at"].isoformat() if isinstance(r["updated_at"], datetime) else r["updated_at"],
                "offerCount": int(r["offer_count"] or 0),
            }
        )
    return result


# PUBLIC_INTERFACE
async def fetch_query_offers(db: DbPool, *, query_id: int) -> List[Dict[str, Any]]:
    """Fetch offers for a particular query_id."""
    rows = await _fetch(
        db.pool,
        """
        SELECT
          o.id,
          s.code AS site_code,
          s.name AS site_name,
          o.product_name,
          o.product_url,
          o.image_url,
          o.currency,
          o.price_numeric,
          o.price_text,
          o.availability,
          o.shipping_text,
          o.scraped_at
        FROM public.offers o
        JOIN public.sites s ON s.id = o.site_id
        WHERE o.query_id=$1
        ORDER BY o.price_numeric NULLS LAST, o.id ASC
        """,
        query_id,
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": int(r["id"]),
                "site": {"code": r["site_code"], "name": r["site_name"]},
                "productName": r["product_name"],
                "productUrl": r["product_url"],
                "imageUrl": r["image_url"],
                "currency": r["currency"],
                "priceNumeric": float(r["price_numeric"]) if r["price_numeric"] is not None else None,
                "priceText": r["price_text"],
                "availability": r["availability"],
                "shippingText": r["shipping_text"],
                "scrapedAt": r["scraped_at"].isoformat() if isinstance(r["scraped_at"], datetime) else r["scraped_at"],
            }
        )
    return out


# Small helper for graceful shutdown waits (not public API)
async def _sleep_briefly() -> None:
    await asyncio.sleep(0.01)
