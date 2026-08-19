from __future__ import annotations

import base64
import binascii
import hashlib
from urllib.parse import quote, unquote


OPERATIONS = frozenset({"base64_encode", "base64_decode", "url_encode", "url_decode", "sha256", "sha512"})


class TextToolError(ValueError):
    pass


def transform_text(operation: str, value: str) -> str:
    if operation not in OPERATIONS:
        raise TextToolError("unknown_operation")

    if operation == "base64_encode":
        return base64.b64encode(value.encode("utf-8")).decode("ascii")
    if operation == "base64_decode":
        compact = "".join(value.split())
        try:
            decoded = base64.b64decode(compact, validate=True)
            return decoded.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise TextToolError("invalid_base64") from exc
    if operation == "url_encode":
        return quote(value, safe="")
    if operation == "url_decode":
        return unquote(value)
    if operation == "sha256":
        return hashlib.sha256(value.encode("utf-8")).hexdigest()
    return hashlib.sha512(value.encode("utf-8")).hexdigest()
