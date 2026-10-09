from abc import ABC, abstractmethod
from datetime import datetime

from django.conf import settings

from info.utils.weather import OpenMeteoWeather, WeatherUtilBase
from search.utils.url import URL


class CityWeatherHelperBase(ABC):
    @abstractmethod
    def get_city_weather(self, city: dict, **kwargs):
        pass


def _clock(iso_time: str) -> str:
    return datetime.fromisoformat(iso_time).strftime("%I:%M")


class OpenMeteoWeatherHelper(CityWeatherHelperBase):
    def __init__(self, klass: WeatherUtilBase = None, url: URL = None):
        if url is None:
            klass = OpenMeteoWeather
            url = URL(**settings.OPEN_METEO_FORECAST_CONFIG)

        self._weather_util = klass(url=url)

    def get_city_weather(self, city: dict, **kwargs):
        """Weather for a geocoded city, in the field names the city_info template uses."""
        data = self._weather_util.get_city_weather(city["latitude"], city["longitude"])
        current, daily = data["current"], data["daily"]

        return {
            "city_name": city["name"],
            "state_code": city.get("admin1") or city.get("country", ""),
            "country_code": city.get("country_code", ""),
            "timezone": data.get("timezone"),
            "temp": current["temperature_2m"],
            "app_temp": current["apparent_temperature"],
            "pres": round(current["surface_pressure"]),
            "wind_spd": current["wind_speed_10m"],
            "wind_dir": current["wind_direction_10m"],
            "clouds": current["cloud_cover"],
            "precip": current["precipitation"],
            "uv": current["uv_index"],
            "sunrise": _clock(daily["sunrise"][0]),
            "sunset": _clock(daily["sunset"][0]),
            "ts": datetime.fromisoformat(current["time"]).strftime("%m-%d-%Y, %H:%M"),
        }
