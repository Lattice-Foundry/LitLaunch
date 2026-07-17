"""Small redaction helpers for diagnostics and console previews."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

SENSITIVE_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "api-key",
)
SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(token|secret|password|passwd|api_key|apikey|key)"
    r"(\s*[:=]\s*)"
    r"([^\s,;]+)"
)
SENSITIVE_WORD_PATTERN = re.compile(
    r"(?i)\b((?:token|secret|password|passwd|api_key|apikey|key)\s+)"
    r"([A-Za-z0-9._~+/=-]{6,})"
)
# Redact userinfo credentials embedded in URLs (scheme://user:pass@host),
# independent of the surrounding key name, so a credential-bearing value cannot
# leak just because its key does not look sensitive.
URL_CREDENTIAL_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^\s/:@]+:[^\s/@]+@")


def format_command_preview(command: Sequence[str]) -> str:
    """Format a shell-free command sequence for display with basic redaction."""

    return subprocess.list2cmdline(redact_sensitive_args(command))


def format_env_preview(env: Mapping[str, str]) -> str:
    """Format environment overrides for display without exposing secrets."""

    parts: list[str] = []
    for key in sorted(env):
        value = str(env[key])
        if _is_sensitive_argument_name(key):
            parts.append(f"{key}=<redacted>")
        else:
            parts.append(f"{key}={redact_sensitive_text(value)}")
    return ", ".join(parts)


def redact_sensitive_args(command: Sequence[str]) -> tuple[str, ...]:
    """Redact sensitive-looking command argument values."""

    redacted: list[str] = []
    redact_next = False
    for part in command:
        value = str(part)
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        if _is_sensitive_argument_name(value):
            if "=" in value:
                key, _separator, _secret = value.partition("=")
                redacted.append(f"{key}=<redacted>")
            else:
                redacted.append(value)
                redact_next = True
            continue
        redacted.append(redact_sensitive_text(value))
    return tuple(redacted)


def redact_sensitive_text(value: object) -> str:
    """Redact sensitive-looking values in display/report strings."""

    text = str(value)
    text = URL_CREDENTIAL_PATTERN.sub(r"\1<redacted>@", text)
    text = SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1\2<redacted>", text)
    text = SENSITIVE_WORD_PATTERN.sub(r"\1<redacted>", text)
    return _redact_local_path_prefixes(text)


def sanitize_report_dict(value: object) -> object:
    """Recursively redact strings in a report-like data structure."""

    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        return {
            redact_sensitive_text(key): sanitize_report_dict(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [sanitize_report_dict(item) for item in value]
    return value


def _is_sensitive_argument_name(value: str) -> bool:
    lowered = value.lower().lstrip("-")
    name = lowered.split("=", 1)[0]
    if name in {"server.sslcertfile", "server.sslkeyfile"}:
        return True
    if any(marker in name for marker in SENSITIVE_MARKERS):
        return True
    return name == "key" or name.endswith((".key", "_key", "-key"))


def _redact_local_path_prefixes(text: str) -> str:
    redacted = text
    for prefix in _local_path_prefixes():
        flags = re.IGNORECASE if re.match(r"^[A-Za-z]:[\\/]", prefix) else 0
        redacted = re.sub(re.escape(prefix), "<user-home>", redacted, flags=flags)
    return redacted


def _local_path_prefixes() -> tuple[str, ...]:
    candidates: set[str] = set()
    for name in ("USERPROFILE", "HOME"):
        value = os.environ.get(name)
        if value:
            candidates.update(_path_variants(value))

    home_drive = os.environ.get("HOMEDRIVE")
    home_path = os.environ.get("HOMEPATH")
    if home_drive and home_path:
        candidates.update(_path_variants(f"{home_drive}{home_path}"))

    with suppress(RuntimeError):
        candidates.update(_path_variants(str(Path.home())))

    useful = {
        candidate.rstrip("\\/")
        for candidate in candidates
        if len(candidate.rstrip("\\/")) >= 5 and candidate.rstrip("\\/") not in {"/"}
    }
    return tuple(sorted(useful, key=len, reverse=True))


def _path_variants(path: str) -> tuple[str, ...]:
    normalized = path.strip().rstrip("\\/")
    if not normalized:
        return ()
    return (normalized, normalized.replace("\\", "/"), normalized.replace("/", "\\"))
