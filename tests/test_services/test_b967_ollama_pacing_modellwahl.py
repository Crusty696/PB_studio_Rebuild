"""B-967 — das direkte EDL-Reasoning schickte einen leeren Modellnamen.

Aus ``logs/pb_studio.log`` (2026-08-31, zweimal reproduziert):

    OllamaPacingService: Querying model '' for direct EDL reasoning...
    OllamaClient: HTTP-Fehler 400: {"error":"model is required"}
    Ollama direct EDL reasoning failed: HTTP-Fehler 400: {"error":"model is required"}

Ursache: ``get_ollama_settings()`` liefert ``model`` mit dem Vorgabewert ``""``
(``services/settings_store.py:193``). Der Schlüssel existiert damit immer, und
der eigene Vorgabewert in ``cfg.get("model", "llama3.2")`` greift nie. Solange
im Einstellungsdialog kein Modell gewählt ist, ging ein leerer Name an Ollama.

``services/pacing_strategist.py:354`` löst denselben Bedarf über
``resolve_model_for_task(client, "pacing")``. Der direkte EDL-Pfad war der
einzige, der das nicht tat.

Das Fake-Session-Muster ist aus
``tests/test_services/test_brain_context_in_ask_ai_and_pacing.py`` übernommen —
so bleibt der Test ohne DB-Zugriff.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_die_einstellung_liefert_wirklich_einen_leeren_namen():
    """Beleg für die Ursache, nicht nur für das Symptom."""
    quelle = (REPO_ROOT / "services" / "settings_store.py").read_text(
        encoding="utf-8", errors="replace")

    assert '"model": self.get_nested("ollama", "model", default="")' in quelle


def test_der_vergleichspfad_macht_es_schon_richtig():
    """``pacing_strategist`` war die Vorlage — der Fix gleicht beide an."""
    quelle = (REPO_ROOT / "services" / "pacing_strategist.py").read_text(
        encoding="utf-8", errors="replace")

    assert 'resolve_model_for_task(client, "pacing")' in quelle


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def options(self, *a, **kw):
        return self

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Ersetzt die echte DB-Session — kein DB-Zugriff im Test."""

    def __init__(self, track, clips):
        self._track = track
        self._clips = clips

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query(self, model):
        from database import AudioTrack, VideoClip

        if model is AudioTrack:
            return _FakeQuery([self._track])
        if model is VideoClip:
            return _FakeQuery(self._clips)
        return _FakeQuery([])


class _Client:
    """Zeichnet auf, mit welchem Modell gefragt wurde."""

    def __init__(self):
        self.gefragt_mit: list[str] = []

    def is_available(self):
        return True

    def chat(self, **kwargs):
        self.gefragt_mit.append(kwargs.get("model"))
        return '{"edl": [{"start": 0.0, "end": 8.0, "video_id": 1, "scene_id": 101}]}'


def _dienst(monkeypatch, modell: str):
    """Ein Dienst mit Fake-DB und Fake-Client, ohne Konstruktor-Nebenwirkungen."""
    from services.pacing import ollama_pacing
    from services.pacing.ollama_pacing import OllamaPacingService

    track = SimpleNamespace(
        id=1, duration=600.0, bpm=142.0,
        structure_segments=[
            SimpleNamespace(label="DROP", start_time=10.0, end_time=40.0, energy=0.9),
        ],
    )
    clip = SimpleNamespace(
        id=1, file_path="C:/videos/a.mp4", duration=30.0,
        scenes=[
            SimpleNamespace(id=101, start_time=0.0, end_time=5.0,
                            ai_mood="energetic", ai_tags=["strobe"]),
        ],
    )
    monkeypatch.setattr(
        ollama_pacing, "Session", lambda _engine: _FakeSession(track, [clip])
    )

    svc = OllamaPacingService.__new__(OllamaPacingService)
    svc.enabled = True
    svc.url = "http://localhost:11434"
    svc.model = modell
    svc._client = _Client()
    return svc


def _edl(svc):
    return svc.generate_edl(audio_id=1, video_clip_ids=[1])


def test_ohne_gewaehltes_modell_fragt_der_dienst_den_router(monkeypatch):
    """Der Kern des Fixes."""
    import services.model_router as router

    monkeypatch.setattr(
        router, "resolve_model_for_task", lambda client, task: "gemma3:4b")
    svc = _dienst(monkeypatch, "")

    _edl(svc)

    assert svc._client.gefragt_mit == ["gemma3:4b"], (
        f"gefragt wurde mit {svc._client.gefragt_mit}"
    )


def test_der_router_wird_fuer_pacing_gefragt_nicht_fuer_chat(monkeypatch):
    """Pacing braucht ein Text-Reasoning-Modell, kein Vision-Modell."""
    import services.model_router as router

    aufgaben: list[str] = []

    def _merken(client, task):
        aufgaben.append(task)
        return "gemma3:4b"

    monkeypatch.setattr(router, "resolve_model_for_task", _merken)
    svc = _dienst(monkeypatch, "")

    _edl(svc)

    assert aufgaben == ["pacing"]


def test_ohne_verfuegbares_modell_wird_gar_nicht_gefragt(monkeypatch):
    """Kein leerer Name mehr an Ollama — lieber sauber aussteigen.

    Vorher lief genau hier der HTTP-400 auf.
    """
    import services.model_router as router

    monkeypatch.setattr(router, "resolve_model_for_task", lambda client, task: None)
    svc = _dienst(monkeypatch, "")

    ergebnis = _edl(svc)

    assert ergebnis is None
    assert svc._client.gefragt_mit == [], (
        "trotz fehlendem Modell wurde Ollama gefragt"
    )


def test_ein_gewaehltes_modell_wird_nicht_ueberschrieben(monkeypatch):
    """Die Nutzerwahl bleibt Vorrang — der Router springt nur bei Leere ein."""
    import services.model_router as router

    monkeypatch.setattr(
        router, "resolve_model_for_task",
        lambda client, task: pytest.fail("Router darf hier nicht gefragt werden"),
    )
    svc = _dienst(monkeypatch, "qwen3-vl:4b")

    _edl(svc)

    assert svc._client.gefragt_mit == ["qwen3-vl:4b"]


def test_auch_ein_nur_aus_leerzeichen_bestehender_name_zaehlt_als_leer(monkeypatch):
    """`" "` ist genauso unbrauchbar wie `""` — Ollama antwortet gleich."""
    import services.model_router as router

    monkeypatch.setattr(
        router, "resolve_model_for_task", lambda client, task: "gemma3:4b")
    svc = _dienst(monkeypatch, "   ")

    _edl(svc)

    assert svc._client.gefragt_mit == ["gemma3:4b"]
