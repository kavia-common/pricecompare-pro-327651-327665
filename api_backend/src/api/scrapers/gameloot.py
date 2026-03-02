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


class GamelootScraper:
    site_code = "gameloot"
    base_url = "https://gameloot.in"

    async def search(self, query: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        # Gameloot supports search via /?s= query parameter (WordPress style).
        url = f"{self.base_url}/?s={quote(query)}"
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        offers: List[NormalizedOffer] = []
        for a in soup.select("a.woocommerce-LoopProduct-link, a.woocommerce-loop-product__link, a.product-link"):
            href = a.get("href")
            if not href:
                continue
            title = (a.get_text(" ", strip=True) or None)
            # try find price in same container
            container = a.parent
            price_text: Optional[str] = None
            if container:
                price_el = container.select_one(".price, .woocommerce-Price-amount")
                if price_el:
                    price_text = price_el.get_text(" ", strip=True)
            offers.append(
                NormalizedOffer(
                    site_code=self.site_code,
                    product_name=title,
                    product_url=urljoin(self.base_url, href),
                    image_url=None,
                    currency="INR",
                    price_numeric=parse_price_to_float(price_text),
                    price_text=price_text,
                    availability=None,
                    shipping_text=None,
                    raw_data={"source": "search", "searchUrl": url},
                )
            )

        # Deduplicate by URL
        uniq = {}
        for o in offers:
            uniq[o.product_url] = o
        return list(uniq.values())[:10]

    async def from_url(self, url: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        title_el = soup.select_one("h1.product_title, h1")
        product_name = title_el.get_text(" ", strip=True) if title_el else None

        price_el = soup.select_one(".summary .price, .price, .woocommerce-Price-amount")
        price_text = price_el.get_text(" ", strip=True) if price_el else None

        img_el = soup.select_one("img.wp-post-image, .woocommerce-product-gallery__image img")
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
