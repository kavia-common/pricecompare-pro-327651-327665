from __future__ import annotations

from typing import List, Optional
from urllib.parse import quote, urljoin

from src.api.core.scrape_utils import (
    NormalizedOffer,
    ScrapeContext,
    fetch_html,
    parse_price_to_float,
    soup_from_html,
)


class FlipkartScraper:
    site_code = "flipkart"
    base_url = "https://www.flipkart.com"

    async def search(self, query: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        url = f"{self.base_url}/search?q={quote(query)}"
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        offers: List[NormalizedOffer] = []
        # Flipkart markup varies; attempt common selectors.
        for card in soup.select("a.CGtC98, a._1fQZEK, a[href*='/p/']"):
            href = card.get("href")
            if not href:
                continue
            title = card.get_text(" ", strip=True) or None
            container = card.parent

            price_text: Optional[str] = None
            if container:
                price_el = container.select_one("div._30jeq3, div.Nx9bqj")
                if price_el:
                    price_text = price_el.get_text(" ", strip=True)

            img = card.select_one("img")
            image_url = img.get("src") if img else None

            offers.append(
                NormalizedOffer(
                    site_code=self.site_code,
                    product_name=title,
                    product_url=urljoin(self.base_url, href),
                    image_url=image_url,
                    currency="INR",
                    price_numeric=parse_price_to_float(price_text),
                    price_text=price_text,
                    availability=None,
                    shipping_text=None,
                    raw_data={"source": "search", "searchUrl": url},
                )
            )

        uniq = {}
        for o in offers:
            uniq[o.product_url] = o
        return list(uniq.values())[:10]

    async def from_url(self, url: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        title_el = soup.select_one("span.B_NuCI, h1")
        product_name = title_el.get_text(" ", strip=True) if title_el else None

        price_el = soup.select_one("div._30jeq3, div.Nx9bqj")
        price_text = price_el.get_text(" ", strip=True) if price_el else None

        img_el = soup.select_one("img._396cs4, img")
        image_url = img_el.get("src") if img_el else None

        return [
            NormalizedOffer(
                site_code=self.site_code,
                product_name=product_name,
                product_url=url,
                image_url=image_url,
                currency="INR",
                price_numeric=parse_price_to_float(price_text),
                price_text=price_text,
                availability=None,
                shipping_text=None,
                raw_data={"source": "product"},
            )
        ]
