from abc import ABC, abstractmethod
from functools import lru_cache
from urllib.parse import quote

import requests
from django.conf import settings

from search.utils.url import URL


class PhotoUtilBase(ABC):
    _url: URL = None

    def __init__(self, url: URL):
        self._url = url

    @abstractmethod
    def get_photos(self, city: str, **kwargs):
        pass


def commons_file_url(file_url: str, width: int = 1600) -> str:
    """Turn a Wikidata P18 value into a resized Wikimedia Commons image URL."""
    file_name = file_url.rsplit("/", 1)[-1]
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{file_name}?width={width}"


def run_sparql(url: URL, query: str, method: str = "GET"):
    """Run a Wikidata SPARQL query. Use POST for long queries (e.g. hundreds of ids)."""
    headers = {"User-Agent": settings.HTTP_USER_AGENT, "Accept": "application/sparql-results+json"}
    if method == "POST":
        response = requests.post(
            url.get_url(path="/sparql"), data={"query": query}, headers=headers,
            timeout=settings.SPARQL_TIMEOUT,
        )
    else:
        response = requests.get(
            url.get_url(path="/sparql"), params={"query": query, "format": "json"}, headers=headers,
            timeout=settings.SPARQL_TIMEOUT,
        )
    response.raise_for_status()
    return response.json()["results"]["bindings"]


@lru_cache(maxsize=512)
def _city_photos(sparql_host: str, geonames_id: str, name: str):
    url = URL(protocol="https", host=sparql_host, port=443)
    if geonames_id:
        selector = f'?city wdt:P1566 "{geonames_id}" .'
    else:
        safe_name = name.replace("\\", "").replace('"', "")
        selector = f'?city rdfs:label "{safe_name}"@en ; wdt:P31/wdt:P279* wd:Q515 .'

    rows = run_sparql(url, f"""
        SELECT ?img WHERE {{
          {selector}
          ?city wdt:P18 ?img .
        }} LIMIT 5
    """)
    return tuple(commons_file_url(row["img"]["value"]) for row in rows)


class WikidataPhoto(PhotoUtilBase):
    """Keyless city photos from Wikidata's 'image' property (served by Wikimedia Commons)."""

    def get_photos(self, query: str, **kwargs):
        try:
            return list(_city_photos(self._url.host, str(kwargs.get("geonames_id") or ""), query or ""))
        except (requests.RequestException, KeyError, ValueError):
            return []


class WikipediaPhoto(PhotoUtilBase):
    """Fallback: the lead image of the city's English Wikipedia article."""

    def get_photos(self, query: str, **kwargs):
        if not query:
            return []
        try:
            response = requests.get(
                self._url.get_url(path=f"/api/rest_v1/page/summary/{quote(query.replace(' ', '_'))}"),
                headers={"User-Agent": settings.HTTP_USER_AGENT},
                timeout=settings.HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                return []
            data = response.json()
            image = data.get("originalimage") or data.get("thumbnail")
            return [image["source"]] if image else []
        except (requests.RequestException, ValueError):
            return []
