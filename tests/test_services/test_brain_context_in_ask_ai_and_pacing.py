"""B-738-Follow-up: Brain-Gedaechtnis in den drei prompt-bauenden Pfaden.

``services/knowledge_loader.build_brain_context()`` existierte, wurde aber nur
von ``local_agent_service._build_system_prompt`` genutzt. Drei Pfade bauen
ihren Prompt selbst und hatten deshalb KEINEN Zugriff auf die gespeicherten
Erkenntnisse:

- ``services/actions/ai_actions.ask_ai``
- ``services/pacing_strategist.PacingStrategist.generate_pacing_plan``
- ``services/pacing/ollama_pacing.OllamaPacingService.generate_edl``

Der Vision-/Caption-Pfad ist bewusst NICHT angeschlossen — Begruendung im
Test ``test_vision_path_stays_without_brain_context`` unten.

Kein Ollama, keine GPU, keine DB: Client und DB-Session sind Attrappen.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# Gleiche Form wie ``brain_recall`` sie liefert (vgl.
# tests/test_services/test_brain_lernkreis_2026_07_27.py).
_FAKE_RECALL = {
    "status": "ok",
    "action": "brain_recall",
    "result_count": 2,
    "results": [
        {
            "source": "brain_note",
            "score": 1.0,
            "title": "Psytrance-Drops",
            "body": "Im Drop funktionieren harte Schnitte auf jedem 4. Beat.",
        },
        {
            "source": "mem_learned_pattern",
            "score": 0.9,
            "pattern_type": "role_in_section",
            "context_fingerprint": "section=drop",
            "target_ref": "role=action",
            "accepts": 12,
            "rejects": 1,
            "confidence": 0.92,
        },
    ],
    "message": "x",
}

_EMPTY_RECALL = {"status": "ok", "results": [], "result_count": 0}


@pytest.fixture
def brain(monkeypatch):
    """Patcht ``brain_recall`` — der echte ``build_brain_context`` laeuft."""
    import services.actions.brain_actions as brain_actions

    def _use(payload):
        monkeypatch.setattr(brain_actions, "brain_recall", lambda **kw: payload)

    return _use


# ---------------------------------------------------------------------------
# 1. ask_ai
# ---------------------------------------------------------------------------

class _FakeOllamaClient:
    def __init__(self):
        self.calls: list[dict] = []

    def is_available(self):
        return True

    def get_best_available_model(self):
        return "phi3:mini"

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return "Antwort des Modells"


@pytest.fixture
def fake_ollama(monkeypatch):
    import services.actions.ai_actions as ai_actions
    import services.model_router as model_router

    client = _FakeOllamaClient()
    monkeypatch.setattr(ai_actions, "_get_ollama_client", lambda: client)
    monkeypatch.setattr(
        model_router, "resolve_model_for_task", lambda c, task: "phi3:mini"
    )
    monkeypatch.setattr(
        model_router, "emit_task_status", lambda *a, **kw: None
    )
    return client


def test_ask_ai_prompt_contains_brain_memory(brain, fake_ollama):
    """Kernbeweis: ``ask_ai`` speist das Gedaechtnis in den System-Prompt."""
    from services.actions.ai_actions import ask_ai

    brain(_FAKE_RECALL)
    result = ask_ai(question="wie schneide ich drops?")

    assert result["status"] == "ok"
    assert fake_ollama.calls, "Der LLM-Call kam gar nicht zustande"
    system_prompt = fake_ollama.calls[0]["system_prompt"]
    assert "BRAIN-GEDAECHTNIS" in system_prompt
    assert "Psytrance-Drops" in system_prompt
    assert "role_in_section" in system_prompt
    # Der eigentliche Prompt-Zweck darf nicht verdraengt werden.
    assert "KI-Assistent von PB Studio" in system_prompt


def test_ask_ai_prompt_unchanged_when_nothing_learned(brain, fake_ollama):
    """Gegenprobe: ohne gespeicherte Erkenntnisse bleibt der Prompt exakt
    wie vorher — kein Platzhalter, keine Leerzeilen-Kosmetik."""
    from services.actions.ai_actions import ask_ai

    brain(_EMPTY_RECALL)
    ask_ai(question="wie schneide ich drops?")

    system_prompt = fake_ollama.calls[0]["system_prompt"]
    assert "BRAIN" not in system_prompt
    assert system_prompt == (
        "Du bist der KI-Assistent von PB Studio, einer professionellen "
        "Audio/Video-Produktionssoftware fuer DJs und Video-Editoren. "
        "Antworte praezise, hilfreich und auf Deutsch."
    )


def test_ask_ai_survives_a_broken_brain(monkeypatch, fake_ollama):
    """Ein kaputtes Gedaechtnis darf die Aktion nicht mitreissen."""
    import services.actions.brain_actions as brain_actions
    from services.actions.ai_actions import ask_ai

    def _boom(**kw):
        raise RuntimeError("mem_decision fehlt")

    monkeypatch.setattr(brain_actions, "brain_recall", _boom)
    assert ask_ai(question="egal")["status"] == "ok"


# ---------------------------------------------------------------------------
# 2. PacingStrategist
# ---------------------------------------------------------------------------

_VALID_PLAN_JSON = (
    '{"sections": [{"type": "DROP", "start": 0.0, "end": 10.0, '
    '"cut_rate_beats": 2}], "global_min_duration": 3.0, '
    '"variety_priority": 0.7}'
)


def _run_strategist(monkeypatch) -> str:
    from services.pacing_strategist import PacingStrategist

    captured: dict[str, str] = {}
    ps = PacingStrategist()

    def _generate(user_text: str, max_tokens: int = 1024) -> str:
        captured["prompt"] = user_text
        return _VALID_PLAN_JSON

    monkeypatch.setattr(ps, "_generate", _generate)
    plan = ps.generate_pacing_plan(
        sections=[{"type": "DROP", "start": 0.0, "end": 10.0, "avg_energy": 0.9}],
        bpm=142.0,
        total_duration=600.0,
        clip_count=12,
        user_preferences="mehr Impact bei Drops",
    )
    assert plan.degraded is False, "Vorbedingung: Plan wurde erzeugt"
    return captured["prompt"]


def test_pacing_strategist_prompt_contains_brain_memory(brain, monkeypatch):
    """Kernbeweis: der Pacing-Prompt sieht die gelernten Muster."""
    brain(_FAKE_RECALL)
    prompt = _run_strategist(monkeypatch)

    assert "BRAIN-GEDAECHTNIS" in prompt
    assert "Psytrance-Drops" in prompt
    # Prompt-Ziel bleibt die letzte Anweisung.
    assert prompt.rstrip().endswith("Erstelle einen JSON Pacing-Plan.")
    assert "DROP" in prompt and "142.0" in prompt


def test_pacing_strategist_prompt_unchanged_when_nothing_learned(brain, monkeypatch):
    """Gegenprobe: leeres Gedaechtnis -> Prompt ohne Brain-Block."""
    brain(_EMPTY_RECALL)
    prompt = _run_strategist(monkeypatch)
    assert "BRAIN" not in prompt


def test_pacing_brain_block_stays_within_its_tight_budget(brain, monkeypatch):
    """Der Pacing-Pfad hat ein enges Budget: max. 600 Zeichen Gedaechtnis."""
    brain({
        "status": "ok",
        "results": [dict(_FAKE_RECALL["results"][0]) for _ in range(200)],
    })
    prompt = _run_strategist(monkeypatch)
    start = prompt.index("## BRAIN-GEDAECHTNIS")
    end = prompt.index("Erstelle einen JSON Pacing-Plan.")
    assert 0 < len(prompt[start:end].strip()) <= 600


# ---------------------------------------------------------------------------
# 3. OllamaPacingService (direkter EDL-Pfad)
# ---------------------------------------------------------------------------

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


class _FakeEdlClient:
    def __init__(self):
        self.calls: list[dict] = []

    def is_available(self):
        return True

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return '{"edl": [{"start": 0.0, "end": 8.0, "video_id": 1, "scene_id": 101}]}'


def _run_edl(monkeypatch) -> str:
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
    svc.model = "gemma3:4b"
    client = _FakeEdlClient()
    svc._client = client

    edl = svc.generate_edl(audio_id=1, video_clip_ids=[1],
                           user_preferences="harte Schnitte")
    assert edl, "Vorbedingung: EDL wurde erzeugt"
    return client.calls[0]["user_message"]


def test_edl_prompt_contains_brain_memory(brain, monkeypatch):
    """Kernbeweis: auch der direkte EDL-Pfad sieht die gelernten Muster."""
    brain(_FAKE_RECALL)
    user_message = _run_edl(monkeypatch)

    assert "BRAIN-GEDAECHTNIS" in user_message
    assert "Psytrance-Drops" in user_message
    # Metadaten-Payload und Schlussanweisung bleiben erhalten.
    assert '"videos"' in user_message
    assert user_message.rstrip().endswith(
        "Erstelle die EDL für die gesamte Mix-Dauer."
    )


def test_edl_prompt_unchanged_when_nothing_learned(brain, monkeypatch):
    """Gegenprobe: leeres Gedaechtnis -> Prompt exakt wie vorher."""
    brain(_EMPTY_RECALL)
    user_message = _run_edl(monkeypatch)
    assert "BRAIN" not in user_message


# ---------------------------------------------------------------------------
# 4. Vision-Pfade — D-083 read-only Brain-Context
# ---------------------------------------------------------------------------

def test_vision_paths_use_read_only_brain_prompt():
    """D-083: beide Vision-Einstiege nutzen Gateway; Learn bleibt verboten."""
    from pathlib import Path

    for path in (
        "services/vision_analysis_service_moondream.py",
        "services/video_analysis_service.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "build_vision_prompt" in src
        assert "brain_learn_note" not in src
