from abc import ABC, abstractmethod

from django.conf import settings

from search.utils.photo import WikidataPhoto, WikipediaPhoto
from search.utils.url import URL


class CityPhotoHelperBase(ABC):
    @abstractmethod
    def get_city_photo(self, city: str):
        pass


class WikiCityPhotoHelper(CityPhotoHelperBase):
    """City photo from Wikidata, falling back to the Wikipedia article's lead image."""

    def __init__(self):
        self._sources = [
            WikidataPhoto(url=URL(**settings.WIKIDATA_CONFIG)),
            WikipediaPhoto(url=URL(**settings.WIKIPEDIA_CONFIG)),
        ]

    def get_city_photo(self, city: str, geonames_id=None):
        for source in self._sources:
            photos = source.get_photos(query=city, geonames_id=geonames_id)
            if photos:
                return photos[0]
        return None
