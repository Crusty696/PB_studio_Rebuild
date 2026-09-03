"""B-656 — Proxy-Worker laufen über eine Warteschlange, nicht alle sofort.

Per Mutationsprobe am 2026-09-03 als ungedeckt gefunden: neutralisiert man den
Fix in `ui/controllers/video_analysis.py:335`, bleibt die Suite grün
(`31 passed, 2 skipped in 124.10s`).

Der Schaden: Der B-056-Semaphor begrenzt nur die **ffmpeg-Läufe**. Die QThreads
pro Datei entstanden trotzdem sofort — ein Import mit 103 Dateien erzeugte über
100 idle Threads, die alle am Semaphor warteten. Ergebnis: GIL-Halt und
AppHang.

Der Fix stellt Aufträge in `_proxy_pending` und startet Threads nur für die
`_PROXY_MAX_ACTIVE` aktiven Slots.

Die Tests arbeiten gegen die Queue-Logik selbst, ohne Qt-Threads zu starten:
`_launch_proxy_worker` wird ersetzt, damit messbar wird, wie viele Worker
tatsächlich losgeschickt werden.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class _Controller:
    """Nur die Queue-Mechanik, mit den echten Methoden des Controllers."""

    def __init__(self, max_active: int = 2, fenster_lebt: bool = True):
        from ui.controllers.video_analysis import VideoAnalysisController

        self._PROXY_MAX_ACTIVE = max_active
        self._proxy_pending = deque()
        self._proxy_active = 0
        self._proxy_queue_stopped = False
        self._fenster_lebt = fenster_lebt
        self.gestartet: list[int] = []

        # Die echten Methoden, an dieses Objekt gebunden.
        self._drain_proxy_queue = VideoAnalysisController._drain_proxy_queue.__get__(self)
        self._start_proxy_creation = (
            VideoAnalysisController._start_proxy_creation.__get__(self))
        self._proxy_slot_released = (
            VideoAnalysisController._proxy_slot_released.__get__(self))

    def _window_alive(self) -> bool:
        return self._fenster_lebt

    def _launch_proxy_worker(self, clip_id, video_path, title):
        self.gestartet.append(clip_id)


def test_bei_103_dateien_starten_nur_zwei_worker():
    """Der Kern des Befunds — genau der Fall aus dem Schadensbild."""
    c = _Controller(max_active=2)

    for clip_id in range(103):
        c._start_proxy_creation(clip_id, f"/v/{clip_id}.mp4", f"Clip {clip_id}")

    assert len(c.gestartet) == 2, (
        f"{len(c.gestartet)} Worker gestartet statt 2 — die Warteschlange greift nicht"
    )
    assert len(c._proxy_pending) == 101


def test_ein_freier_slot_zieht_genau_einen_auftrag_nach():
    c = _Controller(max_active=2)
    for clip_id in range(5):
        c._start_proxy_creation(clip_id, f"/v/{clip_id}.mp4", "t")

    c._proxy_slot_released()

    assert len(c.gestartet) == 3
    assert c._proxy_active == 2


def test_die_reihenfolge_bleibt_erhalten():
    """FIFO: `popleft` — sonst wandert der erste Import ans Ende."""
    c = _Controller(max_active=1)
    for clip_id in (7, 8, 9):
        c._start_proxy_creation(clip_id, "/v/x.mp4", "t")

    c._proxy_slot_released()
    c._proxy_slot_released()

    assert c.gestartet == [7, 8, 9]


def test_nach_dem_fenster_teardown_rueckt_nichts_mehr_nach():
    """B-020: die Queue lädt sich über `finished` selbst nach."""
    c = _Controller(max_active=2, fenster_lebt=False)

    c._start_proxy_creation(1, "/v/1.mp4", "t")

    assert c.gestartet == []
    assert len(c._proxy_pending) == 0, "die Warteschlange wurde nicht geleert"


def test_ein_abbruch_stoppt_das_nachruecken():
    """B-802: der Abbruch darf die Queue nicht beschleunigen."""
    c = _Controller(max_active=2)
    for clip_id in range(5):
        c._start_proxy_creation(clip_id, "/v/x.mp4", "t")
    vorher = len(c.gestartet)

    c._proxy_queue_stopped = True
    c._proxy_slot_released()

    assert len(c.gestartet) == vorher


def test_ein_neuer_auftrag_hebt_die_abbruch_sperre_auf():
    """Sonst bliebe die Queue nach einem Abbruch dauerhaft taub."""
    c = _Controller(max_active=2)
    c._proxy_queue_stopped = True

    c._start_proxy_creation(1, "/v/1.mp4", "t")

    assert c._proxy_queue_stopped is False
    assert c.gestartet == [1]


def test_das_limit_entspricht_den_semaphor_slots():
    """Quellcode-Guard für den Wert selbst."""
    quelle = (REPO_ROOT / "ui" / "controllers" / "video_analysis.py").read_text(
        encoding="utf-8", errors="replace")

    assert "_PROXY_MAX_ACTIVE = 2" in quelle


def test_der_auftrag_geht_in_die_warteschlange_statt_direkt_zum_worker():
    """Quellcode-Guard: `_start_proxy_creation` darf keinen Worker direkt starten.

    Genau das war der Zustand vor B-656 — und genau das misst kein
    Verhaltenstest, wenn jemand den Aufruf wieder direkt einbaut.
    """
    quelle = (REPO_ROOT / "ui" / "controllers" / "video_analysis.py").read_text(
        encoding="utf-8", errors="replace")

    start = quelle.index("def _start_proxy_creation")
    ende = quelle.index("def _drain_proxy_queue")
    block = quelle[start:ende]

    assert "_proxy_pending.append(" in block
    assert "_drain_proxy_queue()" in block
    assert "_launch_proxy_worker(" not in block, (
        "_start_proxy_creation startet wieder direkt einen Worker"
    )


@pytest.mark.parametrize("marker", ["B-656", "B-802", "B-020"])
def test_die_stelle_behaelt_ihre_marker(marker):
    quelle = (REPO_ROOT / "ui" / "controllers" / "video_analysis.py").read_text(
        encoding="utf-8", errors="replace")

    assert marker in quelle
