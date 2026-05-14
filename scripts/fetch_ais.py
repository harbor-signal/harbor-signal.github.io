#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"
DEFAULT_BOUNDS = "42.28,-71.08,42.38,-70.92"


def parse_bounds(raw: str) -> dict[str, list[float]]:
    south, west, north, east = [float(part.strip()) for part in raw.split(",")]
    return {"sw": [south, west], "ne": [north, east]}


def subscription_message(api_key: str, bounds: dict[str, list[float]]) -> dict[str, Any]:
    return {
        "APIKey": api_key,
        "BoundingBoxes": [[bounds["sw"], bounds["ne"]]],
        "FilterMessageTypes": ["PositionReport"],
    }


def marker_position(lat: float | int | None, lon: float | int | None, bounds: dict[str, list[float]]) -> dict[str, float | None]:
    if lat is None or lon is None:
        return {"x": None, "y": None}
    south, west = bounds["sw"]
    north, east = bounds["ne"]
    if north == south or east == west:
        return {"x": None, "y": None}
    x = ((float(lon) - west) / (east - west)) * 100
    y = 100 - (((float(lat) - south) / (north - south)) * 100)
    return {
        "x": round(max(0, min(100, x)), 1),
        "y": round(max(0, min(100, y)), 1),
    }


def normalize_heading(report: dict[str, Any]) -> float | int | None:
    true_heading = report.get("TrueHeading")
    if true_heading is not None and true_heading != 511:
        return true_heading
    return report.get("Cog")


def classify_vessel(metadata: dict[str, Any], report: dict[str, Any]) -> str:
    raw_type = str(metadata.get("ShipType") or report.get("ShipType") or "").lower()
    name = str(metadata.get("ShipName") or "").lower()
    if "pilot" in name:
        return "pilot boat"
    if "tug" in name or raw_type in {"31", "32", "52"}:
        return "tug"
    if raw_type.startswith("7"):
        return "cargo"
    if raw_type.startswith("8"):
        return "tanker"
    if raw_type.startswith("6"):
        return "passenger"
    if raw_type.startswith("3"):
        return "fishing"
    return raw_type or "unknown"


def transform_position_report(message: dict[str, Any]) -> dict[str, Any]:
    metadata = message.get("MetaData") or message.get("Metadata") or {}
    report = (message.get("Message") or {}).get("PositionReport") or {}
    mmsi = metadata.get("MMSI") or report.get("UserID")
    lat = metadata.get("latitude") or metadata.get("Latitude") or report.get("Latitude")
    lon = metadata.get("longitude") or metadata.get("Longitude") or report.get("Longitude")
    ship_name = str(metadata.get("ShipName") or f"MMSI {mmsi}").strip()
    signal_time = metadata.get("time_utc") or datetime.now(timezone.utc).isoformat()
    position = marker_position(lat, lon, parse_bounds(DEFAULT_BOUNDS))

    return {
        "mmsi": str(mmsi),
        "name": ship_name,
        "type": classify_vessel(metadata, report),
        "flag": metadata.get("Country") or "",
        "lat": lat,
        "lon": lon,
        "x": position["x"],
        "y": position["y"],
        "coordinates": f"{lat}, {lon}",
        "speed_knots": report.get("Sog"),
        "heading": normalize_heading(report),
        "destination": metadata.get("Destination") or "",
        "eta": metadata.get("ETA") or "",
        "length_m": metadata.get("Length") or "",
        "nav_status": report.get("NavigationalStatus"),
        "last_signal": signal_time,
        "source": "AISStream",
        "status": "under way using engine" if report.get("NavigationalStatus") == 0 else "reported",
        "tags": [classify_vessel(metadata, report)],
    }


def build_output(vessels: list[dict[str, Any]], bounds: dict[str, list[float]]) -> dict[str, Any]:
    return {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "source": "aisstream",
        "status": "live",
        "bounds": bounds,
        "vessels": vessels,
    }


async def collect_vessels(api_key: str, bounds: dict[str, list[float]], timeout: int, max_messages: int) -> list[dict[str, Any]]:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("Missing dependency: install websockets to fetch AIS data") from exc

    vessels_by_mmsi: dict[str, dict[str, Any]] = {}
    async with websockets.connect(AISSTREAM_URL) as websocket:
        await websocket.send(json.dumps(subscription_message(api_key, bounds)))
        end_at = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end_at and len(vessels_by_mmsi) < max_messages:
            remaining = max(0.1, end_at - asyncio.get_running_loop().time())
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            message = json.loads(raw)
            if message.get("MessageType") != "PositionReport":
                continue
            vessel = transform_position_report(message)
            if vessel["mmsi"]:
                vessels_by_mmsi[vessel["mmsi"]] = vessel
    return list(vessels_by_mmsi.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Boston Harbor AIS positions from AISStream.")
    parser.add_argument("--bounds", default=DEFAULT_BOUNDS)
    parser.add_argument("--output", default="data/harbor/vessels.json")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--max-messages", type=int, default=80)
    args = parser.parse_args()

    api_key = os.environ.get("AIS_API_KEY")
    if not api_key:
        raise SystemExit("AIS_API_KEY is required")

    bounds = parse_bounds(args.bounds)
    vessels = asyncio.run(collect_vessels(api_key, bounds, timeout=args.timeout, max_messages=args.max_messages))
    output = build_output(vessels, bounds)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
