#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def transform_weather(payload: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
    weather = (payload.get("weather") or [{}])[0]
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    observed_at = payload.get("dt")
    if observed_at:
        last_updated = datetime.fromtimestamp(observed_at, timezone.utc).isoformat()
    else:
        last_updated = datetime.now(timezone.utc).isoformat()
    wind_speed = wind.get("speed")
    visibility = payload.get("visibility")
    return {
        "last_updated": last_updated,
        "source": "openweathermap",
        "status": "live",
        "lat": lat,
        "lon": lon,
        "summary": weather.get("description") or "",
        "conditions": weather.get("description") or "",
        "temperature_f": main.get("temp"),
        "wind_speed_mph": wind_speed,
        "wind_direction_deg": wind.get("deg"),
        "visibility_m": visibility,
        "wind": f"{wind_speed} mph" if wind_speed is not None else "",
        "visibility": f"{visibility} m" if visibility is not None else "",
    }


def fetch_weather(api_key: str, lat: float, lon: float) -> dict[str, Any]:
    query = urllib.parse.urlencode({"lat": lat, "lon": lon, "appid": api_key, "units": "imperial"})
    with urllib.request.urlopen(f"{OPENWEATHER_URL}?{query}", timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return transform_weather(payload, lat=lat, lon=lon)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Boston Harbor weather from OpenWeatherMap.")
    parser.add_argument("--lat", type=float, default=42.3601)
    parser.add_argument("--lon", type=float, default=-71.0589)
    parser.add_argument("--output", default="data/harbor/weather.json")
    args = parser.parse_args()

    api_key = os.environ.get("OW_API_KEY")
    if not api_key:
        raise SystemExit("OW_API_KEY is required")

    output = fetch_weather(api_key, lat=args.lat, lon=args.lon)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
