import logging
from abc import ABC, abstractmethod

import requests
from django.conf import settings

from info.utils.places import CATEGORY_CLASSES, WikidataAirports, WikidataPlaces, WikipediaGeoSearch
from search.utils.url import URL

logger = logging.getLogger(__name__)

_FAILURES = (requests.RequestException, KeyError, ValueError)


class CityPlacesHelperBase(ABC):
    @abstractmethod
    def get_places(self, city: dict, **kwargs):
        pass


class OpenPlacesHelper(CityPlacesHelperBase):
    """
    Places near a city from Wikipedia + Wikidata (free, keyless). If a source is slow or down,
    its sections come back empty and the template hides them, instead of the page erroring.
    """

    def __init__(self):
        wikidata = URL(**settings.WIKIDATA_CONFIG)
        self._nearby = WikidataPlaces(url=wikidata, geosearch=WikipediaGeoSearch(URL(**settings.WIKIPEDIA_CONFIG)))
        self._airports = WikidataAirports(url=wikidata)

    def get_places(self, city: dict, **kwargs):
        """{'dining': {'results': [...]}, 'landmarks': {...}, 'arts': {...}}"""
        try:
            places = self._nearby.get_places(city["latitude"], city["longitude"], **kwargs)
        except _FAILURES as error:
            logger.warning("Nearby places failed for %s: %s", city.get("name"), error)
            places = {category: [] for category in CATEGORY_CLASSES}
        return {category: {"results": found} for category, found in places.items()}

    def get_airports(self, city: dict, **kwargs):
        try:
            return {"results": self._airports.get_places(city["latitude"], city["longitude"], **kwargs)}
        except _FAILURES as error:
            logger.warning("Airports failed for %s: %s", city.get("name"), error)
            return {"results": []}
