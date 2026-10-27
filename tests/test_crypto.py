"""Tests for the AES body cipher."""

from sfcloud import crypto

# Regression vector; JSON is compact like JSON.stringify in the app/Node client.
LOGIN_CODE_PAYLOAD = {"email": "you@example.com", "isLogin": 1}
LOGIN_CODE_WIRE = "8DrM8ExhmYtyFeZB4qDRe5Sj4GGpQ6wgz6Z9cGmhOPKaKe/oUCg8i2285zTL3SrP"


def test_encrypt_known_vector() -> None:
    assert crypto.encrypt(LOGIN_CODE_PAYLOAD) == LOGIN_CODE_WIRE


def test_roundtrip() -> None:
    payload = {"code": "000", "msg": "Bestätigungscode", "data": {"list": [1, 2, 3]}}
    assert crypto.decrypt(crypto.encrypt(payload)) == payload


def test_none_payload_is_empty_object() -> None:
    assert crypto.decrypt(crypto.encrypt(None)) == {}
