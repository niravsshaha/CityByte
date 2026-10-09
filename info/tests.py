from unittest import mock

from django.test import TestCase

from info.utils import places as places_utils
from search.tests import PUNE, fake_response
from search.utils import photo as photo_utils
from search.utils import search as search_utils

WEATHER = {
    "timezone": "Asia/Kolkata",
    "current": {
        "time": "2026-10-10T14:00", "temperature_2m": 29.1, "apparent_temperature": 31.0,
        "surface_pressure": 948.4, "wind_speed_10m": 3.2, "wind_direction_10m": 270,
        "cloud_cover": 40, "precipitation": 0.0, "uv_index": 6.5, "weather_code": 2,
    },
    "daily": {"sunrise": ["2026-10-10T06:27"], "sunset": ["2026-10-10T18:16"]},
}

GEOSEARCH = {"query": {"pages": [
    {"pageprops": {"wikibase_item": "Q1"}}, {"pageprops": {"wikibase_item": "Q2"}},
    {"pageprops": {"wikibase_item": "Q3"}}, {"pageprops": {"wikibase_item": "Q4"}}, {"title": "no item"},
]}}


def row(qid, label, cls, cls_label, description="", img=None):
    r = {
        "item": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "itemLabel": {"value": label},
        "class": {"value": f"http://www.wikidata.org/entity/{cls}"},
        "classLabel": {"value": cls_label},
        "itemDescription": {"value": description},
    }
    if img:
        r["img"] = {"value": f"http://commons.wikimedia.org/wiki/Special:FilePath/{img}"}
    return r


NEARBY = {"results": {"bindings": [
    row("Q1", "Shaniwar Wada", "Q57821", "fort", "fortification in Pune", "Wada.jpg"),
    row("Q2", "Raja Dinkar Kelkar Museum", "Q33506", "museum", "museum in Pune"),
    row("Q3", "Vaishali", "Q11707", "restaurant", "restaurant in Pune"),
    row("Q4", "Q4", "Q33506", "museum"),  # unlabelled: skipped
]}}

AIRPORTS = {"results": {"bindings": [
    row("Q5", "Pune Airport", "Q644371", "international airport", "airport in Maharashtra"),
]}}


def route_get(url, *args, **kwargs):
    if "geocoding-api" in url:
        return fake_response({"results": [PUNE]})
    if "//api.open-meteo.com" in url:
        return fake_response(WEATHER)
    if "/w/api.php" in url:
        return fake_response(GEOSEARCH)
    if "wikidata" in url:
        query = kwargs["params"]["query"]
        if "P1566" in query:  # city photo
            return fake_response({"results": {"bindings": [
                {"img": {"value": "http://commons.wikimedia.org/wiki/Special:FilePath/Pune.jpg"}}]}})
        return fake_response(AIRPORTS)
    return fake_response({}, status=404)


def route_post(url, *args, **kwargs):
    assert "VALUES ?item { wd:Q1 wd:Q2 wd:Q3 wd:Q4 }" in kwargs["data"]["query"]
    return fake_response(NEARBY)


class InfoPageTests(TestCase):
    def setUp(self):
        search_utils._geocode.cache_clear()
        photo_utils._city_photos.cache_clear()
        places_utils._geosearch.cache_clear()

    @mock.patch("requests.post", side_effect=route_post)
    @mock.patch("requests.get", side_effect=route_get)
    def test_info_page_renders_all_sections(self, _get, _post):
        response = self.client.get("/city", {"city": "Pune", "country": "IN"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("s-maxage", response["Cache-Control"])

        weather = response.context["weather_info"]
        self.assertEqual((weather["city_name"], weather["temp"]), ("Pune", 29.1))
        self.assertEqual((weather["sunrise"], weather["sunset"]), ("06:27", "06:16"))

        def names(section):
            return [p["name"] for p in response.context[section]["results"]]

        self.assertEqual(names("outdoor_info"), ["Shaniwar Wada"])
        self.assertEqual(names("arts_info"), ["Raja Dinkar Kelkar Museum"])
        self.assertEqual(names("dining_info"), ["Vaishali"])
        self.assertEqual(names("airport_info"), ["Pune Airport"])

        fort = response.context["outdoor_info"]["results"][0]
        self.assertEqual(fort["location"]["formatted_address"], "Fortification in Pune")
        self.assertEqual(fort["categories"][0]["name"], "Fort")
        self.assertTrue(fort["image"].endswith("Wada.jpg?width=500"))
        self.assertContains(response, "Raja Dinkar Kelkar Museum")

    @mock.patch("requests.post", side_effect=search_utils.requests.ConnectionError())
    @mock.patch("requests.get")
    def test_info_page_survives_api_outages(self, get, _post):
        def flaky(url, *args, **kwargs):
            if "//api.open-meteo.com" in url or "wikidata" in url:
                raise search_utils.requests.ConnectionError()
            return route_get(url, *args, **kwargs)
        get.side_effect = flaky

        response = self.client.get("/city", {"city": "Pune", "country": "IN"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pune")
        # Weather cards start hidden; the browser fills them in from Open-Meteo directly.
        self.assertContains(response, 'id="weather-cards" class="d-flex flex-wrap" style="margin: 1rem;" hidden')
        self.assertContains(response, 'data-lat="18.520000"')
        self.assertNotContains(response, "Top Arts Spots")

    @mock.patch("requests.post", side_effect=route_post)
    @mock.patch("requests.get", side_effect=route_get)
    def test_info_page_uses_coordinates_from_search_page(self, get, _post):
        response = self.client.get("/city", {
            "city": "Pune", "country": "IN", "region": "Maharashtra",
            "lat": "18.52", "lon": "73.86", "id": "1259229",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(any("geocoding-api" in c.args[0] for c in get.call_args_list))
        self.assertContains(response, "Maharashtra, IN")
        self.assertContains(response, 'data-lat="18.520000"')

    @mock.patch("requests.get", return_value=fake_response({"results": []}))
    def test_unknown_city_redirects_home(self, _get):
        response = self.client.get("/city", {"city": "Nowhereville", "country": "ZZ"})
        self.assertRedirects(response, "/", fetch_redirect_response=False)
