"""B-065 + B-067 + B-070 + B-081 + B-082 + B-083 + B-091 Batch-7."""

from __future__ import annotations

import inspect


def test_b065_structure_save_no_engine_dispose() -> None:
    """B-065: structure_detection_service.save_to_db hat KEINEN engine.dispose()
    mehr im Retry-Loop (Code, nicht Doc-Erwaehnung)."""
    import ast
    from services.structure_detection_service import StructureDetectionService

    import textwrap
    src = textwrap.dedent(inspect.getsource(StructureDetectionService.save_to_db))
    tree = ast.parse(src)

    # Suche nach Method-Calls 'engine.dispose()' in den Statements
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if (node.func.attr == "dispose"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "engine"):
                found = True
                break
    assert not found, (
        "B-065: engine.dispose() im Retry-Loop schliesst Cross-Worker-Connections."
    )


def test_b067_spectral_events_merged_not_overwritten() -> None:
    """B-067: analyze_extended merget band_events mit existing events,
    nicht ueberschreiben."""
    from services.spectral_analysis_service import SpectralAnalysisService

    src = inspect.getsource(SpectralAnalysisService.analyze_extended)
    # Kein direktes Ueberschreiben mehr
    assert "spectral.events = band_events" not in src
    # Stattdessen: merge + dedupe
    assert "_deduplicate_events" in src
    assert "spectral.events" in src


def test_b070_create_proxy_accepts_should_stop() -> None:
    """B-070: VideoAnalyzer.create_proxy akzeptiert should_stop und nutzt
    Popen + Poll-Loop statt subprocess.run."""
    from services.video_service import VideoAnalyzer

    sig = inspect.signature(VideoAnalyzer.create_proxy)
    assert "should_stop" in sig.parameters

    src = inspect.getsource(VideoAnalyzer.create_proxy)
    assert "Popen(" in src or "subprocess.Popen" in src
    assert "should_stop" in src
    # Loop-basierter Watchdog
    assert "proc.poll() is None" in src or ".poll()" in src


def test_b070_video_analyzer_propagates_should_stop() -> None:
    """B-070: VideoAnalysisWorker / VideoBatchAnalysisWorker reichen
    should_stop an analyze_and_store durch."""
    from workers.video import VideoAnalysisWorker, VideoBatchAnalysisWorker

    for cls in (VideoAnalysisWorker, VideoBatchAnalysisWorker):
        src = inspect.getsource(cls)
        assert "should_stop=self.should_stop" in src, (
            f"B-070: {cls.__name__} muss should_stop weiterreichen."
        )


def test_b081_action_registry_threshold_raised() -> None:
    """B-081: FUZZY_THRESHOLD ist auf 85 angehoben (vorher 55)."""
    from services import action_registry as ar_mod

    assert ar_mod.FUZZY_THRESHOLD >= 85
    assert hasattr(ar_mod, "DESTRUCTIVE_ACTIONS")
    assert "delete_all_media" in ar_mod.DESTRUCTIVE_ACTIONS
    assert ar_mod.DESTRUCTIVE_FUZZY_THRESHOLD >= 95


def test_b081_resolve_blocks_destructive_low_score() -> None:
    """B-081: resolve() weigert sich, destruktive Action per Fuzzy unter
    DESTRUCTIVE_FUZZY_THRESHOLD aufzurufen."""
    from services.action_registry import ActionRegistry

    src = inspect.getsource(ActionRegistry.resolve)
    assert "DESTRUCTIVE_ACTIONS" in src
    assert "DESTRUCTIVE_FUZZY_THRESHOLD" in src
    assert "REFUSED" in src or "return None" in src


def test_b082_local_agent_caches_system_prompt_components() -> None:
    """B-082: LocalAgentService cached base/media/few_shots Bestandteile
    + bietet invalidate_system_prompt_cache()."""
    from services.local_agent_service import LocalAgentService

    src = inspect.getsource(LocalAgentService._build_system_prompt)
    assert "_sysprompt_base_cache" in src
    assert "_sysprompt_media_cache" in src
    assert "_sysprompt_few_shots_cache" in src

    assert hasattr(LocalAgentService, "invalidate_system_prompt_cache")


def test_b083_get_imported_ids_uses_tuple_query() -> None:
    """B-083: _get_imported_ids nutzt tuple-Query (kein ORM-Hydrate)."""
    from agents.orchestrator_agent import OrchestratorAgent

    src = inspect.getsource(OrchestratorAgent._get_imported_ids)
    # Tuple-Query statt query(AudioTrack).all()
    assert "AudioTrack.id" in src or "(AudioTrack.id," in src
    assert "VideoClip.id" in src or "(VideoClip.id," in src
    # nullpool_session statt direct Session(engine)
    assert "nullpool_session" in src


def test_b091_init_db_uses_clear_strategy() -> None:
    """B-091: init_db erkennt Fresh-DB vs Existing-DB und behandelt sie
    unterschiedlich (kein blindes create_all + Alembic upgrade head)."""
    from database import migrations

    src = inspect.getsource(migrations.init_db)
    assert "is_fresh" in src or "existing_tables" in src
    assert "command.stamp" in src
    assert "_run_alembic_migrations" in src
