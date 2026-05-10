"""B-296 Phase F: OnboardingBanner default-visible, dismiss persists via QSettings."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings


@pytest.fixture(autouse=True)
def _clean_settings():
    """Use isolated QSettings org to avoid test cross-talk."""
    s = QSettings("PBStudioTest", "PBStudioTestApp")
    s.clear()
    yield
    s.clear()


def _make_banner(banner_id="test_banner", message="Test", organization=None):
    """Helper that constructs an OnboardingBanner with isolated QSettings."""
    if organization is None:
        organization = ("PBStudioTest", "PBStudioTestApp")
    from ui.widgets.onboarding_banner import OnboardingBanner
    return OnboardingBanner(
        banner_id=banner_id,
        message=message,
        qsettings_org=organization,
    )


def test_b296_banner_visible_default(qapp):
    banner = _make_banner()
    assert banner.isVisible() or not banner.isHidden(), (
        "B-296: OnboardingBanner default-sichtbar erwartet."
    )


def test_b296_banner_dismiss_hides(qapp):
    banner = _make_banner()
    banner.btn_dismiss.click()
    assert banner.isHidden(), "B-296: Dismiss-Klick versteckt Banner."


def test_b296_banner_dismiss_persists(qapp):
    banner = _make_banner(banner_id="persist_test")
    banner.btn_dismiss.click()
    # Re-construct with same banner_id and isolated settings
    banner2 = _make_banner(banner_id="persist_test")
    assert banner2.isHidden(), (
        "B-296: nach Dismiss + Re-Construct ist Banner via QSettings versteckt."
    )


def test_b296_banner_set_message(qapp):
    banner = _make_banner(message="Anfang")
    banner.set_message("Geaendert")
    assert "Geaendert" in banner.lbl.text()
