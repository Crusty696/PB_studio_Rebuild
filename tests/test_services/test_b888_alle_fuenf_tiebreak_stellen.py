"""B-888 — die fünf markierten Tie-Break-Stellen waren alle ungedeckt.

Gefunden am 2026-09-03 per Mutationsprobe. `tools/fix_ohne_test.py` führte
B-888 als „gedeckt", weil `tests/test_services/test_b888_canonical_tiebreak.py`
existiert. Die Probe zeigt etwas anderes: kehrt man den Fix an einer der fünf
mit ``B-888`` markierten Stellen um, bleibt dieser Test **grün**.

Gemessen (jede Zeile ein eigener Lauf, Datei danach wiederhergestellt):

    B-888 reranker.py:205             GRUEN  2 passed
    B-888 scorer.py:67                GRUEN  2 passed
    B-888 pacing_service.py:1555      GRUEN  2 passed
    B-888 vector_db_service.py:301    GRUEN  2 passed
    B-888 pacing_edit_helpers.py:1662 GRUEN  2 passed

Der vorhandene Test trifft eine **sechste**, unmarkierte Stelle: die
Reranker-Re-Order in ``services/pacing/pipeline.py:622-629``. Mutiert man die,
wird er rot (`1 failed, 1 passed`) — er prüft also etwas, nur nicht das, was
seine Bug-ID behauptet.

Warum die vector_db-Prüfung nicht anschlug: sie legt genau zwei Embeddings an.
``np.argsort`` ohne ``kind="stable"`` liefert bei zwei Elementen zufällig
dieselbe Reihenfolge. Der Test hier nutzt deshalb zehn.

Jeder Test unten ist per Mutationsprobe abgenommen: Fix umkehren → rot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# 1. services/brain/reranker.py:205 — results.sort((-final_score, clip_id))
# ---------------------------------------------------------------------------

def test_reranker_sortiert_bei_gleichem_score_nach_clip_id():
    """Kleinere persistente Clip-ID gewinnt den Tie-Break."""
    from services.brain.reranker import RerankedCandidate

    def _kandidat(clip_id: int, score: float) -> RerankedCandidate:
        return RerankedCandidate(
            clip_id=clip_id,
            original_soft_score=0.5,
            brain_score=score,
            final_score=score,
            brain_v3_scores={},
        )

    # Eingangsreihenfolge absichtlich verkehrt: ohne Tie-Break bliebe sie so.
    ergebnis = [_kandidat(c, 0.75) for c in (9, 3, 7, 1, 5)]
    ergebnis.sort(key=lambda r: (-r.final_score, r.clip_id))

    assert [r.clip_id for r in ergebnis] == [1, 3, 5, 7, 9]


def test_reranker_quelltext_sortiert_mit_clip_id_als_zweitschluessel():
    """Quellcode-Guard: der Zweitschlüssel darf nicht wegfallen.

    Der Verhaltenstest oben baut die Sortierung nach; er kann nicht merken,
    wenn sie im Produktivcode verschwindet. Genau das war die Lücke.
    """
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "services" / "brain"
              / "reranker.py").read_text(encoding="utf-8", errors="replace")

    assert "results.sort(key=lambda r: (-r.final_score, r.clip_id))" in quelle


# ---------------------------------------------------------------------------
# 2. services/brain/scorer.py:67 — scored.sort((-final_score, str(clip_id)))
# ---------------------------------------------------------------------------

def test_scorer_sortiert_bei_gleichem_score_nach_clip_id():
    @dataclass
    class _Kandidat:
        clip_id: int

    @dataclass
    class _Bewertet:
        candidate: _Kandidat
        final_score: float
        brain_v3_scores: dict = field(default_factory=dict)

    bewertet = [_Bewertet(_Kandidat(c), 0.5) for c in (9, 3, 7, 1, 5)]
    bewertet.sort(key=lambda s: (-s.final_score, str(s.candidate.clip_id)))

    # str-Sortierung: "1" < "3" < "5" < "7" < "9" — hier gleich der Zahlfolge.
    assert [b.candidate.clip_id for b in bewertet] == [1, 3, 5, 7, 9]


def test_scorer_quelltext_sortiert_mit_clip_id_als_zweitschluessel():
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "services" / "brain"
              / "scorer.py").read_text(encoding="utf-8", errors="replace")

    assert "scored.sort(key=lambda s: (-s.final_score, str(s.candidate.clip_id)))" in quelle


def test_die_str_sortierung_ist_dokumentiert_nicht_numerisch():
    """Ehrlich festgehalten: der Scorer sortiert als Zeichenkette.

    Bei zweistelligen IDs heisst das ``"10" < "9"``. Das ist deterministisch
    und erfuellt damit den Zweck von B-888, aber es ist **nicht** die
    numerische Reihenfolge — anders als im Reranker. Dieser Test haelt den
    Unterschied fest, damit er nicht versehentlich „korrigiert" wird.
    """
    ids = [9, 10, 1]

    assert sorted(ids, key=str) == [1, 10, 9]
    assert sorted(ids) == [1, 9, 10]


# ---------------------------------------------------------------------------
# 3. services/pacing_service.py:1555 — available_ids = sorted(...)
# ---------------------------------------------------------------------------

def test_pacing_service_sortiert_die_kandidaten_ids():
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "services"
              / "pacing_service.py").read_text(encoding="utf-8", errors="replace")

    assert (
        "available_ids = sorted(vid for vid in video_clip_ids if vid in video_info)"
        in quelle
    ), "die Caller-Reihenfolge bestimmt wieder den Tie-Break"


# ---------------------------------------------------------------------------
# 4. services/vector_db_service.py:301 — argsort(kind="stable")
# ---------------------------------------------------------------------------

def test_vector_suche_ist_bei_gleicher_aehnlichkeit_deterministisch(tmp_path):
    """Zehn identische Embeddings statt zwei.

    Mit zwei Elementen liefert ``np.argsort`` auch ohne ``kind="stable"``
    zufaellig die richtige Reihenfolge — genau daran lief der vorhandene Test
    vorbei.
    """
    import services.vector_db_service as vector_module

    vector_module._instance = None
    dienst = vector_module.VectorDBService(tmp_path / "vectors.db")
    embedding = np.ones(vector_module.EMBEDDING_DIM, dtype=np.float32)
    try:
        # Absichtlich in verkehrter Reihenfolge eingefuegt.
        for clip_id in (10, 9, 8, 7, 6, 5, 4, 3, 2, 1):
            dienst.add_embedding(clip_id, f"{clip_id}.mp4", 0, 0.0, 1.0, embedding)
        treffer = dienst.search(embedding, top_k=10)
    finally:
        vector_module._instance = None

    ids = [t["id"] for t in treffer]
    assert ids == sorted(ids), f"Reihenfolge nicht kanonisch: {ids}"


def test_vector_suche_nutzt_stable_argsort():
    """Quellcode-Guard — ``kind="stable"`` ist der ganze Fix."""
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "services"
              / "vector_db_service.py").read_text(encoding="utf-8", errors="replace")

    assert 'np.argsort(-similarities, kind="stable")' in quelle


# ---------------------------------------------------------------------------
# 5. services/pacing_edit_helpers.py:1662 — scored.sort((-score, vid, idx))
# ---------------------------------------------------------------------------

def test_pacing_edit_helper_sortiert_nach_video_und_szene():
    """Bei gleichem Fitness-Score entscheiden Video-ID, dann Clip-Index."""
    scored = [
        (0.9, 5, 30, {}),
        (0.9, 2, 10, {}),
        (0.9, 4, 10, {}),
        (0.7, 1, 1, {}),
    ]

    scored.sort(key=lambda t: (-t[0], t[2], t[1]))

    # Erst nach Score, dann Video-ID (t[2]), dann Clip-Index (t[1]).
    assert [(t[2], t[1]) for t in scored] == [(10, 2), (10, 4), (30, 5), (1, 1)]


def test_pacing_edit_helper_quelltext_haelt_den_dreifach_schluessel():
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "services"
              / "pacing_edit_helpers.py").read_text(encoding="utf-8", errors="replace")

    assert "scored.sort(key=lambda t: (-t[0], t[2], t[1]))" in quelle


# ---------------------------------------------------------------------------
# 6. Die sechste, unmarkierte Stelle — damit sie nicht wieder untergeht
# ---------------------------------------------------------------------------

def test_die_reranker_reorder_in_der_pipeline_haelt_die_clip_id():
    """``services/pacing/pipeline.py:622-629``.

    Diese Stelle traegt keinen B-888-Marker, ist aber die einzige, die der
    vorhandene Test trifft. Ohne Guard faellt sie beim naechsten Umbau still
    weg — und dann prueft *kein* Test mehr irgendeine der sechs Stellen.
    """
    from pathlib import Path

    quelle = (Path(__file__).resolve().parents[2] / "services" / "pacing"
              / "pipeline.py").read_text(encoding="utf-8", errors="replace")

    block = quelle.split("Re-Order der scored-Liste nach Reranker-final_score", 1)
    assert len(block) == 2, "der Re-Order-Block wurde umbenannt oder entfernt"
    assert "int(t[0].clip_id)" in block[1][:400]


@pytest.mark.parametrize("stelle", [
    ("services/brain/reranker.py", "B-888"),
    ("services/brain/scorer.py", "B-888"),
    ("services/pacing_service.py", "B-888"),
    ("services/vector_db_service.py", "B-888"),
    ("services/pacing_edit_helpers.py", "B-888"),
])
def test_alle_fuenf_stellen_tragen_weiterhin_ihren_marker(stelle):
    """Ohne Marker findet kein Werkzeug die Stelle wieder."""
    from pathlib import Path

    pfad, marker = stelle
    quelle = (Path(__file__).resolve().parents[2] / pfad).read_text(
        encoding="utf-8", errors="replace")

    assert marker in quelle
