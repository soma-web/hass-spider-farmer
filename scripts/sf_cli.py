"""Command line tool to exercise the Spider Farmer cloud library against real hardware.

Usage (from the repo root, with the venv active):
    python scripts/sf_cli.py login you@example.com          # e-mails a code
    python scripts/sf_cli.py login you@example.com 123456   # logs in with it
    python scripts/sf_cli.py devices
    python scripts/sf_cli.py status <serial>
    python scripts/sf_cli.py watch
    python scripts/sf_cli.py set <serial> blower mOnOff=1 mLevel=35
    python scripts/sf_cli.py set <serial> outlet.O3 mOnOff=1
    python scripts/sf_cli.py history <serial> --hours 6
    python scripts/sf_cli.py call udm/getUserRooms/v2 '{}'

The session (token + MQTT credentials) is stored in `sf.session.json`
(git-ignored). Add `-v` for debug logging of every REST call and MQTT message.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "spider_farmer"))

from sfcloud import AuthError, Device, SpiderFarmerApi, SpiderFarmerMqtt

SESSION_FILE = Path("sf.session.json")


def dump(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def load_session() -> dict[str, Any]:
    if not SESSION_FILE.exists():
        sys.exit("No session – run `login <email>` and then `login <email> <code>` first.")
    return json.loads(SESSION_FILE.read_text(encoding="utf-8"))


def parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


async def cmd_login(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    if not args.code:
        await api.request_email_code(args.email)
        print(f"Code sent to {args.email}. Now run: login {args.email} <code>")
        return
    result = await api.login(args.email, args.code)
    session = {
        "email": args.email,
        "token": result.token,
        "user_id": result.user_id,
        "mqtt_username": result.mqtt_username,
        "mqtt_password": result.mqtt_password,
    }
    try:
        session["region"] = await api.get_region()
    except Exception as err:
        print(f"(region lookup failed: {err})")
    SESSION_FILE.write_text(json.dumps(session, indent=2), encoding="utf-8")
    print(f"Logged in as {result.nick_name} (userId {result.user_id}), saved {SESSION_FILE}")


async def load_devices(api: SpiderFarmerApi, session: dict[str, Any]) -> list[Device]:
    """Devices via REST; falls back to the cached list when the token was replaced."""
    try:
        devices = await api.get_all_devices(session["user_id"])
    except AuthError:
        if "devices" not in session:
            raise
        print("(REST token replaced by another login – using cached device list)")
        return [Device.from_api(raw) for raw in session["devices"]]
    session["devices"] = [d.raw for d in devices]
    SESSION_FILE.write_text(json.dumps(session, indent=2), encoding="utf-8")
    return devices


async def cmd_devices(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    session = load_session()
    if args.raw:
        rooms = await api.get_rooms()
        print("== rooms ==")
        dump(rooms)
    for d in await load_devices(api, session):
        print(f"\n== {d.name} ({d.product_type}) serial={d.serial} online={d.online}")
        print(f"   UP:   {d.up_topic}\n   DOWN: {d.down_topic}")
        dump(d.raw if args.raw else d.info)
        if args.raw:
            print("-- socket names --")
            dump(await api.get_socket_names(d.serial))


def make_mqtt(session: dict[str, Any], devices: list[Device], **kwargs: Any) -> SpiderFarmerMqtt:
    return SpiderFarmerMqtt(
        session["mqtt_username"],
        session["mqtt_password"],
        session["user_id"],
        devices,
        **kwargs,
    )


async def wait_connected(mqtt: SpiderFarmerMqtt, timeout: float = 20) -> None:
    for _ in range(int(timeout * 10)):
        if mqtt.connected:
            return
        await asyncio.sleep(0.1)
    sys.exit("MQTT connection timed out")


def pick(devices: list[Device], serial: str) -> list[Device]:
    found = [d for d in devices if d.serial == serial]
    if not found:
        sys.exit(f"Unknown serial {serial}; known: {[d.serial for d in devices]}")
    return found


async def cmd_status(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    session = load_session()
    devices = pick(await load_devices(api, session), args.serial)
    mqtt = make_mqtt(session, devices)
    task = asyncio.create_task(mqtt.run())
    await wait_connected(mqtt)
    for method in ("getSysSta", "getDevSta", "getConfigFile"):
        print(f"\n== {method} ==")
        try:
            dump(await mqtt.query(args.serial, method))
        except TimeoutError:
            print("(no reply)")
    task.cancel()


async def cmd_watch(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    session = load_session()
    devices = await load_devices(api, session)
    if args.serial:
        devices = pick(devices, args.serial)

    def on_message(serial: str | None, msg: dict[str, Any]) -> None:
        print(f"\n[{datetime.now():%H:%M:%S}] {serial} {msg.get('method')}")
        dump(msg)

    mqtt = make_mqtt(
        session,
        devices,
        on_message=on_message,
        on_connection_change=lambda c: print(f"-- MQTT connected={c}"),
    )
    print("Watching (Ctrl+C to stop) …")
    await mqtt.run()


async def cmd_set(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    session = load_session()
    devices = pick(await load_devices(api, session), args.serial)
    patch = {}
    for item in args.fields:
        key, _, value = item.partition("=")
        patch[key] = parse_value(value)

    mqtt = make_mqtt(
        session,
        devices,
        on_message=lambda s, m: print(f"\n<- {m.get('method')}") or dump(m),
    )
    task = asyncio.create_task(mqtt.run())
    await wait_connected(mqtt)
    await mqtt.query(args.serial, "getConfigFile")
    print("\n-> sending:")
    key_path = args.component.split(".") if "." in args.component else ["device", args.component]
    dump(await mqtt.set_config(args.serial, key_path, patch))
    await asyncio.sleep(2)
    await mqtt.request(args.serial, "getDevSta")
    await asyncio.sleep(args.wait)
    task.cancel()


async def cmd_history(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    load_session()
    end = datetime.now(UTC)
    dump(await api.get_sensor_history(args.serial, end - timedelta(hours=args.hours), end))


async def cmd_call(api: SpiderFarmerApi, args: argparse.Namespace) -> None:
    load_session()
    dump(await api.call_raw(args.path, json.loads(args.payload)))


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="without code: e-mail a code; with code: log in")
    p.add_argument("email")
    p.add_argument("code", nargs="?")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("devices", help="list devices")
    p.add_argument("--raw", action="store_true", help="show rooms, raw device data, socket names")
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("status", help="getSysSta/getDevSta/getConfigFile over MQTT")
    p.add_argument("serial")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("watch", help="print all MQTT messages")
    p.add_argument("serial", nargs="?")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("set", help="setConfigField, e.g. `set <serial> blower mOnOff=1`")
    p.add_argument("serial")
    p.add_argument("component", help="blower | fan | light | outlet.O1 … (path in configFile)")
    p.add_argument("fields", nargs="+", help="key=value (JSON values allowed)")
    p.add_argument("--wait", type=float, default=5, help="seconds to watch replies")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("history", help="sensor history via REST")
    p.add_argument("serial")
    p.add_argument("--hours", type=float, default=2)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("call", help="raw REST call, prints the decrypted envelope")
    p.add_argument("path", help="e.g. udm/getUserRooms/v2")
    p.add_argument("payload", nargs="?", default="{}")
    p.set_defaults(func=cmd_call)

    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    token = load_session().get("token") if SESSION_FILE.exists() else None
    async with aiohttp.ClientSession() as http:
        await args.func(SpiderFarmerApi(http, token), args)


if __name__ == "__main__":
    try:
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    except KeyboardInterrupt:
        pass
