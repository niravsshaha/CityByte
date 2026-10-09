from unittest import mock

from django.test import TestCase

from search.utils import search as search_utils
from search.utils import photo as photo_utils

PUNE = {
    "id": 1259229, "name": "Pune", "latitude": 18.52, "longitude": 73.86,
    "country_code": "IN", "country": "India", "admin1": "Maharashtra",
}


def fake_response(payload, status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class SearchTests(TestCase):
    def setUp(self):
        search_utils._geocode.cache_clear()
        photo_utils._city_photos.cache_clear()

    def test_main_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CityByte")

    @mock.patch("search.utils.search.requests.get")
    def test_city_suggestions(self, get):
        get.return_value = fake_response({"results": [PUNE]})
        data = self.client.get("/api/search/city", {"q": "Pun"}).json()

        self.assertEqual(data["results"][0]["name"], "Pune")
        self.assertEqual(data["results"][0]["address"]["countryCode"], "IN")
        self.assertEqual(get.call_args.kwargs["params"]["name"], "Pun")

    @mock.patch("search.utils.search.requests.get")
    def test_city_suggestions_survive_api_failure(self, get):
        get.side_effect = search_utils.requests.ConnectionError()
        data = self.client.get("/api/search/city", {"q": "Pune"}).json()
        self.assertEqual(data["results"], [])

    @mock.patch("search.utils.photo.requests.get")
    def test_city_photo_from_wikidata(self, get):
        get.return_value = fake_response({"results": {"bindings": [
            {"img": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/Pune%20skyline.jpg"}}
        ]}})
        data = self.client.get("/api/search/city/photo", {"q": "Pune", "id": "1259229"}).json()

        self.assertEqual(
            data["path"], "https://commons.wikimedia.org/wiki/Special:FilePath/Pune%20skyline.jpg?width=1600"
        )
        self.assertIn('wdt:P1566 "1259229"', get.call_args.kwargs["params"]["query"])
