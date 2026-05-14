from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build_site(tmp_path: Path) -> Path:
    output = tmp_path / "public"
    subprocess.run(
        ["hugo", "--destination", str(output)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return output


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_hugo_site_renders_core_ingrid_surfaces(tmp_path: Path) -> None:
    output = build_site(tmp_path)

    index = read(output / "index.html")
    assert "Harbor Signal" in index
    assert "Harbor Traffic Observatory" in index
    assert "Sci-Fi Review Space" in index
    assert "Latest Harbor Signals" in index
    assert "Latest Reviews" in index
    assert "Live Map" in index
    assert "Observation Timeline" in index
    assert "Vessel Log" in index
    assert "Signal Feed" in index
    assert "Logger" in index
    assert "Currently tracking" in index
    assert "Currently reading" in index
    assert "Recent Signal Feed" in index

    assert (output / "observations" / "index.html").exists()
    assert (output / "reviews" / "index.html").exists()
    assert (output / "analysis" / "index.html").exists()
    assert (output / "about" / "index.html").exists()
    assert (output / "map" / "index.html").exists()
    assert (output / "timeline" / "index.html").exists()
    assert (output / "vessels" / "index.html").exists()
    assert (output / "signal" / "index.html").exists()
    assert (output / "logger" / "index.html").exists()
    assert (output / "threads" / "index.html").exists()
    assert (output / "index.xml").exists()


def test_sample_content_uses_expected_public_schemas(tmp_path: Path) -> None:
    output = build_site(tmp_path)

    observation = read(output / "observations" / "pilot-boat-before-dawn" / "index.html")
    assert "Pilot Boat Before Dawn" in observation
    assert "42.35" in observation
    assert "weather" in observation.lower()
    assert "Castle Island" in observation
    assert "field-log" in observation
    assert "Harbor Pilot 3" in observation
    assert "source" in observation.lower()

    review = read(output / "reviews" / "the-left-hand-of-darkness" / "index.html")
    assert "The Left Hand of Darkness" in review
    assert "Logistics" in review
    assert "Governance" in review
    assert "Bodies" in review
    assert "Tension" in review
    assert "Overall" in review
    assert "verdict-card" in review


def test_harbor_direction_pages_render_operational_surfaces(tmp_path: Path) -> None:
    output = build_site(tmp_path)

    live_map = read(output / "map" / "index.html")
    assert "AIS interval" in live_map
    assert "Weather correlation" in live_map
    assert "Observation marker" in live_map
    assert "AISStream" in live_map
    assert "AISStream Vessel Snapshot" in live_map
    assert "Unique MMSI this fetch" in live_map
    assert "Data freshness" in live_map
    assert "data-vessel-type" in live_map
    assert "left: 50%; top: 50%;" not in live_map
    assert "top: 0.0%;" not in live_map

    timeline = read(output / "timeline" / "index.html")
    assert "Pilot Boat Before Dawn" in timeline
    assert "Manual harbor note" in timeline

    vessels = read(output / "vessels" / "index.html")
    vessel_data = json.loads(read(ROOT / "data" / "harbor" / "vessels.json"))
    assert vessel_data["vessels"][0]["name"] in vessels
    assert "recent observations" in vessels.lower()
    assert "Vessel Dossiers" in vessels
    assert "Sighting History" in vessels
    assert "First seen" in vessels
    assert "Sightings" in vessels

    signal = read(output / "signal" / "index.html")
    assert "The Left Hand of Darkness" in signal
    assert "Pilot Boat Before Dawn" in signal
    assert "logistics" in signal.lower()

    logger = read(output / "logger" / "index.html")
    assert "Observation Logger" in logger
    assert "Vessel reference" in logger
    assert "Works offline" in logger
    assert "Publish to GitHub" in logger
    assert "GitHub token" in logger

    threads = read(output / "threads" / "index.html")
    assert "Cross-Reference Threads" in threads
    assert "logistics of waiting" in threads
    assert "Pilot Boat Before Dawn" in threads
    assert "The Left Hand of Darkness" in threads

    about = read(output / "about" / "index.html")
    assert "I&rsquo;m Ingrid. I live in Boston. I watch ships." in about
    assert "Ingrid, watching the harbor" in about
    assert "/images/ingrid-about" in about
    assert "Harbor Observatory" in about
    assert "Review section" in about
    assert "Signal Feed" in about


def test_static_assets_are_self_contained() -> None:
    css_path = ROOT / "assets" / "css" / "ingrid.css"
    assert css_path.exists()
    css = css_path.read_text(encoding="utf-8")
    assert "--color-harbor: #0a1628" in css
    assert "--color-review: #1a1f2e" in css
    assert "--font-observation" in css
    assert "--font-review" in css
    assert "@font-face" in css
    assert "Harbor Field Mono" in css
    assert "Harbor Review Serif" in css
    assert ".observation .article-body" in css
    assert ".review .article-body" in css
    assert ".marker-pilot-boat" in css
    assert ".marker-tanker" in css
    assert ".marker-passenger" in css
    assert "fonts.googleapis.com" not in css
    assert "gradient" not in css.lower()

    harbor_asset = ROOT / "static" / "images" / "harbor-signal.png"
    assert harbor_asset.exists()
    assert (ROOT / "static" / "images" / "ingrid-about.png").exists()

    assert (ROOT / "static" / "logger.js").exists()
    logger_js = (ROOT / "static" / "logger.js").read_text(encoding="utf-8")
    assert "api.github.com/repos/harbor-signal/harbor-signal.github.io/contents/content/observations/" in logger_js
    assert "method: \"PUT\"" in logger_js
    assert "vessels_referenced" in logger_js
    assert "observation_type: field-log" in logger_js
    assert (ROOT / "static" / "sw.js").exists()
    assert (ROOT / "static" / "manifest.webmanifest").exists()

    assert shutil.which("hugo"), "hugo must be installed for local publishing"


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_scripts_transform_aisstream_and_weather_payloads() -> None:
    fetch_ais = load_script("fetch_ais.py")
    fetch_weather = load_script("fetch_weather.py")

    ais_payload = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 366953000,
            "ShipName": "FRANK S. REYNOLDS",
            "latitude": 42.3542,
            "longitude": -71.0451,
            "time_utc": "2026-05-14 22:12:00 +0000 UTC",
        },
        "Message": {
            "PositionReport": {
                "UserID": 366953000,
                "Sog": 4.2,
                "Cog": 195,
                "TrueHeading": 195,
                "NavigationalStatus": 0,
            }
        },
    }
    vessel = fetch_ais.transform_position_report(ais_payload)
    assert vessel["mmsi"] == "366953000"
    assert vessel["name"] == "FRANK S. REYNOLDS"
    assert vessel["type"] == "unknown"
    assert vessel["speed_knots"] == 4.2
    assert vessel["x"] == 21.8
    assert vessel["y"] == 25.8

    unavailable_heading_payload = {
        **ais_payload,
        "Message": {
            "PositionReport": {
                "UserID": 366953000,
                "Sog": 4.2,
                "Cog": 195,
                "TrueHeading": 511,
                "NavigationalStatus": 0,
            }
        },
    }
    unavailable_heading_vessel = fetch_ais.transform_position_report(unavailable_heading_payload)
    assert unavailable_heading_vessel["heading"] == 195

    static_payload = {
        "MessageType": "ShipStaticData",
        "MetaData": {
            "MMSI": 366953000,
            "ShipName": "FRANK S. REYNOLDS",
        },
        "Message": {
            "ShipStaticData": {
                "UserID": 366953000,
                "Name": "FRANK S. REYNOLDS",
                "Type": 52,
                "Destination": "BOSTON",
                "Eta": {"Month": 5, "Day": 15, "Hour": 6, "Minute": 0},
                "Dimension": {"A": 8, "B": 20},
            }
        },
    }
    static_data = fetch_ais.transform_static_data(static_payload)
    assert static_data["type"] == "tug"
    assert static_data["destination"] == "BOSTON"
    merged_vessel = fetch_ais.apply_static_data(vessel, static_data)
    assert merged_vessel["type"] == "tug"
    assert merged_vessel["length_m"] == 28

    output = fetch_ais.build_output([vessel], fetch_ais.parse_bounds(fetch_ais.DEFAULT_BOUNDS), collection_window_seconds=60)
    assert output["health"]["unique_mmsi_count"] == 1
    assert output["health"]["collection_window_seconds"] == 60
    assert output["health"]["recurrence_candidates"] == []

    history = fetch_ais.update_sightings_history(
        {
            "vessels": {
                "366953000": {
                    "mmsi": "366953000",
                    "name": "FRANK S. REYNOLDS",
                    "type": "tug",
                    "first_seen": "2026-05-14T21:45:00+00:00",
                    "last_seen": "2026-05-14T21:45:00+00:00",
                    "sighting_count": 1,
                    "recent_sightings": [],
                    "destinations": [],
                    "observed_types": ["tug"],
                }
            }
        },
        [vessel],
        observed_at="2026-05-14T22:12:00+00:00",
    )
    dossier = history["vessels"]["366953000"]
    assert dossier["sighting_count"] == 2
    assert dossier["last_seen"] == "2026-05-14T22:12:00+00:00"
    assert dossier["recent_sightings"][0]["speed_knots"] == 4.2

    pruned_history = fetch_ais.prune_history(
        {
            "vessels": {
                "366953000": {
                    **dossier,
                    "recent_sightings": [
                        {"seen_at": "2026-04-01T00:00:00+00:00"},
                        {"seen_at": "2026-05-14T22:12:00+00:00"},
                    ],
                    "summary": {"archived_sighting_count": 0},
                }
            }
        },
        now="2026-05-14T22:12:00+00:00",
        detail_days=30,
    )
    pruned_dossier = pruned_history["vessels"]["366953000"]
    assert pruned_dossier["summary"]["archived_sighting_count"] == 1
    assert len(pruned_dossier["recent_sightings"]) == 1

    weather_payload = {
        "weather": [{"description": "overcast clouds"}],
        "main": {"temp": 48.1},
        "wind": {"speed": 7.0, "deg": 45},
        "visibility": 10000,
        "dt": 1778796720,
    }
    weather = fetch_weather.transform_weather(weather_payload, lat=42.3601, lon=-71.0589)
    assert weather["source"] == "openweathermap"
    assert weather["temperature_f"] == 48.1
    assert weather["conditions"] == "overcast clouds"


def test_pipeline_workflow_and_live_data_schema_exist() -> None:
    workflow = read(ROOT / ".github" / "workflows" / "ais-data.yml")
    assert "*/15 * * * *" in workflow
    assert "AIS_API_KEY" in workflow
    assert "OW_API_KEY" in workflow
    assert "scripts/fetch_ais.py" in workflow
    assert "--history-output data/harbor/sightings_history.json" in workflow
    assert "--timeout 60" in workflow
    assert "scripts/fetch_weather.py" in workflow
    assert "data/harbor/sightings_history.json" in workflow
    assert "actions/deploy-pages" in workflow
    assert "actions/upload-pages-artifact" in workflow

    vessel_data = json.loads(read(ROOT / "data" / "harbor" / "vessels.json"))
    assert vessel_data["source"] == "aisstream"
    assert vessel_data["bounds"]["sw"] == [42.28, -71.08]
    assert vessel_data["health"]["unique_mmsi_count"] == len(vessel_data["vessels"])
    assert isinstance(vessel_data["vessels"], list)

    history_data = json.loads(read(ROOT / "data" / "harbor" / "sightings_history.json"))
    assert history_data["source"] == "aisstream-history"
    assert history_data["vessels"]
