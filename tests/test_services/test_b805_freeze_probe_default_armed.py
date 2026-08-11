"""B-805 — die Freeze-Probe muss per Default scharf sein.

Vorfall 2026-08-11: 27 Minuten Stillstand, ``logs/freeze_stacks.log`` blieb
leer (letzter Eintrag 06:51 aus einem Harness-Lauf). Grund war nicht die
Erkennungslogik, sondern das Gate: Heartbeat (``main.py`` PBWindow-ctor) und
Watchdog-Thread (``main()``) verlangten ``PB_STUDIO_FREEZE_PROBE == "1"`` —
gesetzt wird die Variable nur von ``tests/gui_harness.py``. Beim normalen
Start lief also gar kein Watchdog.
"""
from __future__ import annotations

import re
from pathlib import Path

from services.freeze_probe import freeze_probe_enabled

MAIN_PY = Path(__file__).resolve().parents[2] / "main.py"


def test_default_ist_armiert():
    assert freeze_probe_enabled({}) is True


def test_explizites_opt_out_schaltet_ab():
    for value in ("0", "off", "false", "no", "OFF"):
        assert freeze_probe_enabled({"PB_STUDIO_FREEZE_PROBE": value}) is False


def test_harness_wert_bleibt_an():
    assert freeze_probe_enabled({"PB_STUDIO_FREEZE_PROBE": "1"}) is True


def test_main_py_nutzt_kein_gleich_1_gate_mehr():
    """Beide Gates in main.py duerfen nicht mehr auf ==\"1\" pruefen."""
    src = MAIN_PY.read_text(encoding="utf-8")
    offenders = re.findall(
        r'environ\.get\(\s*"PB_STUDIO_FREEZE_PROBE"\s*\)\s*==\s*"1"', src
    )
    assert not offenders, (
        "main.py schaltet die Freeze-Probe weiterhin nur bei "
        "PB_STUDIO_FREEZE_PROBE=1 scharf — der Normalstart bliebe blind."
    )
    assert src.count("freeze_probe_enabled()") >= 2, (
        "Heartbeat-Gate und Watchdog-Gate muessen beide ueber "
        "freeze_probe_enabled() laufen."
    )
