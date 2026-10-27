# Spider Farmer for Home Assistant

Unofficial Home Assistant integration for Spider Farmer grow controllers
(e.g. GGS controller SF-GGS-PS5): sensors, sockets, light and fans via the
Spider Farmer cloud (REST API + MQTT).

> **Status:** early development – not usable yet. See [Plan.md](Plan.md).

*Not affiliated with or endorsed by Spider Farmer.*

## Development

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install aiohttp "aiomqtt>=2.0.0" cryptography pytest pytest-asyncio ruff
pytest
ruff check .
```

Home Assistant Core does not officially run on Windows; end-to-end tests run
in WSL2 with `custom_components/` linked into the HA config directory.
