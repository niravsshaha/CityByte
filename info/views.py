import logging
from concurrent.futures import ThreadPoolExecutor

from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from info.helpers.places import OpenPlacesHelper
from info.helpers.weather import OpenMeteoWeatherHelper
from search.helpers.autocomplete import GenericDBSearchAutoCompleteHelper
from search.helpers.photo import WikiCityPhotoHelper

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def info_page(request):
    city = GenericDBSearchAutoCompleteHelper().get_city(
        city=request.GET.get("city"), country=request.GET.get("country")
    )
    if city is None:
        return redirect("main_page")

    places = OpenPlacesHelper()

    # Each section comes from a different open API, so fetch them all at once.
    with ThreadPoolExecutor(max_workers=4) as pool:
        weather = pool.submit(OpenMeteoWeatherHelper().get_city_weather, city)
        photo = pool.submit(WikiCityPhotoHelper().get_city_photo, city["name"], city.get("id"))
        nearby = pool.submit(places.get_places, city, limit=5)
        airports = pool.submit(places.get_airports, city, limit=5)
    nearby = nearby.result()

    # Header fields used if the weather API is unavailable, so the page still renders.
    fallback_weather = {
        "city_name": city["name"],
        "state_code": city.get("admin1") or city.get("country", ""),
        "country_code": city.get("country_code", ""),
    }

    response = render(
        request, 'search/city_info.html',
        context={
            "weather_info": _result_or(weather, fallback_weather),
            "dining_info": nearby["dining"],
            "airport_info": airports.result(),
            "outdoor_info": nearby["landmarks"],
            "arts_info": nearby["arts"],
            "photo_link": _result_or(photo, None),
        }
    )
    # Let Vercel's CDN keep each city page for an hour (and serve it stale while refreshing),
    # so repeat visits are instant and we stay polite to the free APIs.
    response["Cache-Control"] = "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400"
    return response


def _result_or(future, default):
    try:
        return future.result()
    except Exception as error:  # a third-party API failing shouldn't take the page down
        logger.warning("City info section failed: %s", error)
        return default
