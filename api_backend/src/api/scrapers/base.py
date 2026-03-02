from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from src.api.core.scrape_utils import NormalizedOffer, ScrapeContext


@dataclass(frozen=True)
class SiteScrapeError:
    """Structured error returned when a site scrape fails."""

    site_code: str
    message: str
    error_type: str
    url: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class SiteScraper(Protocol):
    site_code: str
    base_url: str

    async def search(self, query: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        """Search a site by text query."""

    async def from_url(self, url: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        """Parse a direct product URL for a site."""
