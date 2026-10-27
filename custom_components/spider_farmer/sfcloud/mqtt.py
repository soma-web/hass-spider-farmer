"""Realtime status and control over the Spider Farmer cloud MQTT broker.

Payloads are plaintext JSON (no AES). Per device:
  <prefix>/API/UP/<serial>    device -> client (status replies / pushes)
  <prefix>/API/DOWN/<serial>  client -> device (requests and commands)

Note for Windows: aiomqtt needs a selector event loop, e.g.
`asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import aiomqtt

from .exceptions import CannotConnect
from .models import Device

_LOGGER = logging.getLogger(__name__)

DEFAULT_HOST = "sf.mqtt.spider-farmer.com"
DEFAULT_PORT = 8883

GET_SYS_STA = "getSysSta"
GET_DEV_STA = "getDevSta"
GET_CONFIG_FILE = "getConfigFile"
SET_CONFIG_FIELD = "setConfigField"

INITIAL_REQUESTS = (GET_SYS_STA, GET_DEV_STA, GET_CONFIG_FILE)

MessageCallback = Callable[[str | None, dict[str, Any]], None]
ConnectionCallback = Callable[[bool], None]


@dataclass(slots=True)
class DeviceState:
    """Last known MQTT state of one device."""

    sys: dict[str, Any] | None = None
    dev: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


def _msg_id() -> str:
    return str(int(time.time() * 1000))


def component_config(config: dict[str, Any] | None, comp: str) -> dict[str, Any]:
    """Current sub-config of `comp` from a getConfigFile payload."""
    if not config:
        return {}
    # TODO(M1): confirm whether getConfigFile nests components under "device".
    root = config.get("device") if isinstance(config.get("device"), dict) else config
    return dict(root.get(comp) or {})


def build_set_config(
    serial: str, user_id: str, comp: str, current: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """A setConfigField command carrying the complete merged sub-config."""
    return {
        "method": SET_CONFIG_FIELD,
        "pid": serial,
        "uid": user_id,
        "msgId": _msg_id(),
        "params": {"keyPath": ["device", comp], comp: {**current, **patch}},
    }


def _tls_context() -> ssl.SSLContext:
    # The broker uses a self-signed certificate.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class SpiderFarmerMqtt:
    """Keeps one broker connection for all devices of an account."""

    def __init__(
        self,
        username: str,
        password: str,
        user_id: int | str,
        devices: Iterable[Device],
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        client_id: str | None = None,
        on_message: MessageCallback | None = None,
        on_connection_change: ConnectionCallback | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self.user_id = str(user_id)
        self.devices = {d.serial: d for d in devices}
        self._by_up_topic = {d.up_topic: d.serial for d in self.devices.values()}
        self._host = host
        self._port = port
        # Unique id so we never kick the official app (or another HA) off the broker.
        self._client_id = client_id or f"sfhass_{uuid.uuid4().hex[:12]}"
        self._on_message = on_message
        self._on_connection_change = on_connection_change
        self.states: dict[str, DeviceState] = {s: DeviceState() for s in self.devices}
        self._client: aiomqtt.Client | None = None
        self._waiters: dict[tuple[str, str], list[asyncio.Future]] = defaultdict(list)

    @property
    def offline_topic(self) -> str:
        return f"SF/Offline/{self.user_id}"

    @property
    def connected(self) -> bool:
        return self._client is not None

    async def run(self, reconnect_interval: float = 10) -> None:
        """Connect and process messages forever, reconnecting on errors."""
        while True:
            try:
                await self._run_once()
            except aiomqtt.MqttError as err:
                _LOGGER.warning("MQTT connection lost: %s", err)
            finally:
                if self._client is not None:
                    self._client = None
                    if self._on_connection_change:
                        self._on_connection_change(False)
            await asyncio.sleep(reconnect_interval)

    async def _run_once(self) -> None:
        async with aiomqtt.Client(
            self._host,
            self._port,
            username=self._username,
            password=self._password,
            identifier=self._client_id,
            tls_context=_tls_context(),
            keepalive=60,
        ) as client:
            self._client = client
            if self._on_connection_change:
                self._on_connection_change(True)
            for topic in [*self._by_up_topic, self.offline_topic]:
                await client.subscribe(topic)
            for serial in self.devices:
                for method in INITIAL_REQUESTS:
                    await self.request(serial, method)
            async for message in client.messages:
                self._handle(message.topic.value, message.payload)

    def _handle(self, topic: str, payload: Any) -> None:
        try:
            msg = json.loads(payload)
        except (TypeError, ValueError):
            _LOGGER.debug("Ignoring non-JSON message on %s: %r", topic, payload)
            return
        if not isinstance(msg, dict):
            return
        serial = self._by_up_topic.get(topic) or msg.get("pid")
        method = msg.get("method")
        _LOGGER.debug("MQTT %s (%s): %s", topic, method, msg)

        state = self.states.get(serial) if serial else None
        if state is not None and isinstance(msg.get("data"), dict):
            if method == GET_SYS_STA:
                state.sys = msg["data"]
            elif method == GET_DEV_STA:
                state.dev = msg["data"]
            elif method == GET_CONFIG_FILE:
                state.config = msg["data"]

        for fut in self._waiters.pop((serial, method), []):
            if not fut.done():
                fut.set_result(msg)
        if self._on_message:
            self._on_message(serial, msg)

    async def _publish(self, serial: str, payload: dict[str, Any]) -> None:
        if self._client is None:
            raise CannotConnect("MQTT not connected")
        _LOGGER.debug("MQTT publish %s: %s", self.devices[serial].down_topic, payload)
        await self._client.publish(self.devices[serial].down_topic, json.dumps(payload))

    async def request(self, serial: str, method: str) -> None:
        """Ask a device for getDevSta / getSysSta / getConfigFile / getDevOpLog."""
        await self._publish(
            serial, {"method": method, "msgId": _msg_id(), "pid": serial, "uid": self.user_id}
        )

    async def query(self, serial: str, method: str, timeout: float = 10) -> dict[str, Any]:
        """Send a request and wait for the matching reply."""
        fut = asyncio.get_running_loop().create_future()
        self._waiters[(serial, method)].append(fut)
        try:
            await self.request(serial, method)
            return await asyncio.wait_for(fut, timeout)
        finally:
            waiters = self._waiters.get((serial, method))
            if waiters and fut in waiters:
                waiters.remove(fut)

    async def set_component(self, serial: str, comp: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Merge `patch` into the component's full config and send it (like the app)."""
        state = self.states[serial]
        if state.config is None:
            await self.query(serial, GET_CONFIG_FILE)
        current = component_config(state.config, comp)
        command = build_set_config(serial, self.user_id, comp, current, patch)
        await self._publish(serial, command)
        merged = command["params"][comp]
        self._store_component(state, comp, merged)
        return command

    @staticmethod
    def _store_component(state: DeviceState, comp: str, value: dict[str, Any]) -> None:
        if state.config is None:
            state.config = {}
        root = state.config.get("device")
        target = root if isinstance(root, dict) else state.config
        target[comp] = value
