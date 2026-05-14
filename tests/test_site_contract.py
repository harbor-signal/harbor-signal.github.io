from __future__ import annotations

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

    assert (output / "observations" / "index.html").exists()
    assert (output / "reviews" / "index.html").exists()
    assert (output / "analysis" / "index.html").exists()
    assert (output / "about" / "index.html").exists()
    assert (output / "index.xml").exists()


def test_sample_content_uses_expected_public_schemas(tmp_path: Path) -> None:
    output = build_site(tmp_path)

    observation = read(output / "observations" / "pilot-boat-before-dawn" / "index.html")
    assert "Pilot Boat Before Dawn" in observation
    assert "42.35" in observation
    assert "weather" in observation.lower()
    assert "source" in observation.lower()

    review = read(output / "reviews" / "the-left-hand-of-darkness" / "index.html")
    assert "The Left Hand of Darkness" in review
    assert "Logistics" in review
    assert "Governance" in review
    assert "Bodies" in review
    assert "Longing" in review


def test_static_assets_are_self_contained() -> None:
    css_path = ROOT / "assets" / "css" / "ingrid.css"
    assert css_path.exists()
    css = css_path.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in css
    assert "gradient" not in css.lower()

    harbor_asset = ROOT / "static" / "images" / "harbor-signal.png"
    assert harbor_asset.exists()

    assert shutil.which("hugo"), "hugo must be installed for local publishing"
