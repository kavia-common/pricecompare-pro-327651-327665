from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ComparePricesRequestModel(BaseModel):
    query: Optional[str] = Field(
        default=None,
        description="Text query to search across sites (required if queryType='text').",
        examples=["PS5 controller", "Elden Ring PS5"],
    )
    url: Optional[str] = Field(
        default=None,
        description="Direct product URL to parse (required if queryType='url').",
        examples=["https://gameloot.in/product/elden-ring-ps5/"],
    )
    queryType: str = Field(
        default="text",
        description="Type of query: 'text' to search, 'url' to parse a direct product URL.",
        pattern="^(text|url)$",
    )
    sites: Optional[List[str]] = Field(
        default=None,
        description="Optional list of site codes to target. If omitted, all supported sites are used.",
        examples=[["gameloot", "gamenation"]],
    )
    maxResultsPerSite: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of offers to return per site.",
    )


class SiteRef(BaseModel):
    code: str = Field(..., description="Site code, e.g. 'gameloot', 'amazon'.")
    name: Optional[str] = Field(default=None, description="Human-friendly site name when available.")


class OfferModel(BaseModel):
    site: SiteRef = Field(..., description="Site metadata for the offer.")
    productName: Optional[str] = Field(default=None, description="Product title/name if parsed.")
    productUrl: str = Field(..., description="Canonical product URL.")
    imageUrl: Optional[str] = Field(default=None, description="Product image URL if parsed.")
    currency: str = Field(default="INR", description="Currency code, default INR.")
    priceNumeric: Optional[float] = Field(default=None, description="Normalized numeric price, if parsed.")
    priceText: Optional[str] = Field(default=None, description="Raw price text from the page, if available.")
    availability: Optional[str] = Field(default=None, description="Availability text if parsed.")
    shippingText: Optional[str] = Field(default=None, description="Shipping text if parsed.")
    rawData: Dict[str, Any] = Field(default_factory=dict, description="Additional raw parse data for debugging.")


class SiteErrorModel(BaseModel):
    site: SiteRef = Field(..., description="Site metadata for which error occurred.")
    message: str = Field(..., description="Human-readable error message.")
    type: str = Field(..., description="Machine-friendly error type.")
    url: Optional[str] = Field(default=None, description="URL being fetched/parsed, if applicable.")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional error details.")


class ComparePricesResponseModel(BaseModel):
    success: bool = Field(..., description="True if at least one offer was successfully returned.")
    queryId: Optional[int] = Field(default=None, description="Persisted query id if DB is configured and write succeeds.")
    offers: List[OfferModel] = Field(default_factory=list, description="Aggregated offers across sites.")
    cheapestOffer: Optional[OfferModel] = Field(default=None, description="Cheapest offer among those with numeric prices.")
    siteErrors: List[SiteErrorModel] = Field(
        default_factory=list,
        description="Structured per-site errors. Scrape failures do not necessarily fail the whole request.",
    )


class QueryHistoryItem(BaseModel):
    id: int = Field(..., description="Query id.")
    queryText: Optional[str] = Field(default=None, description="Text query, if queryType='text'.")
    queryUrl: Optional[str] = Field(default=None, description="URL query, if queryType='url'.")
    queryType: str = Field(..., description="Query type: 'text' or 'url'.")
    status: str = Field(..., description="Query status: 'completed', 'partial', etc.")
    createdAt: str = Field(..., description="ISO timestamp when the query was created.")
    updatedAt: str = Field(..., description="ISO timestamp when the query was last updated.")
    offerCount: int = Field(..., description="Number of offers persisted for this query.")


class QueryHistoryResponse(BaseModel):
    items: List[QueryHistoryItem] = Field(default_factory=list, description="List of recent queries.")
    limit: int = Field(..., description="Limit used.")
    offset: int = Field(..., description="Offset used.")


class QueryOffersResponse(BaseModel):
    queryId: int = Field(..., description="Query id.")
    offers: List[OfferModel] = Field(default_factory=list, description="Offers persisted for the query.")
