from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.api.core.scrape_utils import domain_from_url
from src.api.scrapers.amazon import AmazonScraper
from src.api.scrapers.flipkart import FlipkartScraper
from src.api.scrapers.gameloot import GamelootScraper
from src.api.scrapers.gamenation import GameNationScraper
from src.api.scrapers.gamestheshop import GamesTheShopScraper


@dataclass(frozen=True)
class ScraperRegistry:
    """Registry of supported site scrapers (single selection point)."""

    by_code: Dict[str, object]

    @staticmethod
    def default() -> "ScraperRegistry":
        scrapers = [
            GamelootScraper(),
            GamesTheShopScraper(),
            GameNationScraper(),
            AmazonScraper(),
            FlipkartScraper(),
        ]
        return ScraperRegistry(by_code={s.site_code: s for s in scrapers})

    def get(self, site_code: str):
        return self.by_code.get(site_code)

    def all_site_codes(self) -> List[str]:
        return list(self.by_code.keys())

    def site_code_for_url(self, url: str) -> Optional[str]:
        host = domain_from_url(url)
        mapping = {
            "gameloot.in": "gameloot",
            "gamestheshop.com": "gamestheshop",
            "gamenation.in": "gamenation",
            "amazon.com": "amazon",
            "flipkart.com": "flipkart",
        }
        return mapping.get(host)
