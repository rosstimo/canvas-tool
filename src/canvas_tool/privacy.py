from __future__ import annotations

from typing import Any

from .normalize import sanitize as _base_sanitize


_EXTRA_PRIVATE_KEYS = {
    "consumer_key",
    "shared_secret",
    "client_secret",
    "custom_fields",
    "student_ids",
    "user_ids",
    "member_ids",
    "users",
    "members",
    "invitees",
}


def sanitize(value: Any) -> Any:
    """Apply the normal Canvas sanitizer plus defense-in-depth identity/credential stripping."""
    return _strip_extra(_base_sanitize(value))


def _strip_extra(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_extra(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _strip_extra(item)
        for key, item in value.items()
        if key not in _EXTRA_PRIVATE_KEYS
    }
