"""Constants for the Spider Farmer integration."""

DOMAIN = "spider_farmer"
MANUFACTURER = "Spider Farmer"

CONF_TOKEN = "token"
CONF_USER_ID = "user_id"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_DEVICES = "devices"

# Fallback poll when the device stops pushing (it normally pushes every ~6 s).
POLL_INTERVAL_SECONDS = 60
# A device counts as offline when nothing arrived for this long.
OFFLINE_AFTER_SECONDS = 120
# How long setup waits for the first status from the cloud.
FIRST_DATA_TIMEOUT_SECONDS = 30
