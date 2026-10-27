"""AES body cipher used by the Spider Farmer REST API.

Every request and response body is AES-128-CBC + PKCS7, Base64-encoded, with a
static key/IV shipped in the app. It is obfuscation, not a security boundary;
authentication is the login token.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = b"Meizhi1234567890"
IV = b"1234567890123456"


def _cipher() -> Cipher:
    return Cipher(algorithms.AES(KEY), modes.CBC(IV))


def encrypt(payload: Any) -> str:
    """Serialize `payload` as JSON and encrypt it into the Base64 wire body."""
    plaintext = json.dumps(payload if payload is not None else {}, separators=(",", ":"))
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    encryptor = _cipher().encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")


def decrypt(body: str) -> Any:
    """Decrypt a Base64 wire body; returns parsed JSON (or text if not JSON)."""
    decryptor = _cipher().decryptor()
    padded = decryptor.update(base64.b64decode(body)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    text = (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
