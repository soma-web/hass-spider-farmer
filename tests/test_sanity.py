"""Smoke test: the protocol library imports without Home Assistant."""

import json
from pathlib import Path


def test_sfcloud_imports_without_homeassistant() -> None:
    import sys

    import sfcloud  # noqa: F401

    assert "homeassistant" not in sys.modules


def test_manifest_domain() -> None:
    manifest = json.loads(
        Path("custom_components/spider_farmer/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["domain"] == "spider_farmer"
