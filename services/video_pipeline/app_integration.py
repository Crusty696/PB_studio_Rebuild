"""App-Integration der Video-Pipeline-Engine — schmaler, reversibler Erststep.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19 (Phase 38/41 Vorstufe).

Stellt eine app-aufrufbare Entry-Funktion bereit, die den NEUEN Orchestrator
(``services/video_pipeline/orchestrator.VideoAnalysisPipeline``) auf EINEM Clip
laeuft. Damit ist u.a. der B-440-/8-RAFT-Fix im echten App-Entry-Point belegbar.

WICHTIG (Governance / reversibel):
- Ersetzt NICHT den bestehenden Pfad ``services/video_analysis_service`` /
  ``VideoAnalysisPipelineWorker``. Rein additiv.
- Nur aktiv wenn Feature-Flag ``PB_ENABLE_VIDEO_PIPELINE_ENGINE=1`` gesetzt ist.
- Default-Verhalten der App bleibt unveraendert (Flag aus -> diese Funktion wird
  vom Controller nicht aufgerufen).
"""
from __future__ import annotations

import os
from pathlib import Path

FEATURE_FLAG = "PB_ENABLE_VIDEO_PIPELINE_ENGINE"
_TRUE = {"1", "true", "yes", "on"}


def engine_enabled() -> bool:
    """True wenn die DAG-Video-Engine aktiviert wurde.

    NEUBAU-VOLLINTEGRATION M3 (D-065): Aktivierung ueber persistentes
    Setting ``video.use_pipeline_engine`` (SettingsStore, UI-Schalter).
    Die Env-Var ``PB_ENABLE_VIDEO_PIPELINE_ENGINE`` bleibt als OVERRIDE:
    ist sie nicht-leer gesetzt, gewinnt sie — "1/true/yes/on" erzwingt AN,
    alles andere AUS (Test-Determinismus). Default AUS bis der
    Paritaets-Nachweis (Engine == Monolith) erbracht ist.
    """
    env = os.getenv(FEATURE_FLAG, "")
    if env.strip() != "":
        return env.strip().lower() in _TRUE
    try:
        from services.settings_store import get_settings_store
        return bool(get_settings_store().get_nested(
            "video", "use_pipeline_engine", default=False))
    except Exception:  # Settings duerfen das Gate nie crashen
        return False


def build_pipeline(
    track_id: int,
    source_path,
    storage_dir,
    *,
    raft_variant: str = "raft_small",
    listener=None,
):
    """Baut die Produktions-Stage-Kette + Orchestrator fuer einen Clip.

    Gibt ``(pipeline, (siglip_service, raft_service))`` zurueck. Die Services
    werden mit zurueckgegeben, damit der Aufrufer sie nach dem Lauf entladen kann.
    """
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    from services.video_pipeline.stages.vlm_caption_stage import VlmCaptionStage
    from services.video_pipeline.stages.cross_modal_stage import CrossModalStage
    # NEUBAU-VOLLINTEGRATION M3 (D-065): Persistenz-Stage schreibt die
    # Engine-Artefakte in Scene + VectorDB (vorher nur Dateien).
    from services.video_pipeline.stages.db_persist_stage import DbPersistStage

    source_path = Path(source_path)
    storage_dir = Path(storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = storage_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = ResumeCheckpoint.load(
        storage_dir / "checkpoint.json",
        track_id=track_id,
        stream_sha256=stream_sha256(source_path),
    )

    # NEUBAU-VOLLINTEGRATION M3 (DEAD-008): ohne externen Listener bekommt der
    # Engine-Lauf einen JsonlObserver — Stage-Events landen als Audit-Trail in
    # storage_dir/pipeline.events.jsonl (vorher war observability.py toter
    # Code). Uebergibt der Aufrufer einen eigenen Listener (UI-Qt-Signale),
    # bleibt der unangetastet.
    if listener is None:
        try:
            from services.video_pipeline.observability import JsonlObserver
            listener = JsonlObserver(storage_dir / "pipeline.events.jsonl")
        except Exception:  # Observability darf den Lauf nie blockieren
            listener = None
    siglip = SigLipEmbedService(model_id="google/siglip-so400m-patch14-384")
    # M3 (D-065): feste Flow-Aufloesung 520x320 (H=320, W=520) wie der
    # Monolith-Pfad (_raft_motion_score), damit Scene.energy zwischen beiden
    # Pipelines auf derselben Motion-Skala liegt (Paritaets-Fix).
    raft = RaftMotionService(variant=raft_variant, flow_resolution=(320, 520))

    # D-065: Projekt-Token beim Pipeline-Bau festhalten, damit ein mid-run
    # Projektwechsel den Scene-Write in die falsche DB verhindert (gleiche
    # Guard-Semantik wie der Monolith-Pfad).
    try:
        from services.video_analysis_service import _current_db_url
        _expected_db_url = _current_db_url()
    except Exception:
        _expected_db_url = None

    stages = [
        ProxyGenStage(),
        SceneDetectStage(),
        KeyframeExtractStage(mode="mid"),
        SigLipEmbedStage(service=siglip, batch_size=2),
        RaftMotionStage(service=raft, sample_rate_s=1.0),
        VlmCaptionStage(),
        CrossModalStage(audio_outputs_dir=audio_dir),
        # Muss ZULETZT laufen — liest scenes/keyframes/embeddings/motion/
        # captions und schreibt Scene + VectorDB (D-065 / PIPE-018).
        DbPersistStage(clip_id=track_id, expected_db_url=_expected_db_url),
    ]
    pipe = VideoAnalysisPipeline(
        track_id=track_id,
        source_path=source_path,
        storage_dir=storage_dir,
        stages=stages,
        checkpoint=checkpoint,
        listener=listener,
    )
    return pipe, (siglip, raft)


def run_video_pipeline_on_clip(
    track_id: int,
    source_path,
    storage_dir,
    *,
    raft_variant: str = "raft_small",
    listener=None,
):
    """Laeuft die neue Engine auf einem Clip und entlaedt GPU-Services danach.

    Returns:
        PipelineResult des Orchestrators.
    """
    pipe, (siglip, raft) = build_pipeline(
        track_id, source_path, storage_dir,
        raft_variant=raft_variant, listener=listener,
    )
    try:
        return pipe.run()
    finally:
        for svc in (siglip, raft):
            try:
                svc.unload()
            except Exception:  # noqa: BLE001 — Unload best effort
                pass
