"""B-785 / B-786 / B-787: Brain-Gateway fuer Non-Tool-Modelle.

B-785: Envelope in Fliesstext wird erkannt (echter phi3:mini-Output).
B-786: Erfolgsmeldung kommt deterministisch aus dem DB-Ergebnis.
B-787: Generische Gedaechtnisfragen bekommen Recall-Kontext.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# Woertlicher phi3:mini-Output aus dem Live-Lauf 2026-08-09 (B-785).
_PHI3_EMBEDDED = (
    "Du kannst das im Brain-Gateway notieren, hier ist ein Beispiel dafuer:\n"
    '{"pb_brain_gateway":"v1","action":"brain_learn_note",'
    '"params":{"body":"Clip X darf nicht in den Drop."}}'
)
# Woertlicher gemma3:4b-Output aus dem Live-Lauf 2026-08-09 (B-786).
_GEMMA3_HALLUCINATION = (
    "Verstanden. Ich habe mir gemerkt: Clip X darf nicht in den Drop."
)
_RECALL_CONTEXT = (
    "## BRAIN-GEDAECHTNIS (selbst gelernt, nutze das statt zu raten)\n"
    '- Notiz "Drops": Harte Schnitte auf jedem vierten Beat.'
)


# --------------------------------------------------------------------------
# B-785 — eingebettetes Envelope
# --------------------------------------------------------------------------


def test_embedded_envelope_in_prose_is_executed(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock(
        return_value={
            "status": "ok",
            "action": "brain_learn_note",
            "note_id": 42,
            "created": True,
            "title": "Clip X darf nicht in den Drop",
            "message": "Erkenntnis gespeichert (brain_note #42).",
        }
    )
    monkeypatch.setattr(action_registry, "execute", execute)

    result = brain_gateway.execute_gateway_response(
        _PHI3_EMBEDDED,
        mode="chat",
        allow_learn=True,
    )

    assert result is not None
    assert result["action"] == "brain_learn_note"
    assert result["error"] is None
    action, params = execute.call_args.args
    assert action == "brain_learn_note"
    assert params["body"] == "Clip X darf nicht in den Drop."
    # Fehlender title wird defensiv aus dem body abgeleitet (B-785).
    assert params["title"].strip()


def test_second_envelope_after_plain_json_object_is_found(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock(
        return_value={"status": "ok", "action": "brain_stats", "message": "2"}
    )
    monkeypatch.setattr(action_registry, "execute", execute)

    raw = (
        'Beispiel ohne Envelope: {"action":"foo","params":{}}\n'
        "Und hier die echte Anfrage:\n"
        '{"pb_brain_gateway":"v1","action":"brain_stats","params":{}}'
    )

    result = brain_gateway.execute_gateway_response(raw, mode="chat")

    assert result is not None
    assert result["action"] == "brain_stats"
    execute.assert_called_once_with("brain_stats", {})


@pytest.mark.parametrize(
    "raw",
    [
        "Ich habe mir das gemerkt, ganz ohne JSON.",
        'Beispiel: {"action":"brain_learn_note","params":{"title":"x"}}',
        'Kaputt: {"pb_brain_gateway":"v1","action":',
        'Falsche Version: {"pb_brain_gateway":"v2","action":"brain_stats"}',
        'Ohne Action: {"pb_brain_gateway":"v1","params":{}}',
    ],
)
def test_prose_without_valid_envelope_stays_plain_chat(monkeypatch, raw):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock()
    monkeypatch.setattr(action_registry, "execute", execute)

    assert brain_gateway.execute_gateway_response(raw, mode="chat") is None
    execute.assert_not_called()


def test_embedded_envelope_keeps_fail_closed_rules(monkeypatch):
    """Toleranteres Finden weicht die Sicherheitsregeln nicht auf."""
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock()
    monkeypatch.setattr(action_registry, "execute", execute)

    without_intent = brain_gateway.execute_gateway_response(
        _PHI3_EMBEDDED,
        mode="chat",
        allow_learn=False,
    )
    in_vision = brain_gateway.execute_gateway_response(
        _PHI3_EMBEDDED,
        mode="vision",
        allow_learn=True,
    )
    free_tool = brain_gateway.execute_gateway_response(
        'Vorschlag:\n{"pb_brain_gateway":"v1","action":"delete_project",'
        '"params":{"project_id":1}}',
        mode="chat",
    )

    assert without_intent["action"] == "brain_gateway_rejected"
    assert "Merk-/Speicherauftrag" in without_intent["error"]
    assert in_vision["action"] == "brain_gateway_rejected"
    assert "nicht erlaubt" in in_vision["error"]
    assert free_tool["action"] == "brain_gateway_rejected"
    assert "nicht erlaubt" in free_tool["error"]
    execute.assert_not_called()


# --------------------------------------------------------------------------
# B-786 — Bestaetigung aus dem DB-Ergebnis
# --------------------------------------------------------------------------


def test_hallucinated_save_without_gateway_action_is_reported_as_not_written(
    monkeypatch,
):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock()
    monkeypatch.setattr(action_registry, "execute", execute)

    result = brain_gateway.execute_gateway_response(
        _GEMMA3_HALLUCINATION,
        mode="chat",
        allow_learn=True,
    )

    assert result is not None
    assert result["action"] == "brain_learn_note_not_written"
    assert result["result"] is None
    assert result["error"]
    assert "NICHTS gespeichert" in result["message"]
    assert "Ich habe mir gemerkt" not in result["message"]
    execute.assert_not_called()


def test_failed_db_write_does_not_claim_success(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    monkeypatch.setattr(
        action_registry,
        "execute",
        MagicMock(
            return_value={
                "status": "error",
                "action": "brain_learn_note",
                "message": "Tabelle 'brain_note' existiert nicht.",
            }
        ),
    )

    result = brain_gateway.execute_gateway_response(
        _PHI3_EMBEDDED,
        mode="chat",
        allow_learn=True,
    )

    assert result["error"] == "Tabelle 'brain_note' existiert nicht."
    assert "NICHTS gespeichert" in result["message"]


def test_successful_write_message_comes_from_db_result(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    monkeypatch.setattr(
        action_registry,
        "execute",
        MagicMock(
            return_value={
                "status": "ok",
                "action": "brain_learn_note",
                "note_id": 7,
                "created": True,
                "title": "Clip X",
                "message": "Erkenntnis gespeichert (brain_note #7).",
            }
        ),
    )

    result = brain_gateway.execute_gateway_response(
        _PHI3_EMBEDDED,
        mode="chat",
        allow_learn=True,
    )

    assert result["message"] == "Erkenntnis gespeichert (brain_note #7)."
    assert result["error"] is None


def test_normal_chat_without_learn_intent_is_unchanged(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock()
    monkeypatch.setattr(action_registry, "execute", execute)

    assert (
        brain_gateway.execute_gateway_response(
            "Der Drop startet bei 1:24.",
            mode="chat",
            allow_learn=False,
        )
        is None
    )
    execute.assert_not_called()


# --------------------------------------------------------------------------
# B-787 — Recall-Fallback fuer generische Gedaechtnisfragen
# --------------------------------------------------------------------------


def _patch_token_miss(monkeypatch) -> list[str]:
    import services.knowledge_loader as knowledge_loader

    queries: list[str] = []

    def _fake(**kwargs):
        query = kwargs.get("query", "")
        queries.append(query)
        return _RECALL_CONTEXT if not query else ""

    monkeypatch.setattr(knowledge_loader, "build_brain_context", _fake)
    return queries


def test_generic_memory_question_gets_context_in_nontool_prompt(monkeypatch):
    from services import brain_gateway

    queries = _patch_token_miss(monkeypatch)

    prompt = brain_gateway.build_nontool_prompt(
        "BASE",
        query="Was hast du dir bisher gemerkt?",
    )

    assert queries == ["Was hast du dir bisher gemerkt?", ""]
    assert _RECALL_CONTEXT in prompt
    assert prompt.startswith("BASE")
    assert "brain_learn_note" in prompt


def test_generic_memory_question_gets_context_in_tool_prompt(monkeypatch):
    from services import brain_gateway

    queries = _patch_token_miss(monkeypatch)

    prompt = brain_gateway.build_tool_prompt(
        "BASE",
        query="Was hast du dir bisher gemerkt?",
    )

    assert queries == ["Was hast du dir bisher gemerkt?", ""]
    assert _RECALL_CONTEXT in prompt


def test_empty_brain_leaves_prompts_untouched(monkeypatch):
    import services.knowledge_loader as knowledge_loader
    from services import brain_gateway

    monkeypatch.setattr(
        knowledge_loader, "build_brain_context", lambda **_kw: ""
    )

    assert brain_gateway.build_tool_prompt("BASE", query="irgendwas") == "BASE"
    nontool = brain_gateway.build_nontool_prompt("BASE", query="irgendwas")
    assert nontool.startswith("BASE")
    assert "BRAIN-GEDAECHTNIS" not in nontool
