"""Async REST client for api.spider-farmer.com."""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import UTC, datetime
from typing import Any

import aiohttp

from . import crypto
from .exceptions import ApiError, AuthError, CannotConnect
from .models import Device, LoginResult

_LOGGER = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.spider-farmer.com"
APP_VERSION = "2.5.2"
SUCCESS_CODE = "000"
# "102": "The token is registered remotely." – another login (e.g. the app) replaced it.
AUTH_ERROR_CODES: frozenset[str] = frozenset({"102"})

_HISTORY_FMT = "%Y-%m-%d %H:%M:%S"


class SpiderFarmerApi:
    """Thin wrapper around the encrypted REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timezone: str = "Europe/Berlin",
        language: str = "English",
    ) -> None:
        self._session = session
        self.token = token
        self._base_url = base_url.rstrip("/")
        self._timezone = timezone
        self._language = language

    def _systemdata(self, auth: bool) -> str:
        data: dict[str, Any] = {
            "reqId": random.randint(1, 999_999_999),
            "appVersion": APP_VERSION,
            "osType": "Android",
            "osVersion": "14",
            "deviceType": "home-assistant",
            "deviceId": "home-assistant",
            "netType": "wifi",
            "timestamp": int(time.time()),
            "wifiName": "unknown_data",
            "timezone": self._timezone,
            "language": self._language,
        }
        if auth and self.token:
            data["token"] = self.token
        return json.dumps(data, separators=(",", ":"))

    async def call_raw(self, path: str, payload: Any = None, *, auth: bool = True) -> Any:
        """POST to `/api/android/<path>` and return the decrypted response envelope."""
        url = f"{self._base_url}/api/android/{path.lstrip('/')}"
        headers = {
            "content-type": "application/json",
            "user-agent": "Dart/3.5 (dart:io)",
            "systemdata": self._systemdata(auth),
        }
        try:
            async with self._session.post(
                url,
                data=crypto.encrypt(payload or {}),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CannotConnect(f"{path}: {err}") from err

        try:
            return crypto.decrypt(text)
        except ValueError:
            # Error pages come back unencrypted.
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                raise CannotConnect(f"{path}: HTTP {resp.status}: {text[:200]}") from None

    async def call(self, path: str, payload: Any = None, *, auth: bool = True) -> Any:
        """Like `call_raw`, but checks the result code and returns `data`."""
        envelope = await self.call_raw(path, payload, auth=auth)
        if not isinstance(envelope, dict):
            raise ApiError(None, str(envelope)[:200], path)
        code = envelope.get("code")
        if code != SUCCESS_CODE:
            _LOGGER.debug("API error on %s: %s", path, envelope)
            err_cls = AuthError if code in AUTH_ERROR_CODES else ApiError
            raise err_cls(code, envelope.get("msg"), path)
        return envelope.get("data")

    # ---- auth --------------------------------------------------------------

    async def request_email_code(self, email: str) -> None:
        """Ask the backend to e-mail a one-time login code."""
        await self.call("ulogin/getEmailCode/v2", {"email": email, "isLogin": 1}, auth=False)

    async def login(self, email: str, otp_code: str) -> LoginResult:
        """Log in with the e-mailed code; stores and returns the session."""
        data = await self.call(
            "ulogin/mailLogin/v2",
            {"email": email, "loginMethod": 2, "otpCode": otp_code},
            auth=False,
        )
        result = LoginResult.from_api(data)
        self.token = result.token
        return result

    async def get_region(self) -> dict[str, Any]:
        return await self.call("ulogin/getBelongingUrlInfo/v2", {})

    # ---- devices -----------------------------------------------------------

    async def get_rooms(self) -> list[dict[str, Any]]:
        return await self.call("udm/getUserRooms/v2", {}) or []

    async def get_devices(self, user_id: int, room_id: int) -> list[Device]:
        data = await self.call(
            "udm/getDeviceList/v2", {"belonginRoomId": room_id, "userId": user_id}
        )
        return [Device.from_api(d, room_id) for d in data or []]

    async def get_all_devices(self, user_id: int) -> list[Device]:
        """Devices across all rooms."""
        devices: dict[str, Device] = {}
        for room in await self.get_rooms():
            # TODO(M1): confirm the room id key in getUserRooms.
            room_id = room.get("id")
            if room_id is None:
                continue
            for device in await self.get_devices(user_id, room_id):
                devices.setdefault(device.serial, device)
        return list(devices.values())

    async def get_socket_names(self, serial: str) -> Any:
        return await self.call("udm/getSocketCustomizeName/v2", {"deviceSerialnum": serial})

    # ---- history -----------------------------------------------------------

    async def get_sensor_history(
        self, serial: str, start: datetime, end: datetime, period: str = "day"
    ) -> list[dict[str, Any]]:
        """Sensor samples (5-minute resolution for `period="day"`).

        The API works in UTC (request range and `addTime`, format
        `MM-DD-YYYY HH:MM:SS`); naive datetimes are treated as UTC. Values are strings.
        """
        start, end = (
            (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC) for dt in (start, end)
        )
        data = await self.call(
            "dr/getDeviceTHPData/v2",
            {
                "deviceSerialnum": serial,
                "type": period,
                "startDate": start.strftime(_HISTORY_FMT),
                "endDate": end.strftime(_HISTORY_FMT),
            },
        )
        return data or []
