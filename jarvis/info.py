"""Weather and news, from free services that need no account or key:
Open-Meteo for the weather and BBC News feeds for headlines."""

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .config import config

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo's place search matches names only, so "Princeton, NJ" is looked
# up as "Princeton" and the state picks between the results.
US_STATES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas", "ca": "california",
    "co": "colorado", "ct": "connecticut", "de": "delaware", "fl": "florida", "ga": "georgia",
    "hi": "hawaii", "id": "idaho", "il": "illinois", "in": "indiana", "ia": "iowa",
    "ks": "kansas", "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada", "nh": "new hampshire",
    "nj": "new jersey", "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon", "pa": "pennsylvania",
    "ri": "rhode island", "sc": "south carolina", "sd": "south dakota", "tn": "tennessee",
    "tx": "texas", "ut": "utah", "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "wy": "wyoming", "dc": "district of columbia",
}

# WMO weather codes, as Open-Meteo reports them.
CONDITIONS = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle",
    57: "freezing drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
    96: "thunderstorms with hail", 99: "thunderstorms with hail",
}

NEWS_FEEDS = {
    "top": "https://feeds.bbci.co.uk/news/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "us": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "health": "https://feeds.bbci.co.uk/news/health/rss.xml",
    "entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "sport": "https://feeds.bbci.co.uk/sport/rss.xml",
}


def _get(url: str, params: dict | None = None) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Jarvis/2.0"})
    with urllib.request.urlopen(request, timeout=15) as reply:
        return reply.read()


def find_place(place: str) -> dict:
    name, _, rest = place.partition(",")
    hints = [h.strip().lower() for h in rest.split(",") if h.strip()]
    hints = [US_STATES.get(h, h) for h in hints]
    found = json.loads(_get(GEOCODE_URL, {"name": name.strip(), "count": 10, "language": "en"}))
    results = found.get("results") or []
    if not results:
        raise RuntimeError(f"I couldn't find a place called {place}.")
    for result in results:
        labels = " ".join(
            str(result.get(k, "")).lower() for k in ("admin1", "country", "country_code")
        )
        if all(hint in labels for hint in hints):
            return result
    return results[0]


def weather(place: str = "") -> str:
    place = place.strip() or config.location
    if not place:
        raise RuntimeError(
            "I don't know where you are. Tell me your town, or say 'remember I live in ...'."
        )
    spot = find_place(place)
    units = config.units
    if units == "auto":
        units = "fahrenheit" if spot.get("country_code") in ("US", "LR", "MM") else "celsius"
    params = {
        "latitude": spot["latitude"],
        "longitude": spot["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto",
        "forecast_days": 3,
    }
    if units == "fahrenheit":
        params.update(temperature_unit="fahrenheit", wind_speed_unit="mph")
    data = json.loads(_get(FORECAST_URL, params))
    degree = "°F" if units == "fahrenheit" else "°C"
    speed = "mph" if units == "fahrenheit" else "km/h"

    now = data["current"]
    where = ", ".join(p for p in (spot.get("name"), spot.get("admin1") or spot.get("country")) if p)
    lines = [
        f"{where}, now: {round(now['temperature_2m'])}{degree} "
        f"(feels like {round(now['apparent_temperature'])}{degree}), "
        f"{CONDITIONS.get(now['weather_code'], 'unsettled')}, "
        f"wind {round(now['wind_speed_10m'])} {speed}."
    ]
    daily = data["daily"]
    for i, label in enumerate(("Today", "Tomorrow", "The day after")):
        if i >= len(daily["time"]):
            break
        rain = daily["precipitation_probability_max"][i]
        lines.append(
            f"{label}: {CONDITIONS.get(daily['weather_code'][i], 'unsettled')}, "
            f"high {round(daily['temperature_2m_max'][i])}{degree}, "
            f"low {round(daily['temperature_2m_min'][i])}{degree}"
            + (f", {rain}% chance of rain or snow." if rain is not None else ".")
        )
    return "\n".join(lines)


def news(topic: str = "top", count: int = 6) -> str:
    feed = NEWS_FEEDS.get(topic.strip().lower(), NEWS_FEEDS["top"])
    root = ET.fromstring(_get(feed))
    stories = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        if title:
            stories.append(f"- {title}" + (f": {summary}" if summary else ""))
        if len(stories) >= max(1, min(count, 15)):
            break
    if not stories:
        return "No headlines came back."
    return "Headlines from BBC News:\n" + "\n".join(stories)
