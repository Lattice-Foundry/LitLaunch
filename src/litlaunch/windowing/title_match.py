"""Shared window-title matching helpers for observational monitors."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from litlaunch.browsers import BrowserKind
from litlaunch.windowing.base import WindowInfo

_BROWSER_SUFFIX_PATTERN = re.compile(
    r"\s+[-\u2013\u2014]\s+"
    r"(?:microsoft\s+edge|google\s+chrome|chrome|chromium)\s*$",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_WEAK_TITLE_TOKENS = frozenset(
    {
        "app",
        "application",
        "browser",
        "chrome",
        "chromium",
        "edge",
        "google",
        "local",
        "localhost",
        "microsoft",
        "streamlit",
        "window",
    }
)


def matches_window_title(
    window_title: str,
    target_title: str,
    target_url: str | None = None,
) -> bool:
    """Return whether an observed browser title matches the expected title."""

    normalized_window = _normalize_title(window_title)
    normalized_target = _normalize_title(target_title)
    if not normalized_window and normalized_target != "streamlit app":
        return False
    if normalized_target and normalized_target in normalized_window:
        return True
    if normalized_target == "streamlit app":
        return True
    if matches_transient_url_title(window_title, target_url):
        return True
    return titles_are_near_match(window_title, target_title)


def matches_transient_url_title(window_title: str, target_url: str | None) -> bool:
    """Return whether a temporary URL-ish window title matches the target URL."""

    if not target_url:
        return False
    hostname = (urlparse(target_url).hostname or "").strip().lower()
    if not hostname:
        return False
    normalized_window = _normalize_title(window_title)
    raw_window = window_title.strip().lower()
    return (
        raw_window == hostname
        or raw_window.startswith(f"{hostname}_/")
        or raw_window.startswith(f"{hostname} ")
        or normalized_window.startswith(_normalize_title(hostname))
    )


def titles_are_near_match(window_title: str, target_title: str) -> bool:
    """Return whether two titles are a conservative token-overlap match."""

    window_tokens = _significant_title_tokens(window_title)
    target_tokens = _significant_title_tokens(target_title)
    if len(window_tokens) < 2 or len(target_tokens) < 2:
        return False
    overlap = window_tokens & target_tokens
    if len(overlap) < 2:
        return False
    shorter_ratio = len(overlap) / min(len(window_tokens), len(target_tokens))
    longer_ratio = len(overlap) / max(len(window_tokens), len(target_tokens))
    return shorter_ratio >= 0.8 and longer_ratio >= 0.6


def window_matches_browser_kind(
    window: WindowInfo,
    browser_kind: BrowserKind | None,
) -> bool:
    """Return whether a captured window belongs to the requested browser kind."""

    if browser_kind is None:
        return True
    process_name = (window.process_name or "").strip().lower()
    if process_name.endswith(".exe"):
        process_name = process_name[:-4]
    if browser_kind == BrowserKind.EDGE:
        return process_name in {"msedge", "microsoft-edge", "microsoft-edge-stable"}
    if browser_kind == BrowserKind.CHROME:
        return process_name in {
            "chrome",
            "chromium",
            "chromium-browser",
            "google-chrome",
            "google-chrome-stable",
        }
    return False


def _normalize_title(title: str) -> str:
    without_suffix = _BROWSER_SUFFIX_PATTERN.sub("", title.strip().lower())
    normalized = re.sub(r"[^a-z0-9]+", " ", without_suffix)
    return " ".join(normalized.split())


def _significant_title_tokens(title: str) -> set[str]:
    normalized = _BROWSER_SUFFIX_PATTERN.sub("", title.strip().lower())
    return {
        token
        for token in _TOKEN_PATTERN.findall(normalized)
        if token not in _WEAK_TITLE_TOKENS
    }
