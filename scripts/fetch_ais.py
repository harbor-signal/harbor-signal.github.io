#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
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
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
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
    raw_type = str(metadata.get("ShipType") or metadata.get("Type") or report.get("ShipType") or report.get("Type") or "").lower()
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


def format_eta(raw_eta: Any) -> str:
    if not isinstance(raw_eta, dict):
        return str(raw_eta or "")
    month = raw_eta.get("Month")
    day = raw_eta.get("Day")
    hour = raw_eta.get("Hour")
    minute = raw_eta.get("Minute")
    if None in {month, day, hour, minute}:
        return ""
    return f"{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d} UTC"


def vessel_length(raw_dimension: Any) -> int | str:
    if not isinstance(raw_dimension, dict):
        return ""
    parts = [raw_dimension.get("A"), raw_dimension.get("B")]
    numeric = [int(part) for part in parts if isinstance(part, int | float)]
    return sum(numeric) if numeric else ""


def transform_static_data(message: dict[str, Any]) -> dict[str, Any]:
    metadata = message.get("MetaData") or message.get("Metadata") or {}
    static = (message.get("Message") or {}).get("ShipStaticData") or {}
    mmsi = metadata.get("MMSI") or static.get("UserID")
    name = str(static.get("Name") or metadata.get("ShipName") or f"MMSI {mmsi}").strip()
    type_metadata = {**metadata, "ShipName": name}
    type_report = {
        "Type": static.get("Type") or static.get("ShipType"),
        "ShipType": static.get("ShipType") or static.get("Type"),
    }
    return {
        "mmsi": str(mmsi),
        "name": name,
        "type": classify_vessel(type_metadata, type_report),
        "destination": static.get("Destination") or metadata.get("Destination") or "",
        "eta": format_eta(static.get("Eta") or static.get("ETA") or metadata.get("ETA")),
        "length_m": vessel_length(static.get("Dimension")),
    }


def apply_static_data(vessel: dict[str, Any], static: dict[str, Any] | None) -> dict[str, Any]:
    if not static:
        return vessel
    merged = dict(vessel)
    for key in ("name", "destination", "eta", "length_m"):
        if static.get(key):
            merged[key] = static[key]
    if static.get("type") and (not merged.get("type") or merged.get("type") == "unknown"):
        merged["type"] = static["type"]
        merged["tags"] = [static["type"]]
    return merged


def transform_position_report(message: dict[str, Any], bounds: dict[str, list[float]] | None = None) -> dict[str, Any]:
    metadata = message.get("MetaData") or message.get("Metadata") or {}
    report = (message.get("Message") or {}).get("PositionReport") or {}
    mmsi = metadata.get("MMSI") or report.get("UserID")
    lat = metadata.get("latitude") or metadata.get("Latitude") or report.get("Latitude")
    lon = metadata.get("longitude") or metadata.get("Longitude") or report.get("Longitude")
    ship_name = str(metadata.get("ShipName") or f"MMSI {mmsi}").strip()
    signal_time = metadata.get("time_utc") or datetime.now(timezone.utc).isoformat()
    position = marker_position(lat, lon, bounds or parse_bounds(DEFAULT_BOUNDS))
    vessel_type = classify_vessel(metadata, report)

    return {
        "mmsi": str(mmsi),
        "name": ship_name,
        "type": vessel_type,
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
        "tags": [vessel_type],
    }


def recurrence_candidates(history: dict[str, Any] | None) -> list[str]:
    if not history:
        return []
    candidates = []
    for mmsi, dossier in (history.get("vessels") or {}).items():
        if int(dossier.get("sighting_count") or 0) > 1:
            candidates.append(str(mmsi))
    return sorted(candidates)


def build_output(
    vessels: list[dict[str, Any]],
    bounds: dict[str, list[float]],
    collection_window_seconds: int,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "last_updated": now_utc,
        "source": "aisstream",
        "status": "live",
        "bounds": bounds,
        "health": {
            "unique_mmsi_count": len({vessel.get("mmsi") for vessel in vessels if vessel.get("mmsi")}),
            "vessel_count": len(vessels),
            "collection_window_seconds": collection_window_seconds,
            "recurrence_candidates": recurrence_candidates(history),
        },
        "vessels": vessels,
    }


def load_history(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"source": "aisstream-history", "vessels": {}}
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"source": "aisstream-history", "vessels": {}}
    history.setdefault("source", "aisstream-history")
    history.setdefault("vessels", {})
    return history


