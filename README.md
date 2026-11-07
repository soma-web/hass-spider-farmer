# Spider Farmer for Home Assistant

<img src="https://raw.githubusercontent.com/soma-web/hass-spider-farmer/main/custom_components/spider_farmer/brand/icon.png" alt="Spider Farmer integration icon" width="128" align="right">

Unofficial Home Assistant integration for Spider Farmer grow controllers
(tested with the GGS controller **SF-GGS-PS5**, firmware 3.14). It talks to the
Spider Farmer cloud – the same REST API and MQTT broker the official app uses.

*Not affiliated with or endorsed by Spider Farmer.*

## Features

| Entity | What |
|---|---|
| Sensors | Temperature, humidity, VPD, PPFD, CO2, soil temperature / moisture / EC (only what your controller reports; per-probe sensors when several soil probes are connected) |
| Switches | Power strip outlets 1–5 |
| Fans | Exhaust fan (1–100 %), circulation fan (10 levels, oscillation on/off) |
| Number | Circulation fan oscillation level (0–10) |
| Light | Grow light brightness, light mode (manual / time window / PPFD), time window: on and off time, duration, target brightness, sunrise/sunset |
| Diagnostics | Connectivity, Wi-Fi signal, uptime |

- **Push updates**: the controller reports its state every few seconds over MQTT.
- **History import**: on first setup, up to 30 days of cloud sensor history are
  imported into Home Assistant's long-term statistics.

## Installation

### Marketplace (Home Assistant 2026.11 and later, recommended)

1. *Settings → Marketplace* → **Add from link** (top right) → enter
   `https://github.com/soma-web/hass-spider-farmer` and select **Add**
   (choose *Integration* as type if asked). Adding a link requires connecting
   the Marketplace to GitHub once.
2. Open **Spider Farmer** → **Install**. No restart is needed; the setup opens
   right away.

### HACS (Home Assistant 2026.10)

1. HACS → ⋮ → *Custom repositories* → add
   `https://github.com/soma-web/hass-spider-farmer` as *Integration*.
2. Download **Spider Farmer** and restart Home Assistant.

### Manual

Copy `custom_components/spider_farmer` into your Home Assistant
`config/custom_components/` folder and restart.

## Setup

*Settings → Devices & services → Add integration → Spider Farmer*, enter the
e-mail address of your Spider Farmer account and then the login code you receive
by e-mail.

> **Logging in signs you out of the Spider Farmer app.** The cloud allows one
> app session per account. Simply log in to the app again afterwards –
> Home Assistant keeps working, because it only needs the MQTT connection after
> setup. (Only the history import at setup needs the fresh login.)

## Good to know

- **Controls behave like manual control in the app** (`mOnOff` / `mLevel`). If a
  component runs on a schedule or cycle in the app, the controller may override
  manual changes. The raw controller mode is shown as the `mode_type` attribute.
- **Light**: switching or dimming it puts the light into manual mode, like in the
  app; the time window no longer runs until you set *Light mode* back to *Time window*.
  [`examples/lighting-card.yaml`](examples/lighting-card.yaml) is a dashboard card
  with all light settings.
- Before every command the current configuration is read from the controller,
  so changes made in the app are not overwritten.
- The MQTT broker uses a self-signed certificate, so certificate verification is
  disabled for that connection (as in the official app).
- This is based on reverse engineering of the app; Spider Farmer may change
  their cloud at any time.

## Support

If you find this integration useful, you can support its development:

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/A4Y829KJC5)

## Development

The protocol library `custom_components/spider_farmer/sfcloud/` has no Home
Assistant dependency and can be developed on any OS:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install aiohttp "aiomqtt>=2.0.0" cryptography pytest pytest-asyncio ruff
pytest            # library tests
ruff check .
```

`scripts/sf_cli.py` talks to real hardware (`login`, `devices`, `status`, `watch`,
`set`, `history`, `call`); run it with `--help`.

Home Assistant tests (`tests_ha/`) and a development instance need Linux/WSL2
with Python ≥ 3.14:

```bash
uv venv --python 3.14 ~/ha-test
uv pip install --python ~/ha-test/bin/python pytest-homeassistant-custom-component "aiomqtt>=2.0.0"
~/ha-test/bin/python -m pytest tests tests_ha

# Dev instance on http://localhost:8123 with this repo linked in
# (needs build-essential and Home Assistant in ~/ha-dev/.venv)
bash scripts/ha-dev.sh
```

