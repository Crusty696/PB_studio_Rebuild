"""B-951 — das RL-Feedback landete in der Tabelle und wurde nie gelesen.

``record_rl_feedback`` schreibt einen ``AIPacingMemory``-Eintrag. Aus genau
dieser Tabelle zieht ``_get_ai_memory_bias`` den Bias fuer die Clip-Auswahl —
das Feedback war also am richtigen Ort. Es griff nur nie, weil
``overall_energy`` leer blieb und der Filter ``overall_energy.between(...)``
jeden NULL-Eintrag aussortiert.

In der Projekt-DB lagen am 2026-08-31 zwei solche Eintraege (positive und
negative), beide mit ``overall_energy = None``.

Haetten sie gegriffen, waere es schlimmer gewesen: der Eintrag traegt
``mood="negative"`` und ``cut_type="feedback_78_clips"`` — als Vorbild gelesen
haette ein Daumen runter den Lauf zum Muster gemacht.
"""

from __future__ import annotations

import pytest

from services.pacing_memory import RL_LABEL_PREFIX, _mittlere_energie


# ── Energie fuer den Filter ───────────────────────────────────────────────

def test_mittlere_energie_aus_der_kurve():
    assert _mittlere_energie([0.2, 0.4, 0.6]) == pytest.approx(0.4)


def test_unnormierte_kurve_wird_skaliert():
    """Die Kurve aus B-931 ist nicht normiert (max lag dort bei 0.42)."""
    wert = _mittlere_energie([2.0, 4.0, 6.0])

    assert 0.0 <= wert <= 1.0
    assert wert == pytest.approx(4.0 / 6.0)


@pytest.mark.parametrize("kurve", [None, [], [None, None], "kaputt"])
def test_unbrauchbare_kurve_liefert_none(kurve):
    assert _mittlere_energie(kurve) is None


def test_ergebnis_liegt_immer_im_filterbereich():
    """Der Bias-Filter vergleicht gegen 0..1 — alles andere faellt durch."""
    for kurve in ([0.0], [1.0], [0.5, 0.5], [10.0, 0.0]):
        wert = _mittlere_energie(kurve)
        assert wert is None or 0.0 <= wert <= 1.0


# ── Sentiment-Auswertung im Bias ──────────────────────────────────────────

class _Mem:
    def __init__(self, label=None, mood=None, bpm=130.0, energy=0.5,
                 cut_type=None, raft_motion=None, crossfade_duration=None):
        self.label = label
        self.mood = mood
        self.bpm = bpm
        self.overall_energy = energy
        self.cut_type = cut_type
        self.raft_motion = raft_motion
        self.crossfade_duration = crossfade_duration


def _bias_mit(memories, monkeypatch):
    """Ruft _get_ai_memory_bias mit vorgegebener Trefferliste."""
    import services.pacing_memory as pm

    class _Query:
        def filter(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return memories

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def query(self, *a, **k):
            return _Query()

    monkeypatch.setattr(pm, "Session", lambda *a, **k: _Session())
    return pm._get_ai_memory_bias(130.0, 0.5)


def test_negative_bewertung_unterdrueckt_den_bias(monkeypatch):
    """Was schlecht bewertet wurde, soll sich nicht wiederholen."""
    memories = [
        _Mem(label="gelernt", mood="drop", cut_type="hard", raft_motion=0.8),
        _Mem(label=f"{RL_LABEL_PREFIX}negative", mood="negative"),
    ]

    assert _bias_mit(memories, monkeypatch) is None


def test_rl_eintrag_wird_nie_als_vorbild_gelesen(monkeypatch):
    """Sonst kaeme mood='positive' als bevorzugte Stimmung zurueck."""
    memories = [_Mem(label=f"{RL_LABEL_PREFIX}positive", mood="positive",
                     cut_type="feedback_78_clips")]

    assert _bias_mit(memories, monkeypatch) is None


def test_positive_bewertung_laesst_echte_vorbilder_stehen(monkeypatch):
    """Ein Daumen hoch darf gelernte Regeln nicht verdraengen."""
    memories = [
        _Mem(label="gelernt", mood="drop", cut_type="hard", raft_motion=0.8),
        _Mem(label=f"{RL_LABEL_PREFIX}positive", mood="positive"),
    ]

    bias = _bias_mit(memories, monkeypatch)

    assert bias is not None
    assert bias["mood"] == "drop", "die echte Lernregel muss gewinnen"
    assert bias["preferred_motion"] == 0.8


def test_ohne_rl_eintraege_bleibt_alles_wie_vorher(monkeypatch):
    memories = [_Mem(label="gelernt", mood="buildup", raft_motion=0.3)]

    bias = _bias_mit(memories, monkeypatch)

    assert bias is not None
    assert bias["mood"] == "buildup"