def update_sightings_history(
    history: dict[str, Any],
    vessels: list[dict[str, Any]],
    observed_at: str | None = None,
    max_recent_sightings: int = 25,
) -> dict[str, Any]:
    next_history = {
        "source": "aisstream-history",
        "last_updated": observed_at or datetime.now(timezone.utc).isoformat(),
        "vessels": dict(history.get("vessels") or {}),
    }
    for vessel in vessels:
        mmsi = str(vessel.get("mmsi") or "")
        if not mmsi:
            continue
        seen_at = observed_at or vessel.get("last_signal") or next_history["last_updated"]
        existing = dict(next_history["vessels"].get(mmsi) or {})
        recent_sightings = list(existing.get("recent_sightings") or [])
        observed_types = set(existing.get("observed_types") or [])
        destinations = set(existing.get("destinations") or [])
        vessel_type = vessel.get("type") or "unknown"
        destination = vessel.get("destination") or ""
        if vessel_type:
            observed_types.add(str(vessel_type))
        if destination:
            destinations.add(str(destination))

        sighting = {
            "seen_at": seen_at,
            "lat": vessel.get("lat"),
            "lon": vessel.get("lon"),
            "speed_knots": vessel.get("speed_knots"),
            "heading": vessel.get("heading"),
            "status": vessel.get("status"),
            "destination": destination,
        }
        next_history["vessels"][mmsi] = {
            "mmsi": mmsi,
            "name": vessel.get("name") or existing.get("name") or f"MMSI {mmsi}",
            "type": vessel_type or existing.get("type") or "unknown",
            "first_seen": existing.get("first_seen") or seen_at,
            "last_seen": seen_at,
            "sighting_count": int(existing.get("sighting_count") or 0) + 1,
            "recent_sightings": [sighting, *recent_sightings][:max_recent_sightings],
            "destinations": sorted(destinations),
            "observed_types": sorted(observed_types),
        }
    return next_history


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def prune_history(history: dict[str, Any], now: str | None = None, detail_days: int = 30) -> dict[str, Any]:
    now_dt = parse_timestamp(now or datetime.now(timezone.utc).isoformat()) or datetime.now(timezone.utc)
    cutoff = now_dt - timedelta(days=detail_days)
    next_history = dict(history)
    vessels = dict(next_history.get("vessels") or {})
    for mmsi, dossier in vessels.items():
        next_dossier = dict(dossier)
        summary = dict(next_dossier.get("summary") or {})
        archived_count = int(summary.get("archived_sighting_count") or 0)
        kept = []
        for sighting in next_dossier.get("recent_sightings") or []:
            seen_at = parse_timestamp(sighting.get("seen_at"))
            if seen_at and seen_at < cutoff:
                archived_count += 1
            else:
                kept.append(sighting)
        summary["archived_sighting_count"] = archived_count
        summary["detail_window_days"] = detail_days
        summary["detail_cutoff"] = cutoff.isoformat()
        next_dossier["summary"] = summary
        next_dossier["recent_sightings"] = kept
        vessels[mmsi] = next_dossier
    next_history["vessels"] = vessels
    return next_history


async def collect_vessels(api_key: str, bounds: dict[str, list[float]], timeout: int, max_messages: int) -> list[dict[str, Any]]:
    try:
        import websockets
    except ImportError as exc:
        raise SystemExit("Missing dependency: install websockets to fetch AIS data") from exc

    vessels_by_mmsi: dict[str, dict[str, Any]] = {}
    static_by_mmsi: dict[str, dict[str, Any]] = {}
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
            if message.get("MessageType") == "ShipStaticData":
                static = transform_static_data(message)
                if static["mmsi"]:
                    static_by_mmsi[static["mmsi"]] = static
                    if static["mmsi"] in vessels_by_mmsi:
                        vessels_by_mmsi[static["mmsi"]] = apply_static_data(vessels_by_mmsi[static["mmsi"]], static)
                continue
            if message.get("MessageType") == "PositionReport":
                vessel = transform_position_report(message, bounds=bounds)
                if vessel["mmsi"]:
                    vessels_by_mmsi[vessel["mmsi"]] = apply_static_data(vessel, static_by_mmsi.get(vessel["mmsi"]))
    return list(vessels_by_mmsi.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Boston Harbor AIS positions from AISStream.")
    parser.add_argument("--bounds", default=DEFAULT_BOUNDS)
    parser.add_argument("--output", default="data/harbor/vessels.json")
    parser.add_argument("--history-output", default="data/harbor/sightings_history.json")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-messages", type=int, default=80)
    parser.add_argument("--history-detail-days", type=int, default=30)
    args = parser.parse_args()

    api_key = os.environ.get("AIS_API_KEY")
    if not api_key:
        raise SystemExit("AIS_API_KEY is required")

    bounds = parse_bounds(args.bounds)
    vessels = asyncio.run(collect_vessels(api_key, bounds, timeout=args.timeout, max_messages=args.max_messages))
    history_path = Path(args.history_output)
    history = prune_history(update_sightings_history(load_history(history_path), vessels), detail_days=args.history_detail_days)
    output = build_output(vessels, bounds, collection_window_seconds=args.timeout, history=history)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    history_path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
