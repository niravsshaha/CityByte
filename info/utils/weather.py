from abc import ABC, abstractmethod

import requests
from django.conf import settings

from search.utils.url import URL


class WeatherUtilBase(ABC):
    _url: URL = None

    def __init__(self, url: URL):
        self._url = url

    @abstractmethod
    def get_city_weather(self, latitude: float, longitude: float, **kwargs):
        pass


class OpenMeteoWeather(WeatherUtilBase):
    """Keyless current weather from the Open-Meteo forecast API."""

    CURRENT_FIELDS = [
        "temperature_2m", "apparent_temperature", "surface_pressure", "wind_speed_10m",
        "wind_direction_10m", "cloud_cover", "precipitation", "uv_index", "weather_code",
    ]

    def get_city_weather(self, latitude: float, longitude: float, **kwargs):
        response = requests.get(
            self._url.get_url(path="/v1/forecast"),
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(self.CURRENT_FIELDS),
                "daily": "sunrise,sunset",
                "timezone": "auto",
                "wind_speed_unit": "ms",
                "forecast_days": 1,
            },
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            timeout=settings.HTTP_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
