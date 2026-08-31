"""B-936 — SigLIP fuellte `model_registry.last_used_at` nie.

AUD-11 traegt die Nutzung in ``ensure_loaded``/``load_ollama`` ein. Die
Video-Analyse ruft aber ``ModelManager.load_siglip()`` direkt
(`services/video_analysis_service.py:549` und `:1377`). Folge: die Spalte
"Zuletzt benutzt" zeigte fuer jedes Modell "Nie" und
``get_cleanup_candidates`` behandelte alles als "lange ungenutzt".
"""

import contextlib

import pytest

from services.model_manager import ModelManager


class _FakeManager:
    """Nur die Felder, die der Cache-Hit-Pfad von load_siglip anfasst."""

    def __init__(self):
        self._swap_lock = contextlib.nullcontext()
        self._current_model_id = "google/siglip-so400m-patch14-384"
        self._model_type = "siglip"
        self._model = object()
        self._extras = {"processor": object()}
        self.touched = []

    def _ensure_cuda_or_fallback(self, _grund):
        return None

    def _touch_last_used(self, model_id):
        self.touched.append(model_id)


def test_cache_hit_traegt_die_nutzung_ein():
    fake = _FakeManager()

    model, processor = ModelManager.load_siglip(fake, "google/siglip-so400m-patch14-384")

    assert model is fake._model
    assert processor is fake._extras["processor"]
    assert fake.touched == ["google/siglip-so400m-patch14-384"], (
        "ein bereits geladenes Modell wird trotzdem benutzt — sonst faellt "
        "last_used_at bei jedem weiteren Clip wieder hinten runter"
    )


def test_touch_last_used_ruft_die_registry():
    aufrufe = []

    class _FakeService:
        def touch_last_used(self, model_id):
            aufrufe.append(model_id)

    import services.model_lifecycle_service as mls
    alt = mls.get_model_lifecycle_service
    mls.get_model_lifecycle_service = lambda *a, **k: _FakeService()
    try:
        ModelManager._touch_last_used(
            ModelManager.__new__(ModelManager), "google/siglip-so400m-patch14-384")
    finally:
        mls.get_model_lifecycle_service = alt

    assert aufrufe == ["google/siglip-so400m-patch14-384"]


@pytest.mark.parametrize("fehler", [ImportError, RuntimeError, AttributeError])
def test_registry_fehler_sprengt_den_modell_load_nicht(fehler):
    import services.model_lifecycle_service as mls

    def _boom(*a, **k):
        raise fehler("Registry weg")

    alt = mls.get_model_lifecycle_service
    mls.get_model_lifecycle_service = _boom
    try:
        # Darf nicht werfen: das Laden des Modells ist wichtiger als die Statistik.
        ModelManager._touch_last_used(ModelManager.__new__(ModelManager), "irgendwas")
    finally:
        mls.get_model_lifecycle_service = alt


def test_frisch_geladen_traegt_die_nutzung_auch_ein():
    """Quelltext-Guard fuer den zweiten Rueckgabepfad.

    Der Frisch-Load-Pfad laesst sich ohne echtes SigLIP nicht durchlaufen
    (transformers, CUDA, fp16-NaN-Guard). Geprueft wird deshalb, dass der
    Aufruf zwischen der "geladen"-Logzeile und dem return steht.
    """
    import inspect

    src = inspect.getsource(ModelManager.load_siglip)
    nach_log = src.split("SigLIP '%s' geladen.", 1)[1]
    vor_return = nach_log.split("return self._model", 1)[0]
    assert "_touch_last_used(model_id)" in vor_return


# ── B-945: Drosselung ─────────────────────────────────────────────────────

def test_wiederholte_cache_hits_schreiben_nur_einmal(monkeypatch):
    """B-945: Der Cache-Hit-Pfad laeuft pro Clip.

    Eine Analyse mit 121 Clips schrieb 121-mal in die Registry, jedes Mal ueber
    eine eigene NullPool-Session auf derselben SQLite-Datei, auf die parallel
    die Analyse-Worker schreiben. Fuer eine tagesgenaue Spalte reicht ein
    Schreibvorgang pro Stunde und Modell.
    """
    aufrufe = []

    class _FakeService:
        def touch_last_used(self, model_id):
            aufrufe.append(model_id)

    import services.model_lifecycle_service as mls
    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda *a, **k: _FakeService())

    manager = ModelManager.__new__(ModelManager)
    # ModelManager ist ein Singleton — __new__ liefert die geteilte Instanz.
    # Ohne Reset traegt sie den Zeitstempel aus einem frueheren Test.
    manager._last_used_geschrieben = {}
    for _ in range(50):
        ModelManager._touch_last_used(manager, "google/siglip-so400m-patch14-384")

    assert len(aufrufe) == 1


def test_verschiedene_modelle_werden_getrennt_gezaehlt(monkeypatch):
    aufrufe = []

    class _FakeService:
        def touch_last_used(self, model_id):
            aufrufe.append(model_id)

    import services.model_lifecycle_service as mls
    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda *a, **k: _FakeService())

    manager = ModelManager.__new__(ModelManager)
    manager._last_used_geschrieben = {}
    ModelManager._touch_last_used(manager, "modell-a")
    ModelManager._touch_last_used(manager, "modell-b")
    ModelManager._touch_last_used(manager, "modell-a")

    assert aufrufe == ["modell-a", "modell-b"]


def test_abgelaufene_drosselung_schreibt_wieder(monkeypatch):
    aufrufe = []

    class _FakeService:
        def touch_last_used(self, model_id):
            aufrufe.append(model_id)

    import services.model_lifecycle_service as mls
    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda *a, **k: _FakeService())

    manager = ModelManager.__new__(ModelManager)
    manager._last_used_geschrieben = {}
    ModelManager._touch_last_used(manager, "modell-a")
    # Zeitstempel um mehr als eine Stunde zurueckdatieren
    manager._last_used_geschrieben["modell-a"] = (
        manager._last_used_geschrieben["modell-a"] - 3601.0)
    ModelManager._touch_last_used(manager, "modell-a")

    assert len(aufrufe) == 2
