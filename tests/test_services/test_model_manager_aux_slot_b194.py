"""B-194 regression tests — RAFT lebt im aux-Slot, evicted SigLIP nicht.

Vor dem Fix rief ``ModelManager.load_raft()`` ``self.unload()`` (H17-Fix).
Das schob das main-Modell (SigLIP, im Batch-Captioning vorgeladen) auf
CPU. workers/video.py hielt aber noch eine Reference auf das jetzt-
CPU-bewohnte SigLIP-Objekt — Inputs landeten auf CUDA, Inferenz feuerte
einen Mixed-Device-RuntimeError, der von der OOM-Recovery faelschlich
als "OOM bei SigLIP Batch" geloggt wurde. Resultat: 0/N Embeddings fuer
jedes der 218 Videos.

Der Fix trennt main-Slot (SigLIP/transformers) und aux-Slot (RAFT) im
ModelManager. Diese Tests verhindern, dass jemand load_raft() wieder
auf den main-Slot setzt oder die Eviction-Logik wieder zusammenfuehrt.

Die Tests arbeiten mit Mocks, brauchen also keine GPU.
"""

from __future__ import annotations

import inspect
import threading

from services import model_manager as mm_mod
from services.model_manager import ModelManager


def _reset_singleton() -> None:
    """Cold-start die Singleton-Instanz — sonst kontaminieren vorherige
    Tests die Aux/Main-Slots.
    """
    with ModelManager._lock:
        ModelManager._instance = None


# ---------------------------------------------------------------------------
# 1. Architektur-Riegel: Aux-Slots existieren und sind disjunkt
# ---------------------------------------------------------------------------


def test_aux_slot_attributes_exist_after_new() -> None:
    """Aux-Slot-Felder muessen direkt nach ``__new__`` da sein, parallel
    zum Main-Slot. Sonst koennen Threads in einer Halb-State-Lage
    landen (siehe B-122-Pattern)."""
    _reset_singleton()
    inst = ModelManager.__new__(ModelManager)
    assert hasattr(inst, "_aux_model"), "B-194: _aux_model fehlt"
    assert hasattr(inst, "_aux_model_id"), "B-194: _aux_model_id fehlt"
    assert hasattr(inst, "_aux_model_type"), "B-194: _aux_model_type fehlt"
    assert hasattr(inst, "_aux_extras"), "B-194: _aux_extras fehlt"
    # Disjunkt zum main-Slot:
    assert inst._model is None
    assert inst._aux_model is None


def test_unload_aux_method_exists() -> None:
    """``_unload_aux`` und ``unload_raft`` muessen Public/Protected-API sein."""
    assert hasattr(ModelManager, "_unload_aux")
    assert hasattr(ModelManager, "unload_raft")
    assert callable(ModelManager.unload_raft)


# ---------------------------------------------------------------------------
# 2. Source-Inspection: load_raft() darf self.unload() NICHT mehr rufen
# ---------------------------------------------------------------------------


def test_load_raft_does_not_call_self_unload() -> None:
    """Architektur-Riegel: ``load_raft()`` darf nicht das main-Modell
    entladen. Der Source-Code muss frei von Code-Zeilen ``self.unload()``
    sein. Erlaubt sind ``self._unload_aux()`` und Erwaehnungen im
    Docstring.
    """
    src = inspect.getsource(ModelManager.load_raft)
    # Filtere Zeilen, die nur Code sind — Docstring (zwischen """ ... """)
    # ueberspringen. Bonus: Inline-Kommentare bleiben drin, das ist OK,
    # weil ein Kommentar mit ``self.unload()`` eh kein Funktionsaufruf
    # ist.
    in_docstring = False
    code_lines = []
    for line in src.splitlines():
        if '"""' in line:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Inline-Kommentar entfernen
        if "#" in line:
            line = line.split("#", 1)[0]
        code_lines.append(line)
    code = "\n".join(code_lines)
    assert "self.unload(" not in code, (
        "B-194: load_raft() ruft self.unload() — das wuerde das main-Modell "
        "(z.B. SigLIP im Batch-Captioning) auf CPU schieben und die in "
        "workers/video.py gehaltenen Referenzen invalidieren."
    )


# ---------------------------------------------------------------------------
# 3. Verhaltens-Test mit Mocks: aux-Load schiebt main nicht raus
# ---------------------------------------------------------------------------


class _FakeModel:
    """Minimal-Modell fuer Lifecycle-Tests. ``cpu()`` markiert den
    Device-Wechsel, damit wir verifizieren koennen, ob jemand das
    Modell ungefragt verschoben hat."""

    def __init__(self, label: str):
        self.label = label
        self.device = "cuda"
        self.cpu_called = False

    def cpu(self):
        self.cpu_called = True
        self.device = "cpu"
        return self


