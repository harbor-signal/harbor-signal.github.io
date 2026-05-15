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
DEFAULT_REGISTRY = "data/harbor/vessel_registry.json"

AIS_TYPE_CODES = {
    "30": "fishing",
    "31": "tug",
    "32": "tug",
    "40": "high-speed craft",
    "50": "service craft",
    "51": "service craft",
    "52": "tug",
    "53": "service craft",
    "54": "service craft",
    "55": "service craft",
    "58": "service craft",
    "60": "passenger",
    "70": "cargo",
    "80": "tanker",
}


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


def clean_text(value: Any) -> str:
    return str(value or "").replace("\x00", "").strip().rstrip("<").strip()


def normalize_vessel_type(raw_value: Any, name: str = "") -> str:
    raw_type = clean_text(raw_value).lower()
    vessel_name = clean_text(name).lower()
    if "pilot" in vessel_name:
        return "pilot boat"
    if vessel_name.startswith("cg") or "coast guard" in vessel_name:
        return "service craft"
    if "tug" in vessel_name or raw_type in {"31", "32", "52"}:
        return "tug"
    if raw_type in AIS_TYPE_CODES:
        return AIS_TYPE_CODES[raw_type]
    if raw_type.startswith("4"):
        return "high-speed craft"
    if raw_type.startswith("5"):
        return "service craft"
    if raw_type.startswith("6"):
        return "passenger"
    if raw_type.startswith("7"):
        return "cargo"
    if raw_type.startswith("8"):
        return "tanker"
    if raw_type.startswith("3"):
        return "fishing"
    if raw_type.startswith("9"):
        return "other"
    for label in ("pilot boat", "high-speed craft", "service craft", "passenger", "tanker", "cargo", "tug", "fishing"):
        if label in raw_type:
            return label
    return raw_type or "unknown"


def classify_vessel(metadata: dict[str, Any], report: dict[str, Any]) -> str:
    raw_type = metadata.get("ShipType") or metadata.get("Type") or report.get("ShipType") or report.get("Type") or ""
    return normalize_vessel_type(raw_type, metadata.get("ShipName") or "")


def format_eta(raw_eta: Any) -> str:
    if not isinstance(raw_eta, dict):
        return str(raw_eta or "")
    month = raw_eta.get("Month")
    day = raw_eta.get("Day")
    hour = raw_eta.get("Hour")
    minute = raw_eta.get("Minute")
    if None in {month, day, hour, minute}:
        return ""
    if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31 and 0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        return ""
    return f"{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute):02d} UTC"


