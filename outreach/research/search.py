"""Search and business-listing providers (section 6: "Search API plus page fetching", "Google
Places API or equivalent"). Each is optional and keyed by an environment variable."""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str = ""


class SearchProvider:
    name = "none"

    def search(self, query: str, count: int = 8) -> list[SearchHit]:
        return []


class BraveSearch(SearchProvider):
    name = "brave"

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=15)

    def search(self, query: str, count: int = 8) -> list[SearchHit]:
        r = self.client.get("https://api.search.brave.com/res/v1/web/search",
                            params={"q": query, "count": count},
                            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"})
        if r.status_code != 200:
            return []
        hits = (r.json().get("web") or {}).get("results") or []
        return [SearchHit(h.get("title", ""), h.get("url", ""), h.get("description", "")) for h in hits]


class SerpApiSearch(SearchProvider):
    name = "serpapi"

    def __init__(self, api_key: str, client: httpx.Client | None = None, country: str = "fr"):
        self.api_key, self.country = api_key, country.lower()
        self.client = client or httpx.Client(timeout=15)

    def search(self, query: str, count: int = 8) -> list[SearchHit]:
        r = self.client.get("https://serpapi.com/search.json",
                            params={"q": query, "num": count, "engine": "google", "api_key": self.api_key,
                                    "gl": self.country, "hl": self.country})
        if r.status_code != 200:
            return []
        hits = r.json().get("organic_results") or []
        return [SearchHit(h.get("title", ""), h.get("link", ""), h.get("snippet", "")) for h in hits]


@dataclass(frozen=True)
class Place:
    name: str
    address: str
    phone: str          # international format as Google gives it
    website: str
    source_url: str     # the Google Maps link, as the evidence URL


class GooglePlaces:
    """Google Places API (New): text search, used for the business phone number and website."""

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=15)

    def find(self, query: str, max_results: int = 3) -> list[Place]:
        r = self.client.post("https://places.googleapis.com/v1/places:searchText",
                             headers={"X-Goog-Api-Key": self.api_key, "Content-Type": "application/json",
                                      "X-Goog-FieldMask": "places.displayName,places.formattedAddress,"
                                                          "places.internationalPhoneNumber,places.websiteUri,"
                                                          "places.googleMapsUri"},
                             json={"textQuery": query, "maxResultCount": max_results})
        if r.status_code != 200:
            return []
        out = []
        for p in r.json().get("places", []):
            out.append(Place(name=(p.get("displayName") or {}).get("text", ""),
                             address=p.get("formattedAddress", ""),
                             phone=p.get("internationalPhoneNumber", ""),
                             website=p.get("websiteUri", ""),
                             source_url=p.get("googleMapsUri", "")))
        return out


def make_search_provider(settings) -> SearchProvider:
    if settings.SEARCH_PROVIDER == "brave" and settings.BRAVE_API_KEY:
        return BraveSearch(settings.BRAVE_API_KEY)
    if settings.SEARCH_PROVIDER == "serpapi" and settings.SERPAPI_KEY:
        return SerpApiSearch(settings.SERPAPI_KEY, country=settings.DEFAULT_COUNTRY)
    return SearchProvider()
