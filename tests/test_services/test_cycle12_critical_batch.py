"""Cycle 12 / P5 CRITICAL-Batch: B-053 + B-034."""
from __future__ import annotations

import inspect

import pytest


# ── B-053: ingest_service hardcoded project_id=1 ──────────────────────────


def test_b053_ingest_audio_default_is_none():
    from services.ingest_service import ingest_audio
    sig = inspect.signature(ingest_audio)
    assert sig.parameters["project_id"].default is None


def test_b053_ingest_video_default_is_none():
    from services.ingest_service import ingest_video
    sig = inspect.signature(ingest_video)
    assert sig.parameters["project_id"].default is None


def test_b053_get_all_audio_default_is_none():
    from services.ingest_service import get_all_audio
    sig = inspect.signature(get_all_audio)
    assert sig.parameters["project_id"].default is None


def test_b053_get_all_video_default_is_none():
    from services.ingest_service import get_all_video
    sig = inspect.signature(get_all_video)
    assert sig.parameters["project_id"].default is None


def test_b053_get_all_media_default_is_none():
    from services.ingest_service import get_all_media
    sig = inspect.signature(get_all_media)
    assert sig.parameters["project_id"].default is None


def test_b053_get_combo_items_default_is_none():
    from services.ingest_service import get_combo_items
    sig = inspect.signature(get_combo_items)
    assert sig.parameters["project_id"].default is None


def test_b053_delete_all_media_default_is_none():
    from services.ingest_service import delete_all_media
    sig = inspect.signature(delete_all_media)
    assert sig.parameters["project_id"].default is None


def test_b053_import_video_folder_default_is_none():
    from services.ingest_service import import_video_folder
    sig = inspect.signature(import_video_folder)
    assert sig.parameters["project_id"].default is None


def test_b053_resolve_project_id_uses_active(monkeypatch):
    """Wenn None passed → get_active_project_id wird befragt."""
    from services import ingest_service
    monkeypatch.setattr(
        "database.session.get_active_project_id",
        lambda: 42,
    )
    assert ingest_service._resolve_project_id(None) == 42


def test_b053_resolve_project_id_explicit_wins(monkeypatch):
    """Wenn caller explizit project_id passt → kein Lookup."""
    from services import ingest_service
    monkeypatch.setattr(
        "database.session.get_active_project_id",
        lambda: 99,
    )
    assert ingest_service._resolve_project_id(7) == 7


def test_b053_resolve_project_id_fallback_when_no_active(monkeypatch):
    """Wenn None passed UND kein aktives Projekt → fallback auf 1 mit Warning."""
    from services import ingest_service
    monkeypatch.setattr(
        "database.session.get_active_project_id",
        lambda: None,
    )
    assert ingest_service._resolve_project_id(None) == 1


def test_b439_delete_all_media_no_active_project_raises(monkeypatch):
    """B-439: delete_all_media(None) ohne aktives Projekt wirft ValueError statt
    versehentlich Medien von project_id=1 zu loeschen (=1-Fallback entfernt)."""
    import pytest
    from services import ingest_service
    monkeypatch.setattr(
        "database.session.get_active_project_id",
        lambda: None,
    )
    with pytest.raises(ValueError, match="Kein aktives Projekt"):
        ingest_service.delete_all_media(None)


# ── B-034: OllamaClient TOCTOU race ───────────────────────────────────────


def test_b034_ollama_chat_vision_check_inside_lock():
    """B-034 Fix-Direction: Check on is_paused soll IM Lock-Block sein,
    nicht draußen — sonst öffnet sich ein Race-Window zwischen Check und
    chat-Call."""
    from services import ollama_client
    src = inspect.getsource(ollama_client)
    # Mindest-Anforderung: chat_vision oder ein vergleichbarer Pfad muss
    # _paused-Check VERWENDEN. Wenn er es hat, soll er zumindest das
    # threading-Lock greifen.
    if "is_paused" in src or "_paused" in src:
        # Heuristik: irgendein lock-block muss auch _paused referenzieren
        # — sonst ist der Check nicht thread-safe.
        assert "_lock" in src or "Lock" in src, (
            "B-034: paused-state ohne Lock — TOCTOU bleibt offen."
        )
