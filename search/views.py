from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from search.helpers.autocomplete import GenericDBSearchAutoCompleteHelper
from search.helpers.photo import WikiCityPhotoHelper


@require_http_methods(["GET"])
def main_page(request):
    return render(request, 'search/search.html', context={"request": request})


@require_http_methods(["GET"])
def city_suggestions(request):
    suggestions = GenericDBSearchAutoCompleteHelper().get_suggestions(city=request.GET.get("q"), limit=10)

    return JsonResponse({
        "results": [
            {
                "name": city["name"],
                "region": city.get("admin1", ""),
                "country": city.get("country", ""),
                "geonames_id": city.get("id"),
                "address": {"countryCode": city.get("country_code", "")},
            }
            for city in suggestions
        ]
    })


@require_http_methods(["GET"])
def city_photo(request):
    photo_link = WikiCityPhotoHelper().get_city_photo(
        city=request.GET.get("q"), geonames_id=request.GET.get("id")
    )
    return JsonResponse({
        "path": photo_link,
    })
