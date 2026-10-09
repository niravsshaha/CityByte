from abc import ABC, abstractmethod
from functools import lru_cache

import requests
from django.conf import settings

from search.utils.photo import commons_file_url, run_sparql
from search.utils.url import URL


class PlacesUtilBase(ABC):
    _url: URL = None

    def __init__(self, url: URL):
        self._url = url

    @abstractmethod
    def get_places(self, latitude: float, longitude: float, **kwargs):
        pass


def _place(name, address, category, image=None):
    """Shape every place the same way the city_info template expects."""
    return {
        "name": name,
        "location": {"formatted_address": address or ""},
        "categories": [{"name": category or ""}],
        "image": image,
    }


# Wikidata "instance of" classes for each section of the city page.
CATEGORY_CLASSES = {
    # tourist attraction, park, monument, landmark, tower, palace, castle, temple, church,
    # mosque, bridge, garden, archaeological site, memorial, square, cathedral,
    # national park, fort, historic site, beach, zoo
    "landmarks": [
        "Q570116", "Q22698", "Q4989906", "Q2319498", "Q12518", "Q16560", "Q23413", "Q44539",
        "Q16970", "Q32815", "Q12280", "Q1107656", "Q839954", "Q5003624", "Q174782", "Q2977",
        "Q46169", "Q57821", "Q1081138", "Q40080", "Q43501",
    ],
    # museum, art museum, art gallery, theatre, opera house, concert hall, cultural centre,
    # history museum, science museum, arts centre, national museum
    "arts": [
        "Q33506", "Q207694", "Q1007870", "Q24354", "Q153562", "Q1060829", "Q1329623",
        "Q16735822", "Q588140", "Q2190251", "Q2668072",
    ],
    # restaurant, cafe, bar, pub, brasserie, bakery, food market
    "dining": ["Q11707", "Q30022", "Q187456", "Q11446", "Q1052765", "Q274393", "Q1192284"],
}
CLASS_TO_CATEGORY = {q: cat for cat, qs in CATEGORY_CLASSES.items() for q in qs}


def _rows_to_places(rows):
    places, seen = [], set()
    for row in rows:
        name = row.get("itemLabel", {}).get("value", "")
        item_id = row["item"]["value"]
        # Unlabelled items come back as their Q-id; skip them and duplicate rows.
        if item_id in seen or not name or (name.startswith("Q") and name[1:].isdigit()):
            continue
        seen.add(item_id)

        address = row.get("address", {}).get("value") or row.get("itemDescription", {}).get("value", "")
        image = row.get("img", {}).get("value")
        places.append((row, _place(
            name=name,
            address=address[:1].upper() + address[1:] if address else "",
            category=row.get("classLabel", {}).get("value", "").title(),
            image=commons_file_url(image, width=500) if image else None,
        )))
    return places


class WikipediaGeoSearch:
    """Wikidata ids of the (up to 500) Wikipedia articles nearest to a point. Fast and keyless."""

    def __init__(self, url: URL):
        self._url = url

    def get_item_ids(self, latitude: float, longitude: float, radius_m: int = 10000):
        return list(_geosearch(self._url.get_url(path="/w/api.php"), round(latitude, 3), round(longitude, 3), radius_m))


@lru_cache(maxsize=256)
def _geosearch(endpoint, latitude, longitude, radius_m):
    response = requests.get(
        endpoint,
        params={
            "action": "query", "generator": "geosearch", "ggscoord": f"{latitude}|{longitude}",
            "ggsradius": radius_m, "ggslimit": 500, "prop": "pageprops", "ppprop": "wikibase_item",
            "format": "json", "formatversion": 2,
        },
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        timeout=settings.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", [])
    return tuple(p["pageprops"]["wikibase_item"] for p in pages if p.get("pageprops", {}).get("wikibase_item"))


class WikidataPlaces(PlacesUtilBase):
    """Sort nearby Wikidata items into dining / landmarks / arts, most notable first."""

    def __init__(self, url: URL, geosearch: WikipediaGeoSearch = None):
        super().__init__(url)
        self._geosearch = geosearch

    def get_places(self, latitude: float, longitude: float, **kwargs):
        limit = int(kwargs.get("limit", 5))
        item_ids = self._geosearch.get_item_ids(latitude, longitude)
        if not item_ids:
            return {category: [] for category in CATEGORY_CLASSES}

        items = " ".join(f"wd:{q}" for q in item_ids)
        classes = " ".join(f"wd:{q}" for q in CLASS_TO_CATEGORY)
        # Look up the known items by id (fast), rather than a radius scan (slow in dense cities).
        rows = run_sparql(self._url, f"""
            SELECT ?item ?itemLabel ?itemDescription ?class ?classLabel ?address ?img ?links WHERE {{
              VALUES ?item {{ {items} }}
              VALUES ?class {{ {classes} }}
              ?item wdt:P31 ?class ; wikibase:sitelinks ?links .
              # skip places that have closed, been dissolved or demolished
              FILTER NOT EXISTS {{ ?item wdt:P576 [] }}
              FILTER NOT EXISTS {{ ?item wdt:P3999 [] }}
              OPTIONAL {{ ?item wdt:P6375 ?address . }}
              OPTIONAL {{ ?item wdt:P18 ?img . }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
            }} ORDER BY DESC(?links)
        """, method="POST")

        result = {category: [] for category in CATEGORY_CLASSES}
        for row, place in _rows_to_places(rows):
            category = CLASS_TO_CATEGORY[row["class"]["value"].rsplit("/", 1)[-1]]
            if len(result[category]) < limit:
                result[category].append(place)
        return result


class WikidataAirports(PlacesUtilBase):
    """Airports (things with an IATA code that are airports) within ~60 km, busiest-known first."""

    def get_places(self, latitude: float, longitude: float, **kwargs):
        limit = int(kwargs.get("limit", 5))
        rows = run_sparql(self._url, f"""
            SELECT ?item ?itemLabel ?itemDescription ?classLabel ?img ?links WHERE {{
              {{
                SELECT ?item (SAMPLE(?c) AS ?class) (MAX(?sl) AS ?links) WHERE {{
                  SERVICE wikibase:around {{
                    ?item wdt:P625 ?loc .
                    bd:serviceParam wikibase:center "Point({longitude} {latitude})"^^geo:wktLiteral .
                    bd:serviceParam wikibase:radius "{kwargs.get('radius_km', 60)}" .
                  }}
                  ?item wdt:P238 ?iata ; wdt:P31 ?c ; wikibase:sitelinks ?sl .
                  ?c wdt:P279* wd:Q1248784 .
                  FILTER NOT EXISTS {{ ?item wdt:P3999 [] }}
                }} GROUP BY ?item ORDER BY DESC(?links) LIMIT {limit * 2}
              }}
              OPTIONAL {{ ?item wdt:P18 ?img . }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
            }} ORDER BY DESC(?links)
        """)
        return [place for _, place in _rows_to_places(rows)][:limit]
