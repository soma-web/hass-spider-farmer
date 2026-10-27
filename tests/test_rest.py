"""Tests for the REST client using a fake aiohttp session."""

from __future__ import annotations

import json
from typing import Any

import pytest

from sfcloud import ApiError, SpiderFarmerApi, crypto


class FakeResponse:
    def __init__(self, text: str, status: int = 200) -> None:
        self._text = text
        self.status = status

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeSession:
    """Records requests and answers with queued (encrypted) envelopes."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, *, data: str, headers: dict[str, str], timeout: Any) -> FakeResponse:
        self.requests.append(
            {
                "url": url,
                "payload": crypto.decrypt(data),
                "systemdata": json.loads(headers["systemdata"]),
            }
        )
        response = self.responses.pop(0)
        if isinstance(response, FakeResponse):
            return response
        return FakeResponse(crypto.encrypt(response))


def ok(data: Any) -> dict[str, Any]:
    return {"code": "000", "subCode": None, "msg": "success", "data": data}


async def test_login_stores_token_and_omits_it_before() -> None:
    session = FakeSession(
        ok({"token": "TOK", "userId": 5, "mqttName": "m", "mqttPwd": "p", "nickName": "n"})
    )
    api = SpiderFarmerApi(session)  # type: ignore[arg-type]
    result = await api.login("a@b.c", "123456")

    req = session.requests[0]
    assert req["url"] == "https://api.spider-farmer.com/api/android/ulogin/mailLogin/v2"
    assert req["payload"] == {"email": "a@b.c", "loginMethod": 2, "otpCode": "123456"}
    assert "token" not in req["systemdata"]
    assert result.token == api.token == "TOK"


async def test_authenticated_call_sends_token() -> None:
    session = FakeSession(ok([]))
    api = SpiderFarmerApi(session, "TOK")  # type: ignore[arg-type]
    assert await api.get_rooms() == []
    assert session.requests[0]["systemdata"]["token"] == "TOK"


async def test_error_code_raises() -> None:
    session = FakeSession({"code": "401", "msg": "token invalid", "data": None})
    api = SpiderFarmerApi(session, "TOK")  # type: ignore[arg-type]
    with pytest.raises(ApiError) as err:
        await api.get_rooms()
    assert err.value.code == "401"


async def test_plaintext_error_page() -> None:
    session = FakeSession(FakeResponse('{"code":"500","msg":"boom"}', status=500))
    api = SpiderFarmerApi(session, "TOK")  # type: ignore[arg-type]
    with pytest.raises(ApiError):
        await api.get_rooms()


async def test_get_all_devices_across_rooms() -> None:
    device = {"deviceSerialnum": "S1", "productType": "SF-GGS-PS5", "deviceInfo": "{}"}
    session = FakeSession(ok([{"id": 1}, {"id": 2}]), ok([device]), ok([device]))
    api = SpiderFarmerApi(session, "TOK")  # type: ignore[arg-type]
    devices = await api.get_all_devices(5)
    assert [d.serial for d in devices] == ["S1"]
    assert session.requests[1]["payload"] == {"belonginRoomId": 1, "userId": 5}


async def test_history_range_is_sent_in_utc() -> None:
    from datetime import datetime, timedelta, timezone

    session = FakeSession(ok([]))
    api = SpiderFarmerApi(session, "TOK")  # type: ignore[arg-type]
    cet = timezone(timedelta(hours=1))
    await api.get_sensor_history(
        "S1", datetime(2026, 10, 27, 0, 0, tzinfo=cet), datetime(2026, 10, 27, 12, 0, tzinfo=cet)
    )
    payload = session.requests[0]["payload"]
    assert payload["startDate"] == "2026-10-26 23:00:00"
    assert payload["endDate"] == "2026-10-27 11:00:00"
