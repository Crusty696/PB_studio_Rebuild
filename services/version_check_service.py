"""Version check service for PB Studio.

Fetches the latest GitHub release in a background QThread (non-blocking).
Fails silently when offline or when the remote is unreachable.

Usage:
    checker = VersionCheckWorker(current_version="0.5.0")
    checker.update_available.connect(my_slot)
    checker.start()

Signals:
    update_available(str latest_version, str download_url)
        Emitted only when a newer release is found.
        Always emitted when the check completes (success or failure).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional, Tuple

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)

# Override via env var for self-hosted / private repos:
#   PBSTUDIO_UPDATE_API_URL=https://api.github.com/repos/youruser/pb-studio-rebuild/releases/latest
_DEFAULT_API_URL = os.environ.get(
    "PBSTUDIO_UPDATE_API_URL",
    "https://api.github.com/repos/PB-Studio/pb-studio-rebuild/releases/latest",
)
_REQUEST_TIMEOUT = 8  # seconds


def _parse_version(version_str: str) -> Optional[Tuple[int, ...]]:
    """Parse a semver-like string into a tuple of ints.

    Strips a leading 'v' if present.  Returns None on parse failure.
    """
    version_str = version_str.lstrip("v").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        return None
    return tuple(int(x) for x in match.groups())


def _is_newer(latest: Tuple[int, ...], current: Tuple[int, ...]) -> bool:
    return latest > current


class VersionCheckWorker(QThread):
    """Background thread that checks for a newer release on GitHub."""

    # Emitted when a newer version is available
    update_available = Signal(str, str)  # (latest_version, download_url)
    # Always emitted when the check is done (success or silent failure)

    def __init__(self, current_version: str, api_url: str = _DEFAULT_API_URL, parent=None):
        super().__init__(parent)
        self._current_version = current_version
        self._api_url = api_url

    def run(self) -> None:
        try:
            self._do_check()
        except Exception as exc:  # broad catch intentional — background version check must never crash app, network/parse errors possible
            # Any unexpected error: log at DEBUG level, never surface to user
            logger.debug("Version check failed unexpectedly: %s", exc)

    def _do_check(self) -> None:
        """Perform the actual HTTP request and comparison."""
        import urllib.error
        import urllib.request
        import json

        current_tuple = _parse_version(self._current_version)
        if current_tuple is None:
            logger.warning("Cannot parse current version '%s', skipping update check", self._current_version)
            return

        try:
            req = urllib.request.Request(
                self._api_url,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "PBStudio-UpdateCheck/1.0"},
            )
            with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            # Network unavailable / offline mode — fail silently
            logger.debug("Version check: network unavailable (%s)", exc.reason)
            return
        except TimeoutError:
            logger.debug("Version check: request timed out")
            return
        except OSError as exc:
            logger.debug("Version check: OS error (%s)", exc)
            return

        tag = data.get("tag_name", "")
        latest_tuple = _parse_version(tag)
        if latest_tuple is None:
            logger.debug("Version check: cannot parse tag '%s'", tag)
            return

        if not _is_newer(latest_tuple, current_tuple):
            logger.debug("Version check: up to date (current=%s, latest=%s)", self._current_version, tag)
            return

        download_url = data.get("html_url", "")
        # Prefer the first browser-downloadable asset if present
        assets = data.get("assets", [])
        for asset in assets:
            if asset.get("browser_download_url"):
                download_url = asset["browser_download_url"]
                break

        logger.info("New version available: %s (current: %s)", tag, self._current_version)
        self.update_available.emit(tag.lstrip("v"), download_url)
