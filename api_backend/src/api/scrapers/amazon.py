from __future__ import annotations

from typing import List
from urllib.parse import quote, urljoin

from src.api.core.scrape_utils import (
    NormalizedOffer,
    ScrapeContext,
    fetch_html,
    parse_price_to_float,
    soup_from_html,
)


class AmazonScraper:
    site_code = "amazon"
    base_url = "https://www.amazon.com"

    async def search(self, query: str, ctx: ScrapeContext) -> List[NormalizedOffer]:
        url = f"{self.base_url}/s?k={quote(query)}"
        html = await fetch_html(url, ctx)
        soup = soup_from_html(html)

        offers: List[NormalizedOffer] = []
        for item in soup.select("[data-component-type='s-search-result']"):
            a = item.select_one("h2 a[href]")
            if not a:
                continue
            href = a.get("href")
            title = a.get_text(" ", strip=True) or None

            whole = item.select_one(".a-price .a-offscreen")
            price_text = whole.get_text(" ", strip=True) if whole else None

            img = item.select_one("img.s-image")
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

        title_el = soup.select_one("#productTitle")
        product_name = title_el.get_text(" ", strip=True) if title_el else None

        price_el = soup.select_one(".a-price .a-offscreen, #priceblock_ourprice, #priceblock_dealprice")
        price_text = price_el.get_text(" ", strip=True) if price_el else None

        img_el = soup.select_one("#landingImage, img#imgBlkFront")
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
