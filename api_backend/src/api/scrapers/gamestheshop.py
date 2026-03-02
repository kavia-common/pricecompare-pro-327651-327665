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


class GamesTheShopScraper:
    site_code = "gamestheshop"
    base_url = "https://www.gamestheshop.com"

    async def search(self, query: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        # Common pattern: /search?type=product&q=...
        url = f"{self.base_url}/search?type=product&q={quote(query)}"
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        offers: List[NormalizedOffer] = []
        for card in soup.select("a.product-item__link, a.grid-product__link, a[href*='/products/']"):
            href = card.get("href")
            if not href:
                continue
            container = card.parent
            title = card.get_text(" ", strip=True) or None

            price_text: Optional[str] = None
            if container:
                price_el = container.select_one(".price, .product-item__price, .money")
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

        uniq = {}
        for o in offers:
            uniq[o.product_url] = o
        return list(uniq.values())[:10]

    async def from_url(self, url: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        title_el = soup.select_one("h1.product-single__title, h1")
        product_name = title_el.get_text(" ", strip=True) if title_el else None

        price_el = soup.select_one(".product-single__price .money, .price .money, .money")
        price_text = price_el.get_text(" ", strip=True) if price_el else None

        img_el = soup.select_one("img.product-featured-media, img.product__image, img")
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
