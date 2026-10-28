"""Make the embedded sfcloud library importable without Home Assistant."""

import sys
from pathlib import Path

# Appended, not prepended: the integration's select.py must not shadow the stdlib module.
sys.path.append(str(Path(__file__).resolve().parents[1] / "custom_components" / "spider_farmer"))
