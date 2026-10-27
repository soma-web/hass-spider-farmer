"""Exceptions raised by the Spider Farmer cloud library."""

from __future__ import annotations


class SpiderFarmerError(Exception):
    """Base error."""


class CannotConnect(SpiderFarmerError):
    """Network/transport problem talking to the cloud."""


class ApiError(SpiderFarmerError):
    """The API answered with a non-success code."""

    def __init__(self, code: str | None, msg: str | None, path: str) -> None:
        super().__init__(f"{path}: code={code} msg={msg}")
        self.code = code
        self.msg = msg
        self.path = path


class AuthError(ApiError):
    """The token was rejected (expired / logged out) – a new login is needed."""
