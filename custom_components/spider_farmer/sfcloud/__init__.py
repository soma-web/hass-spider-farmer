"""Spider Farmer cloud protocol library (REST + MQTT).

This package must not import anything from Home Assistant and uses only
relative imports internally, so it can be imported standalone as `sfcloud`
(tests, CLI, Windows) as well as part of the integration.
"""

from .exceptions import ApiError, AuthError, CannotConnect, SpiderFarmerError
from .models import Device, LoginResult, topic_prefix
from .mqtt import DeviceState, SpiderFarmerMqtt
from .rest import SpiderFarmerApi

__all__ = [
    "ApiError",
    "AuthError",
    "CannotConnect",
    "Device",
    "DeviceState",
    "LoginResult",
    "SpiderFarmerApi",
    "SpiderFarmerError",
    "SpiderFarmerMqtt",
    "topic_prefix",
]
