"""Der Lernkreis war an drei Stellen unterbrochen (B-732, B-737, B-738).

B-732 — ``BrainV3Service.feedback()`` nahm nur ``rating`` + ``CutContext``
        entgegen. Der FeedbackLogger verteilt alpha/beta seit Commit 0504b2d
        gewichtet nach Achsen-Beitrag, sah ueber den Service aber nie
        Beitraege und landete im Uniform-Fallback. Uniform kann die
        Rangfolge des Scorers mathematisch nicht aendern.
B-737 — Ereignisse loesten die Pattern-Aggregation erst ab 20 Stueck aus,
        und ``notify_run_end()`` hatte im Produktivcode keinen Aufrufer.
        Zusaetzlich stiess Brain-Feedback das Muster-Lernen gar nicht an.
B-738 — Nur der tool-faehige Orchestrator-Pfad erreichte die Brain-Daten.
        Modelle ohne Tool-Support (phi3, gemma) sahen sie nie.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from services.brain.brain_v3_service import BrainV3Service
from services.brain.cold_start import BRIDGE_AXES
from services.brain.context_resolver import CutContext
from services.brain.schemas.brain_v3_schemas import FeedbackRequest
from services.brain.storage.brain_store import BrainStore
from services.brain.weight_store import WeightStore


@pytest.fixture
def service(tmp_path: Path):
    """BrainV3Service auf temporaeren DBs, ohne Muster-Lern-Seiteneffekt."""
    store = BrainStore(
        weights_path=tmp_path / "weights.db",
        patterns_path=tmp_path / "patterns.db",
    )
    weights = WeightStore(store.weights_path)
    svc = BrainV3Service(
        brain_store=store,
        weight_store=weights,
        pattern_notifier=lambda: None,
    )
    yield svc
    weights.close()


def _level0_counts(db_path: Path) -> dict[str, tuple[float, float]]:
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        rows = conn.execute(
            "SELECT axis, positive_count, negative_count FROM axis_weights "
            "WHERE context_level = 0"
        ).fetchall()
    return {r[0]: (float(r[1]), float(r[2])) for r in rows}


# ---------------------------------------------------------------------------
# B-732
# ---------------------------------------------------------------------------

def test_service_feedback_produces_different_axis_values(service):
    """Beweis: Feedback UEBER DEN SERVICE ist achsen-differenziert.

    Der bisherige Beleg (test_brain_v3_credit_assignment.py) galt nur fuer
    den direkten FeedbackLogger-Aufruf.
    """
    contributions = {
        "motion_match_weight": 0.9,
        "brightness_match_weight": 0.45,
        "semantic_match_weight": 0.09,
    }
    resp = service.feedback(
        FeedbackRequest(cut_id=1, rating="perfect"),
        context=CutContext(audio_section_type="drop"),
        axis_contributions=contributions,
    )

    assert resp.credit_mode == "weighted"
    assert resp.n_axes_credited == 3

    counts = _level0_counts(service._brain_store.weights_path)
    assert set(counts) == set(contributions), (
        "Nur beitragende Achsen duerfen lernen, alle anderen bleiben leer. "
        f"Geschrieben: {sorted(counts)}"
    )
    alphas = {axis: a for axis, (a, _b) in counts.items()}
    assert len(set(alphas.values())) == 3, (
        f"Alle Achsenwerte identisch -> Uniform, Ranking unveraenderbar: {alphas}"
    )
    # Staerkste Achse behaelt den vollen Plan-Doc-Delta (perfect => alpha 2.0)
    assert alphas["motion_match_weight"] == pytest.approx(2.0)
    assert alphas["brightness_match_weight"] == pytest.approx(2.0 * 0.45 / 0.9)
    assert alphas["semantic_match_weight"] == pytest.approx(2.0 * 0.09 / 0.9)


def test_service_feedback_accepts_contributions_from_request(service):
    """Das Request-Schema fuehrt ``axis_contributions`` bereits — der
    Service muss sie auch dann benutzen, wenn kein Keyword mitkommt."""
    resp = service.feedback(
        FeedbackRequest(
            cut_id=2,
            rating="no_match",
            axis_contributions={"kick_weight": 1.0, "snare_weight": 0.25},
        ),
        context=CutContext(),
    )
    assert resp.credit_mode == "weighted"
    counts = _level0_counts(service._brain_store.weights_path)
    assert counts["kick_weight"][1] == pytest.approx(2.0)
    assert counts["snare_weight"][1] == pytest.approx(0.5)


def test_service_feedback_without_contributions_stays_uniform(service):
    """Rueckwaertskompatibilitaet: Aufrufer ohne Beitraege duerfen nicht
    brechen — sie landen weiterhin im bewusst markierten Uniform-Pfad."""
    resp = service.feedback(
        FeedbackRequest(cut_id=3, rating="fits"),
        context=CutContext(),
    )
    assert resp.credit_mode == "uniform"
    assert resp.n_buckets_updated == len(BRIDGE_AXES) * 6

    counts = _level0_counts(service._brain_store.weights_path)
    assert set(counts) == set(BRIDGE_AXES)
    assert len({a for a, _b in counts.values()}) == 1, (
        "Uniform muss weiterhin uniform sein — sonst ist die Altkompatibilitaet weg."
    )


# ---------------------------------------------------------------------------
# B-737
# ---------------------------------------------------------------------------

class _CountingAggregator:
    def __init__(self) -> None:
        self.calls = 0
        self.done = threading.Event()

    def run(self) -> int:
        self.calls += 1
        self.done.set()
        return 7


def _worker(flush_delay_sec: float = 0.05, batch_size: int = 20):
    from workers.memory_updater import MemoryUpdaterWorker

    w = MemoryUpdaterWorker(
        session_factory=lambda: None,
        batch_size=batch_size,
        flush_delay_sec=flush_delay_sec,
    )
    agg = _CountingAggregator()
    w._aggregator = agg
    return w, agg


def test_single_event_reaches_the_aggregator():
    """Kernbeweis: EIN Ereignis reicht — nicht erst 20."""
    w, agg = _worker(flush_delay_sec=0.05)

    scheduled = w.notify_feedback()
    assert scheduled is False, "Bei 1 von 20 darf kein Sofort-Batch laufen."
    assert agg.calls == 0, "Sofort-Flush waere das alte, teure Verhalten."

    assert agg.done.wait(5.0), (
        "Debounce-Flush kam nicht — ein einzelnes Ereignis geht wieder verloren."
    )
    assert agg.calls == 1
    assert w.pending_events == 0


def test_shutdown_flushes_pending_events():
    """Lauf-Ende / Schliessen: Restereignisse duerfen nicht verfallen."""
    w, agg = _worker(flush_delay_sec=0.0)  # Timer aus -> nur shutdown zaehlt

    for _ in range(3):
        w.notify_feedback()
    assert agg.calls == 0
    assert w.pending_events == 3

    assert w.shutdown() == 7
    assert agg.calls == 1
    assert w.pending_events == 0
    # Zweiter Shutdown ohne offene Ereignisse macht nichts.
    assert w.shutdown() == 0
    assert agg.calls == 1


def test_batch_threshold_still_wins_over_debounce():
    """Regression: die 20er-Schwelle bleibt der schnelle Pfad."""
    w, agg = _worker(flush_delay_sec=30.0, batch_size=3)

    assert w.notify_feedback() is False
    assert w.notify_feedback() is False
    assert w.notify_feedback() is True

    assert agg.done.wait(5.0)
    assert agg.calls == 1


def test_brain_feedback_notifies_pattern_learning(tmp_path: Path):
    """Brain-Feedback muss beim Muster-Lernen ankommen.

    Vorher schrieb der 4-Klick-Pfad nur weights.db; der PatternAggregator
    wurde ausschliesslich vom Verdict-Pfad in ui/timeline.py angestossen.
    """
    store = BrainStore(
        weights_path=tmp_path / "w.db", patterns_path=tmp_path / "p.db",
    )
    weights = WeightStore(store.weights_path)
    seen: list[int] = []
    svc = BrainV3Service(
        brain_store=store,
        weight_store=weights,
        pattern_notifier=lambda: seen.append(1),
    )
    try:
        svc.feedback(FeedbackRequest(cut_id=9, rating="perfect"))
        svc.feedback(FeedbackRequest(cut_id=10, rating="no_match"))
    finally:
        weights.close()
    assert seen == [1, 1], "Muster-Lernen wurde nicht benachrichtigt."


def test_pattern_notify_failure_does_not_break_feedback(tmp_path: Path):
    """Der Lernkreis darf das Feedback nie mit runterreissen."""
    store = BrainStore(
        weights_path=tmp_path / "w.db", patterns_path=tmp_path / "p.db",
    )
    weights = WeightStore(store.weights_path)

    def _boom():
        raise RuntimeError("DB weg")

    svc = BrainV3Service(
        brain_store=store, weight_store=weights, pattern_notifier=_boom,
    )
    try:
        resp = svc.feedback(FeedbackRequest(cut_id=11, rating="fits"))
    finally:
        weights.close()
    assert resp.n_buckets_updated > 0


# ---------------------------------------------------------------------------
# B-738
# ---------------------------------------------------------------------------

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


class _FakeRegistry:
    """Registry-Attrappe in der Groessenordnung der echten (gemessen
    2026-07-27: 62 Aktionen, volles Schema 35.907 Zeichen, kompakte Liste
    im Template 8.601 Zeichen).

    Bewusst KEINE Nutzung des globalen ``action_registry``: andere Tests in
    derselben Session leeren es, dann waere dieser Test reihenfolge-abhaengig
    statt eine Aussage ueber den Prompt-Aufbau.
    """

    def __init__(self, n_actions: int = 62, line_len: int = 135) -> None:
        self.names = [f"pb_action_{i:03d}" for i in range(n_actions)]
        self._line_len = line_len

    def list_actions(self) -> list[str]:
        return list(self.names)

    def get_compact_action_list(self) -> str:
        return "\n".join(
            f"- {name}(media_id, mode): ".ljust(self._line_len, "x")
            for name in self.names
        )

    def get_schema_for_prompt(self) -> str:
        # Das echte Voll-Schema sprengt das Budget immer -> Kompakt-Pfad.
        return "{" + "y" * 36000 + "}"


def _prompt_service(registry=None):
    """LocalAgentService ohne Modell-/DB-Last (Muster aus
    tests/test_services/test_llm_sees_actions.py)."""
    from services.local_agent_service import LocalAgentService

    svc = LocalAgentService.__new__(LocalAgentService)
    svc._lock = threading.RLock()
    svc.registry = registry if registry is not None else _FakeRegistry()
    svc._sysprompt_base_cache = None
    svc._sysprompt_media_cache = ""
    svc._sysprompt_media_ts = 0.0
    svc._sysprompt_few_shots_cache = ""
    svc._sysprompt_few_shots_ts = 0.0
    svc._build_media_context = lambda: ""
    svc._get_positive_few_shots = lambda limit=3: ""
    return svc


def test_toolless_prompt_path_sees_brain_content(monkeypatch):
    """Kernbeweis B-738: der Plain-Chat-Prompt (kein Tool-Call noetig)
    enthaelt die gespeicherten Erkenntnisse."""
    import services.actions.brain_actions as brain_actions

    monkeypatch.setattr(
        brain_actions, "brain_recall", lambda **kw: _FAKE_RECALL,
    )

    prompt = _prompt_service()._build_system_prompt("was weisst du ueber drops?")

    assert "BRAIN-GEDAECHTNIS" in prompt
    assert "Psytrance-Drops" in prompt
    assert "role_in_section" in prompt


def test_brain_context_does_not_evict_the_action_list(monkeypatch):
    """Regression gegen Commit 5a0ac3c: die Aktionsliste muss bleiben.

    Geprueft wird gegen den LIVE-Registry-Stand, nicht gegen eine fest
    verdrahtete Namensliste — andere Tests in derselben Session tauschen das
    ``action_registry`` aus, und dann wuerde eine Fixliste den Testlauf
    reihenfolge-abhaengig machen statt den Prompt zu pruefen.
    """
    import services.actions.brain_actions as brain_actions
    from services.local_agent_service import LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS

    monkeypatch.setattr(
        brain_actions, "brain_recall", lambda **kw: _FAKE_RECALL,
    )

    registry = _FakeRegistry()
    prompt = _prompt_service(registry)._build_system_prompt(
        "was weisst du ueber drops?"
    )

    assert "BRAIN-GEDAECHTNIS" in prompt, "Vorbedingung: Brain-Block ist drin."
    assert "DOMAIN-WISSEN" in prompt, "Vorbedingung: Knowledge-Block ist drin."
    assert len(prompt) <= LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS, (
        f"Systemprompt {len(prompt)} > Budget "
        f"{LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS}"
    )
    assert "[Systemprompt gekuerzt" not in prompt, (
        "Notabschnitt am Ende bedeutet: das Budget wurde blind abgeschnitten."
    )
    missing = [n for n in registry.names if n not in prompt]
    assert missing == [], f"Aktionen aus dem Prompt gedraengt: {missing}"


def test_brain_context_is_empty_when_nothing_learned(monkeypatch):
    """Ohne Daten bleibt der Prompt exakt wie vorher — kein Platzhalter."""
    import services.actions.brain_actions as brain_actions
    from services.knowledge_loader import build_brain_context

    monkeypatch.setattr(
        brain_actions,
        "brain_recall",
        lambda **kw: {"status": "ok", "results": [], "result_count": 0},
    )
    assert build_brain_context(query="egal") == ""


def test_brain_context_respects_its_char_cap(monkeypatch):
    import services.actions.brain_actions as brain_actions
    from services.knowledge_loader import (
        BRAIN_CONTEXT_MAX_CHARS,
        build_brain_context,
    )

    many = {
        "status": "ok",
        "results": [dict(_FAKE_RECALL["results"][0]) for _ in range(200)],
    }
    monkeypatch.setattr(brain_actions, "brain_recall", lambda **kw: many)

    ctx = build_brain_context(query="drops")
    assert 0 < len(ctx) <= BRAIN_CONTEXT_MAX_CHARS


def test_brain_context_survives_a_broken_brain(monkeypatch):
    """Der Chat darf nicht sterben, nur weil das Gedaechtnis kaputt ist."""
    import services.actions.brain_actions as brain_actions
    from services.knowledge_loader import build_brain_context

    def _boom(**kw):
        raise RuntimeError("mem_decision fehlt")

    monkeypatch.setattr(brain_actions, "brain_recall", _boom)
    assert build_brain_context(query="drops") == ""
