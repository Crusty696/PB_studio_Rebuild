"""B-222-A — Model-Warmup Pre-Flight Tests.

Hintergrund: Cross-Thread Use-After-Free Crash (B-222) entstand durch
~2.5 GB SigLIP-Download in Worker-Thread waehrend UI-Interaktion.
Pre-Flight im Pipeline-Worker erkennt unvollstaendigen Cache und laedt
das Modell VOR dem GPU_LOAD_LOCK herunter.
"""
from __future__ import annotations

import inspect
from unittest.mock import patch


def test_b222a_model_warmup_module_exists() -> None:
    """services.model_warmup ist importierbar mit erwarteter API."""
    from services import model_warmup as mw

    assert hasattr(mw, "is_siglip_cached")
    assert hasattr(mw, "is_raft_cached")
    assert hasattr(mw, "warmup_siglip")
    assert hasattr(mw, "warmup_raft")
    assert hasattr(mw, "warmup_all")
    assert hasattr(mw, "check_pipeline_models_ready")


def test_b222a_is_siglip_cached_returns_tuple_bool_list() -> None:
    """is_siglip_cached liefert (vollstaendig, fehlende_liste) Tuple."""
    from services.model_warmup import is_siglip_cached

    result = is_siglip_cached()
    assert isinstance(result, tuple) and len(result) == 2
    cached, missing = result
    assert isinstance(cached, bool)
    assert isinstance(missing, list)


def test_b222a_is_siglip_cached_detects_missing_safetensors() -> None:
    """Wenn try_to_load_from_cache fuer model.safetensors None liefert,
    soll is_siglip_cached cached=False mit safetensors in missing-Liste
    zurueckgeben."""
    from services import model_warmup as mw

    def fake_lookup(repo_id, filename):
        # Alle Files vorhanden außer model.safetensors
        if filename == "model.safetensors":
            return None
        return f"/fake/cache/{filename}"

    with patch("huggingface_hub.try_to_load_from_cache", side_effect=fake_lookup):
        cached, missing = mw.is_siglip_cached("test/model")

    assert cached is False
    assert "model.safetensors" in missing


def test_b222a_is_siglip_cached_full_cache_returns_true() -> None:
    from services import model_warmup as mw

    def fake_lookup(repo_id, filename):
        return f"/fake/cache/{filename}"

    with patch("huggingface_hub.try_to_load_from_cache", side_effect=fake_lookup):
        cached, missing = mw.is_siglip_cached("test/model")

    assert cached is True
    assert missing == []


def test_b222a_warmup_siglip_skips_when_cached() -> None:
    """Wenn cache vollstaendig: kein snapshot_download-Call."""
    from services import model_warmup as mw

    def fake_lookup(repo_id, filename):
        return f"/fake/cache/{filename}"

    snapshot_calls = []
    def fake_snapshot(*args, **kwargs):
        snapshot_calls.append((args, kwargs))

    with patch("huggingface_hub.try_to_load_from_cache", side_effect=fake_lookup), \
         patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot):
        ok = mw.warmup_siglip("test/model")

    assert ok is True
    assert len(snapshot_calls) == 0, (
        "B-222-A: warmup_siglip darf nicht downloaden, wenn cache vollstaendig."
    )


def test_b222a_warmup_siglip_calls_snapshot_when_missing() -> None:
    """Wenn safetensors fehlt: snapshot_download wird aufgerufen."""
    from services import model_warmup as mw

    call_count = {"check": 0}
    def fake_lookup(repo_id, filename):
        call_count["check"] += 1
        # Erste Pruefung: safetensors fehlt. Nach Download: alles da.
        if call_count["check"] <= 3 and filename == "model.safetensors":
            return None
        return f"/fake/cache/{filename}"

    snapshot_calls = []
    def fake_snapshot(*args, **kwargs):
        snapshot_calls.append((args, kwargs))

    with patch("huggingface_hub.try_to_load_from_cache", side_effect=fake_lookup), \
         patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot):
        ok = mw.warmup_siglip("test/model")

    assert len(snapshot_calls) == 1, (
        "B-222-A: warmup_siglip muss snapshot_download bei missing files rufen."
    )


def test_b222a_check_pipeline_models_ready_format() -> None:
    """check_pipeline_models_ready -> (bool, list[str]) Format."""
    from services.model_warmup import check_pipeline_models_ready

    ready, gaps = check_pipeline_models_ready()
    assert isinstance(ready, bool)
    assert isinstance(gaps, list)
    if not ready:
        assert all(isinstance(g, str) for g in gaps)


def test_b222a_pipeline_worker_has_preflight() -> None:
    """workers/video.py:VideoAnalysisPipelineWorker.run hat Pre-Flight-Check
    VOR GPU_LOAD_LOCK."""
    from workers.video import VideoAnalysisPipelineWorker

    src = inspect.getsource(VideoAnalysisPipelineWorker.run)
    assert "model_warmup" in src or "is_siglip_cached" in src, (
        "B-222-A: Pre-Flight-Check fehlt im Pipeline-Worker."
    )
    # Pre-Flight muss VOR GPU_LOAD_LOCK stehen — sonst entstehen die UAFs
    # waehrend das UI durch Lock-Wait blockiert ist.
    preflight_idx = src.find("is_siglip_cached")
    if preflight_idx == -1:
        preflight_idx = src.find("model_warmup")
    # Wir suchen den echten Lock-Acquire, nicht bloße Comment-Erwaehnung des
    # Symbols. Neuere Pipeline nutzt ``gpu_resource_lease(...)``; dieser
    # Contextmanager kapselt ``with GPU_LOAD_LOCK`` in services.model_manager.
    lock_idx = src.find("with GPU_LOAD_LOCK")
    if lock_idx == -1:
        lock_idx = src.find("with gpu_resource_lease")
    assert preflight_idx > 0
    assert lock_idx > 0
    assert preflight_idx < lock_idx, (
        "B-222-A: Pre-Flight muss VOR dem ersten `with GPU_LOAD_LOCK` stehen."
    )


def test_b222a_warmup_script_exists() -> None:
    """scripts/warmup_models.py existiert + hat --check-only flag."""
    from pathlib import Path

    script_path = Path(__file__).parent.parent.parent / "scripts" / "warmup_models.py"
    assert script_path.exists(), "B-222-A: scripts/warmup_models.py muss existieren."

    src = script_path.read_text(encoding="utf-8")
    assert "--check-only" in src
    assert "warmup_all" in src or "warmup_siglip" in src
