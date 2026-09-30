"""Transports used to reach a RetroTINK-4K.

Two ways are supported:

* ``SerialTransport``  - the RetroTINK is plugged by USB into the Home Assistant host.
* ``DonutShopTransport`` - the RetroTINK has a DonutShop (Arduino Nano ESP32) dongle
  plugged into it, and Home Assistant talks to that dongle over Wi-Fi.

Both take the exact same RetroTINK serial command strings ("remote menu",
"pwr on", "remote pwr", ...). This module has no Home Assistant import so it
can be tested on its own.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

SERIAL_BAUD = 115200
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=5)

# Values seen in DonutShop's /api/status "power_state" field.
POWER_STATES_ON = {"awake", "on", "booting"}
POWER_STATES_OFF = {"sleep", "asleep", "sleeping", "off", "standby"}


class TransportError(Exception):
    """Raised when a command could not be delivered."""


class SerialTransport:
    """Send commands over a local USB serial port."""

    def __init__(self, port: str) -> None:
        self.port = port

    def configure(self) -> None:
        """Set the port's line settings (blocking)."""
        try:
            subprocess.run(
                ["stty", "-F", self.port, str(SERIAL_BAUD), "cs8", "-cstopb", "-parenb"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            _LOGGER.warning("Could not configure serial port %s: %s", self.port, err)

    def test(self) -> bool:
        """Return True if the port can be opened (blocking)."""
        import serial  # pylint: disable=import-outside-toplevel

        try:
            serial.Serial(self.port, SERIAL_BAUD, timeout=1).close()
            return True
        except serial.SerialException:
            return False

    def send(self, command: str) -> None:
        """Write one command line (blocking)."""
        import serial  # pylint: disable=import-outside-toplevel

        try:
            with serial.Serial(
                self.port,
                SERIAL_BAUD,
                bytesize=serial.EIGHTBITS,
                stopbits=serial.STOPBITS_ONE,
                parity=serial.PARITY_NONE,
                timeout=1,
            ) as ser:
                ser.write(f"{command}\n".encode("ascii"))
        except serial.SerialException as err:
            raise TransportError(str(err)) from err


class DonutShopTransport:
    """Send commands to a DonutShop dongle over the network.

    Commands go to ``POST /api/command`` (DonutShop v0.7.25+). If that endpoint
    is missing, the older ``POST /cmd`` endpoint (raw text body, same as the
    DonutShop web terminal uses) is used instead, so v0.6.x also works.
    """

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        host = host.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self.base_url = host
        self._use_legacy_cmd = False

    async def info(self) -> dict[str, Any] | None:
        """Return /api/info, or None if the dongle is too old to have it."""
        data = await self._get_json("/api/info")
        return data if data and data.get("ok") else None

    async def test(self) -> bool:
        """Return True if a DonutShop answers at this address."""
        try:
            if await self.info() is not None:
                return True
            async with self._session.get(
                f"{self.base_url}/", timeout=HTTP_TIMEOUT
            ) as resp:
                return resp.status < 500
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False

    async def status(self) -> dict[str, Any] | None:
        """Return the parsed /api/status payload, or None if unavailable.

        DonutShop answers ``{"ok": false}`` while its WebCtl page is open in a
        browser, or while the RetroTINK serial link is busy. Callers should
        keep their previous state in that case. Raises TransportError if the
        dongle itself cannot be reached.
        """
        try:
            data = await self._get_json("/api/status")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise TransportError(f"{self.base_url}: {err}") from err
        if not data or not data.get("ok"):
            return None
        return data

    async def send(self, command: str) -> None:
        """Send one RetroTINK serial command."""
        try:
            if not self._use_legacy_cmd:
                async with self._session.post(
                    f"{self.base_url}/api/command",
                    json={"command": command},
                    timeout=HTTP_TIMEOUT,
                ) as resp:
                    if resp.status == 404:
                        _LOGGER.info(
                            "%s has no /api/command, falling back to /cmd", self.base_url
                        )
                        self._use_legacy_cmd = True
                    else:
                        body = await resp.text()
                        if resp.status >= 400:
                            raise TransportError(f"HTTP {resp.status}: {body}")
                        return

            async with self._session.post(
                f"{self.base_url}/cmd",
                data=command.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
                timeout=HTTP_TIMEOUT,
            ) as resp:
                if resp.status >= 400:
                    raise TransportError(f"HTTP {resp.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise TransportError(f"{self.base_url}: {err}") from err

    async def _get_json(self, path: str) -> dict[str, Any] | None:
        async with self._session.get(
            f"{self.base_url}{path}", timeout=HTTP_TIMEOUT
        ) as resp:
            if resp.status == 404:
                return None
            text = await resp.text()
        try:
            data = json.loads(text)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None


def power_state_to_bool(value: str | None) -> bool | None:
    """Map DonutShop's power_state string to on/off, or None if unknown."""
    if not value:
        return None
    value = value.lower()
    if value in POWER_STATES_ON:
        return True
    if value in POWER_STATES_OFF:
        return False
    return None
