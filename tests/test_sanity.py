"""Smoke test: the protocol library imports without Home Assistant."""

import json
import subprocess
import sys
from pathlib import Path


def test_sfcloud_imports_without_homeassistant() -> None:
    # Fresh interpreter: the HA pytest plugin may already have imported homeassistant here.
    code = (
        "import sys; sys.path.insert(0, 'custom_components/spider_farmer'); "
        "import sfcloud; assert 'homeassistant' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_manifest_domain() -> None:
    manifest = json.loads(
        Path("custom_components/spider_farmer/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["domain"] == "spider_farmer"