def clean_eta(value: Any) -> str:
    eta = clean_text(value)
    if not eta:
        return ""
    try:
        date_part, time_part, *_ = eta.split()
        month, day = [int(part) for part in date_part.split("-", 1)]
        hour, minute = [int(part) for part in time_part.split(":", 1)]
    except ValueError:
        return eta
    if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
        return ""
    return eta


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
    name = clean_text(static.get("Name") or metadata.get("ShipName") or f"MMSI {mmsi}")
    type_metadata = {**metadata, "ShipName": name}
    type_report = {
        "Type": static.get("Type") or static.get("ShipType"),
        "ShipType": static.get("ShipType") or static.get("Type"),
    }
    return {
        "mmsi": str(mmsi),
        "name": name,
        "type": classify_vessel(type_metadata, type_report),
        "destination": clean_text(static.get("Destination") or metadata.get("Destination")),
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


def known_history_type(dossier: dict[str, Any]) -> str:
    candidates = [dossier.get("type"), *(dossier.get("observed_types") or [])]
    for candidate in candidates:
        vessel_type = normalize_vessel_type(candidate, dossier.get("name") or "")
        if vessel_type and vessel_type != "unknown":
            return vessel_type
    return ""


def latest_history_destination(dossier: dict[str, Any]) -> str:
    for sighting in dossier.get("recent_sightings") or []:
        destination = clean_text(sighting.get("destination"))
        if destination:
            return destination
    for destination in dossier.get("destinations") or []:
        cleaned = clean_text(destination)
        if cleaned:
            return cleaned
    return ""


def apply_history_data(vessel: dict[str, Any], dossier: dict[str, Any] | None) -> dict[str, Any]:
    if not dossier:
        return vessel
    merged = dict(vessel)
    history_type = known_history_type(dossier)
    if history_type and (not merged.get("type") or merged.get("type") == "unknown"):
        merged["type"] = history_type
        merged["tags"] = [history_type]
    destination = latest_history_destination(dossier)
    if destination and not clean_text(merged.get("destination")):
        merged["destination"] = destination
    if dossier.get("name") and str(merged.get("name") or "").startswith("MMSI "):
        merged["name"] = dossier["name"]
    return merged


def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    vessels = data.get("vessels", data)
    return {str(key): value for key, value in vessels.items()}


def apply_registry_data(vessel: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    entry = registry.get(str(vessel.get("mmsi") or ""))
    if not entry:
        normalized_name = clean_text(vessel.get("name")).upper()
        entry = next((item for item in registry.values() if clean_text(item.get("name")).upper() == normalized_name), None)
    if not entry:
        return vessel
    merged = dict(vessel)
    registry_type = normalize_vessel_type(entry.get("type"), entry.get("name") or merged.get("name") or "")
    if registry_type and (not merged.get("type") or merged.get("type") == "unknown"):
        merged["type"] = registry_type
        merged["tags"] = [registry_type]
    for key in ("name", "destination", "eta", "length_m"):
        value = clean_text(entry.get(key)) if key != "length_m" else entry.get(key)
        if value and not clean_text(merged.get(key)):
            merged[key] = value
    return merged


def enrich_vessels(vessels: list[dict[str, Any]], history: dict[str, Any], registry: dict[str, Any]) -> list[dict[str, Any]]:
    dossiers = history.get("vessels") or {}
    enriched = []
    for vessel in vessels:
        merged = apply_history_data(vessel, dossiers.get(str(vessel.get("mmsi") or "")))
        merged = apply_registry_data(merged, registry)
        merged["destination"] = clean_text(merged.get("destination"))
        merged["eta"] = clean_eta(merged.get("eta"))
        if not merged.get("tags") or merged.get("tags") == ["unknown"]:
            merged["tags"] = [merged.get("type") or "unknown"]
        enriched.append(merged)
    return enriched


def transform_position_report(message: dict[str, Any], bounds: dict[str, list[float]] | None = None) -> dict[str, Any]:
    metadata = message.get("MetaData") or message.get("Metadata") or {}
    report = (message.get("Message") or {}).get("PositionReport") or {}
    mmsi = metadata.get("MMSI") or report.get("UserID")
    lat = metadata.get("latitude") or metadata.get("Latitude") or report.get("Latitude")
    lon = metadata.get("longitude") or metadata.get("Longitude") or report.get("Longitude")
    ship_name = clean_text(metadata.get("ShipName") or f"MMSI {mmsi}")
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
        "destination": clean_text(metadata.get("Destination")),
        "eta": clean_eta(metadata.get("ETA")),
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
        if vessel_type == "unknown":
            vessel_type = known_history_type(existing) or vessel_type
        destination = clean_text(vessel.get("destination")) or latest_history_destination(existing)
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
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-messages", type=int, default=80)
    parser.add_argument("--history-detail-days", type=int, default=30)
    parser.add_argument("--enrich-existing", action="store_true", help="Enrich the existing output JSON without opening AISStream.")
    args = parser.parse_args()

    bounds = parse_bounds(args.bounds)
    history_path = Path(args.history_output)
    registry = load_registry(Path(args.registry))
    history_input = load_history(history_path)
    path = Path(args.output)
    if args.enrich_existing:
        existing_output = json.loads(path.read_text(encoding="utf-8"))
        vessels = enrich_vessels(existing_output.get("vessels") or [], history_input, registry)
        existing_output["vessels"] = vessels
        existing_output.setdefault("health", {})["unique_mmsi_count"] = len({vessel.get("mmsi") for vessel in vessels if vessel.get("mmsi")})
        path.write_text(json.dumps(existing_output, indent=2) + "\n", encoding="utf-8")
        return

    api_key = os.environ.get("AIS_API_KEY")
    if not api_key:
        raise SystemExit("AIS_API_KEY is required")

    vessels = asyncio.run(collect_vessels(api_key, bounds, timeout=args.timeout, max_messages=args.max_messages))
    vessels = enrich_vessels(vessels, history_input, registry)
    history = prune_history(update_sightings_history(load_history(history_path), vessels), detail_days=args.history_detail_days)
    output = build_output(vessels, bounds, collection_window_seconds=args.timeout, history=history)
    path.parent.mkdir(parents=True, exist_ok=True)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    history_path.write_text(json.dumps(history, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