def test_unload_aux_only_clears_aux_slot() -> None:
    """Setze main + aux manuell, rufe ``_unload_aux`` — nur aux darf weg
    sein, main muss intakt bleiben (insbesondere KEIN ``cpu()``-Call).
    """
    _reset_singleton()
    mm = ModelManager()
    main_obj = _FakeModel("siglip")
    aux_obj = _FakeModel("raft")
    mm._model = main_obj
    mm._current_model_id = "google/siglip-so400m-patch14-384"
    mm._model_type = "siglip"
    mm._aux_model = aux_obj
    mm._aux_model_id = "raft_small"
    mm._aux_model_type = "raft"

    try:
        mm._unload_aux()
        assert mm._aux_model is None, "B-194: aux-Slot wurde nicht geleert"
        assert mm._aux_model_type is None
        # Wichtigster Test:
        assert mm._model is main_obj, "B-194: main wurde unerwartet geleert"
        assert main_obj.cpu_called is False, (
            "B-194: main-Modell wurde auf CPU geschoben — genau das "
            "verursachte den Mixed-Device-Bug, der als OOM mis-diagnostiziert wurde."
        )
        # aux-Modell wurde wie erwartet auf CPU geschoben:
        assert aux_obj.cpu_called is True
    finally:
        mm._model = None
        mm._current_model_id = None
        mm._model_type = None


def test_unload_clears_both_slots() -> None:
    """Vollstaendiges ``unload()`` raeumt main UND aux."""
    _reset_singleton()
    mm = ModelManager()
    main_obj = _FakeModel("siglip")
    aux_obj = _FakeModel("raft")
    mm._model = main_obj
    mm._current_model_id = "google/siglip-so400m-patch14-384"
    mm._model_type = "siglip"
    mm._aux_model = aux_obj
    mm._aux_model_id = "raft_small"
    mm._aux_model_type = "raft"

    mm.unload()

    assert mm._model is None
    assert mm._aux_model is None
    assert mm._current_model_id is None
    assert mm._aux_model_type is None
    assert main_obj.cpu_called is True
    assert aux_obj.cpu_called is True


def test_unload_raft_is_idempotent_when_aux_empty() -> None:
    """``unload_raft()`` darf nicht crashen wenn der aux-Slot leer ist
    oder ein anderes (hypothetisches) aux-Modell haelt.
    """
    _reset_singleton()
    mm = ModelManager()
    # Leerer aux-Slot
    mm.unload_raft()
    # Aux mit anderem Typ — wird nicht angefasst
    other = _FakeModel("other_aux")
    mm._aux_model = other
    mm._aux_model_id = "other"
    mm._aux_model_type = "other"
    try:
        mm.unload_raft()
        assert mm._aux_model is other, (
            "B-194: unload_raft() darf nur RAFT entladen, nicht andere aux-Modelle."
        )
    finally:
        mm._aux_model = None
        mm._aux_model_id = None
        mm._aux_model_type = None


# ---------------------------------------------------------------------------
# 4. Source-Inspection: misleading "OOM"-Log unterscheidet jetzt
# ---------------------------------------------------------------------------


def test_video_analysis_oom_log_distinguishes_runtimeerror_from_oom() -> None:
    """B-194: Der Recovery-Pfad in ``services.video_analysis_service`` darf
    RuntimeErrors nicht mehr blind als "OOM" loggen. Der Source muss eine
    Unterscheidung anhand von ``"out of memory"`` im Fehlertext enthalten.
    """
    from services import video_analysis_service as vas

    src = inspect.getsource(vas)
    # Marker fuer die Unterscheidung
    assert "out of memory" in src.lower(), (
        "B-194: Recovery-Logger muss zwischen OOM und anderen RuntimeErrors "
        "unterscheiden (siehe Mis-Diagnose im Cycle-21-Conda-Migrations-Lauf)."
    )
    # Negative-Marker: der pauschale "OOM bei SigLIP Batch" ohne Discriminator
    # darf nicht mehr unkonditional gerufen werden.
    bad_pattern = 'logger.warning("OOM bei SigLIP Batch'
    occurrences = src.count(bad_pattern)
    # 1x ist OK (innerhalb des if _is_oom Zweigs); >1 oder ohne if-Wrapper
    # waere die alte Naivitaet.
    assert occurrences <= 1, (
        f"B-194: 'OOM bei SigLIP Batch'-Log {occurrences}x gefunden — "
        "darf nur einmal als bedingter Logger im _is_oom-Zweig vorkommen."
    )
