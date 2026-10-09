from abc import ABC, abstractmethod
from functools import lru_cache

import requests
from django.conf import settings

from search.utils.url import URL


class SearchUtilBase(ABC):
    _url: URL = None

    def __init__(self, url: URL):
        self._url = url

    @abstractmethod
    def get_city_suggestions(self, city: str, **kwargs):
        pass


@lru_cache(maxsize=512)
def _geocode(base_url: str, name: str, count: int, country_code: str):
    params = {"name": name, "count": count, "language": "en", "format": "json"}
    if country_code:
        params["countryCode"] = country_code

    response = requests.get(
        f"{base_url}/v1/search",
        params=params,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return tuple(response.json().get("results", []))


class OpenMeteoGeocoding(SearchUtilBase):
    """Keyless city search backed by the Open-Meteo geocoding API (GeoNames data)."""

    def get_city_suggestions(self, city: str, **kwargs):
        if not city:
            return []
        try:
            return list(_geocode(
                self._url.get_url(path=""),
                city.strip(),
                int(kwargs.get("limit", 10)),
                (kwargs.get("country") or "").upper(),
            ))
        except (requests.RequestException, ValueError):
            return []

    def get_city(self, city: str, country: str = None):
        """Best match for a city name, optionally restricted to an ISO country code."""
        results = self.get_city_suggestions(city, limit=1, country=country)
        if not results and country:
            results = self.get_city_suggestions(city, limit=1)
        return results[0] if results else None
