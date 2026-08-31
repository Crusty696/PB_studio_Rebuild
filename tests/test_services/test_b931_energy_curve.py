"""B-931: Die V2-Audio-Pipeline muss eine Energiekurve liefern.

Bis 2026-08-31 schrieb sie ausschliesslich der alte AnalysisWorker. Seit
``audio.v2_default`` der Standard ist, blieb ``audio_tracks.energy_curve``
NULL — obwohl Stems-Workspace, Audio-Kachel und Story-Map sie erwarten und die
Analyse sich als "fertig" meldet.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.ai_audio_service import _sekundenkurve_aus_baendern


def _baender(n: int, wert: float = 0.5):
    arr = np.full(n, wert, dtype=np.float32)
    return arr, arr.copy(), arr.copy()


def test_ein_wert_je_sekunde():
    """Kernvertrag: die Kurvenlaenge entspricht der Dauer in Sekunden."""
    low, mid, high = _baender(4000)
    kurve = _sekundenkurve_aus_baendern(low, mid, high, duration=100.0)
    assert kurve is not None
    assert len(kurve) == 100


def test_dynamik_bleibt_erhalten():
    """Eine ansteigende Energie muss sich in der Kurve wiederfinden."""
    n = 1000
    rampe = np.linspace(0.0, 1.0, n, dtype=np.float32)
    kurve = _sekundenkurve_aus_baendern(rampe, rampe.copy(), rampe.copy(), duration=10.0)
    assert kurve[0] < kurve[-1], "Anstieg muss sichtbar bleiben"
    assert max(kurve) > min(kurve)


def test_mittelwert_der_drei_baender():
    """Die Kurve mittelt die drei Baender, sie summiert sie nicht."""
    n = 300
    low = np.full(n, 0.3, dtype=np.float32)
    mid = np.full(n, 0.6, dtype=np.float32)
    high = np.full(n, 0.9, dtype=np.float32)
    kurve = _sekundenkurve_aus_baendern(low, mid, high, duration=3.0)
    assert kurve[0] == pytest.approx(0.6, abs=1e-3)


def test_weniger_frames_als_sekunden_bleibt_nutzbar():
    """Sehr kurze oder grob gerasterte Eingaben duerfen nicht abstuerzen."""
    low, mid, high = _baender(3)
    kurve = _sekundenkurve_aus_baendern(low, mid, high, duration=10.0)
    assert kurve is not None and len(kurve) == 3


@pytest.mark.parametrize("leer", [np.zeros(0, dtype=np.float32), None])
def test_ohne_daten_kommt_none(leer):
    """Ohne verwertbare Baender wird nichts geschrieben — die Anzeige
    "nicht berechnet" bleibt dann ehrlich."""
    if leer is None:
        assert _sekundenkurve_aus_baendern(None, None, None, duration=10.0) is None
    else:
        assert _sekundenkurve_aus_baendern(leer, leer, leer, duration=10.0) is None


def test_ohne_dauer_kommt_none():
    low, mid, high = _baender(100)
    assert _sekundenkurve_aus_baendern(low, mid, high, duration=0.0) is None
