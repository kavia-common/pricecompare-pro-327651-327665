from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ScrapeContext:
    """Context passed to all scrapers."""

    timeout_seconds: float
    user_agent: str


@dataclass(frozen=True)
class NormalizedOffer:
    """Normalized offer returned by a site scraper."""

    site_code: str
    product_name: Optional[str]
    product_url: str
    image_url: Optional[str]
    currency: str
    price_numeric: Optional[float]
    price_text: Optional[str]
    availability: Optional[str]
    shipping_text: Optional[str]
    raw_data: Dict[str, Any]


# PUBLIC_INTERFACE
def domain_from_url(url: str) -> str:
    """Extract hostname from a URL, normalized to lowercase without www."""
    host = urlparse(url).hostname or ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


_PRICE_RE = re.compile(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


# PUBLIC_INTERFACE
def parse_price_to_float(text: Optional[str]) -> Optional[float]:
    """Parse a price string into float.

    Supports formats like '₹ 12,999', 'INR 12999', '12,999.00'.
    Returns None when parsing fails or text is empty.
    """
    if not text:
        return None
    m = _PRICE_RE.search(text.replace("\u20b9", " "))
    if not m:
        return None
    num = m.group(1).replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None


# PUBLIC_INTERFACE
async def fetch_html(url: str, ctx: ScrapeContext) -> str:
    """Fetch HTML for a URL with a stable, debuggable contract.

    Errors:
      - raises httpx.HTTPError on network issues or non-2xx responses.
    """
    headers = {
        "User-Agent": ctx.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=ctx.timeout_seconds) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text


def soup_from_html(html: str) -> BeautifulSoup:
    # lxml is installed; BeautifulSoup will use it if available.
    return BeautifulSoup(html, "lxml")
