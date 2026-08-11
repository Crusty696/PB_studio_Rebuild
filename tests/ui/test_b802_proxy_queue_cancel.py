"""B-802: die unsichtbare Proxy-Warteschlange muss abbrechbar sein.

Live-Befund 2026-08-11: bei einem Ordner-Import mit 486 Clips existieren nur
``_PROXY_MAX_ACTIVE = 2`` sichtbare, cancelbare Tasks. Die restlichen 484
Auftraege warten in ``_proxy_pending`` — ohne Task, ohne Zeile im TASKS-Panel,
ohne Cancel-Pfad. Ein Abbruch toetete den laufenden Job, danach rueckte sofort
der naechste nach: der Abbruch *beschleunigte* die Queue, statt sie zu stoppen
(gemessen ~0.3 Konvertierungen/s trotz Abbruch).

Zweiter Defekt: ``_proxy_pending`` kannte repo-weit nur ``append`` und
``popleft`` — kein ``clear()``. Die Queue ueberlebte damit den Projektwechsel
und erzeugte Proxies fuer Clips, die im neuen Projekt gar nicht existieren.

Getestet wird die Queue-Logik direkt, ohne echte Worker und ohne ffmpeg — die
Startfunktion wird ersetzt und nur mitgeschrieben, was gestartet worden waere.
Die Cancel-Kette des *laufenden* Workers ist nicht Gegenstand dieser Tests;
die ist verdrahtet und durch B-362 abgedeckt.
"""

from __future__ import annotations

import os
from collections import deque
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def ctrl():
    """VideoAnalysisController ohne Qt-Aufbau, mit protokolliertem Start."""
    from ui.controllers.video_analysis import VideoAnalysisController

    c = VideoAnalysisController.__new__(VideoAnalysisController)
    c.window = SimpleNamespace(console_text=SimpleNamespace(append=lambda _t: None))
    c._proxy_pending = deque()
    c._proxy_active = 0
    c._proxy_queue_stopped = False
    c.gestartet: list[int] = []

    def _fake_launch(clip_id, video_path, title):
        c.gestartet.append(clip_id)

    c._launch_proxy_worker = _fake_launch
    return c


def _fuellen(c, anzahl: int) -> None:
    for i in range(anzahl):
        c._start_proxy_creation(i, f"/tmp/clip{i}.mp4", f"Clip {i}")


def test_b802_nur_max_active_starten_rest_wartet(ctrl):
    """Ausgangslage: von 486 Auftraegen laufen 2, der Rest wartet unsichtbar."""
    _fuellen(ctrl, 486)
    assert len(ctrl.gestartet) == ctrl._PROXY_MAX_ACTIVE
    assert len(ctrl._proxy_pending) == 486 - ctrl._PROXY_MAX_ACTIVE


def test_b802_abbruch_leert_die_wartende_queue(ctrl):
    """Der Kern des Tickets: Abbrechen muss die Wartenden verwerfen."""
    _fuellen(ctrl, 486)
    wartend_vorher = len(ctrl._proxy_pending)

    verworfen = ctrl.cancel_pending_proxies("Test")

    assert verworfen == wartend_vorher
    assert len(ctrl._proxy_pending) == 0, (
        "B-802: nach dem Abbruch warten immer noch Auftraege in der Queue."
    )


def test_b802_nach_abbruch_rueckt_nichts_mehr_nach(ctrl):
    """Der eigentliche Schaden: der Abbruch beschleunigte die Queue.

    Nach dem Cancel meldete der beendete Worker seinen Slot frei, worauf
    ``_drain_proxy_queue`` sofort den naechsten Auftrag startete.
    """
    _fuellen(ctrl, 486)
    ctrl.cancel_pending_proxies("Test")
    gestartet_bei_abbruch = len(ctrl.gestartet)

    # Beide laufenden Worker melden sich ab — wie im echten Ablauf.
    ctrl._proxy_slot_released()
    ctrl._proxy_slot_released()

    assert len(ctrl.gestartet) == gestartet_bei_abbruch, (
        "B-802: nach dem Abbruch wurde ein weiterer Proxy-Auftrag gestartet — "
        "genau das machte den Abbruch wirkungslos."
    )


def test_b802_neuer_auftrag_hebt_die_sperre_auf(ctrl):
    """Nach einem Abbruch darf die Queue nicht dauerhaft taub bleiben."""
    _fuellen(ctrl, 10)
    ctrl.cancel_pending_proxies("Test")
    ctrl._proxy_active = 0

    ctrl._start_proxy_creation(999, "/tmp/neu.mp4", "Neuer Clip")

    assert 999 in ctrl.gestartet, (
        "B-802: ein neuer Import nach einem Abbruch wurde nicht mehr gestartet."
    )


def test_b802_projektwechsel_setzt_queue_zurueck(ctrl):
    """Zweiter Defekt: die Queue ueberlebte den Projektwechsel."""
    _fuellen(ctrl, 486)
    assert len(ctrl._proxy_pending) > 0

    verworfen = ctrl.reset_proxy_queue("Projektwechsel")

    assert verworfen > 0
    assert len(ctrl._proxy_pending) == 0, (
        "B-802: nach dem Projektwechsel warten noch Auftraege des alten Projekts."
    )
    assert ctrl._proxy_active == 0
    assert ctrl._proxy_queue_stopped is False, (
        "B-802: nach einem Projektwechsel muss die Queue wieder aufnahmebereit "
        "sein — sonst startet im neuen Projekt kein Import mehr."
    )


def test_b802_reset_erlaubt_sofort_neue_auftraege(ctrl):
    """Nach dem Projektwechsel muss ein Import sofort wieder laufen."""
    _fuellen(ctrl, 486)
    ctrl.reset_proxy_queue("Projektwechsel")

    ctrl._start_proxy_creation(4242, "/tmp/neu.mp4", "Clip im neuen Projekt")

    assert 4242 in ctrl.gestartet
