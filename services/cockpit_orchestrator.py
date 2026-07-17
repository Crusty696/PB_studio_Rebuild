"""Guided Cockpit readiness and next-action orchestration.

V1 ist absichtlich eine duenne Schicht: keine Migration, keine ML-Ausfuehrung,
kein neues Backend. Der Orchestrator liest vorhandene DB-/Statusdaten und
liefert dem Cockpit eine eindeutige naechste Aktion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select

import database


@dataclass(frozen=True)
class PipelineStepSpec:
    key: str
    media_type: str
    label: str
    required_for_auto_edit: bool
    action_key: str


@dataclass(frozen=True)
class CockpitAction:
    key: str
    label: str
    description: str
    enabled: bool = True
    target_workspace: int | None = None
    command: str | None = None


@dataclass(frozen=True)
class CockpitReadiness:
    project_id: int | None
    project_name: str | None = None
    project_path: str | None = None
    audio_ready: bool = False
    video_ready: bool = False
    can_auto_edit: bool = False
    can_export: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_action: CockpitAction = field(default_factory=lambda: ACTIONS["open_project"])
    counts: dict[str, int] = field(default_factory=dict)
    cards: dict[str, str] = field(default_factory=dict)
    missing_steps_per_card: dict[str, list[str]] = field(default_factory=dict)


AUDIO_STEP_SPECS = [
    PipelineStepSpec("bpm_detection", "audio", "Beats", True, "run_audio_complete"),
    PipelineStepSpec("waveform_analysis", "audio", "Waveform", True, "run_audio_complete"),
    PipelineStepSpec("key_detection", "audio", "Tonart", True, "run_audio_complete"),
    PipelineStepSpec("lufs_analysis", "audio", "LUFS", True, "run_audio_complete"),
    PipelineStepSpec("mood_genre_classify", "audio", "Mood/Genre", True, "run_audio_complete"),
    PipelineStepSpec("spectral_analysis", "audio", "Spektral", True, "run_audio_complete"),
    PipelineStepSpec("structure_detection", "audio", "Songstruktur", True, "run_audio_complete"),
    PipelineStepSpec("stem_separation", "audio", "Stems", True, "run_audio_complete"),
    # Stage-Sichtbarkeit (User 2026-07-17): optionale Audio-V2-Steps —
    # sichtbar, aber required=False -> gaten die Cockpit-Readiness NICHT
    # (alte Tracks ohne diese Marks bleiben "ready").
    PipelineStepSpec("onset_detection", "audio", "Onsets", False, "run_audio_complete"),
    PipelineStepSpec("av_pacing_curves", "audio", "AV-Pacing", False, "run_audio_complete"),
]

VIDEO_STEP_SPECS = [
    PipelineStepSpec("scene_detection", "video", "Szenen", True, "run_video_pipeline"),
    PipelineStepSpec("motion_scores", "video", "Bewegung", True, "run_video_pipeline"),
    PipelineStepSpec("keyframe_extraction", "video", "Keyframes", True, "run_video_pipeline"),
    PipelineStepSpec("siglip_embeddings", "video", "Embeddings", True, "run_video_pipeline"),
    PipelineStepSpec("vector_db_storage", "video", "Suchindex", True, "run_video_pipeline"),
    PipelineStepSpec("scene_db_storage", "video", "Szenen speichern", True, "run_video_pipeline"),
    PipelineStepSpec("ai_scene_caption", "video", "Captioning", False, "run_video_pipeline"),
]

ACTIONS = {
    "open_project": CockpitAction(
        key="open_project",
        label="Projekt starten",
        description="Lege ein Projekt an oder oeffne ein bestehendes Projekt.",
        target_workspace=0,
    ),
    "open_material_analysis": CockpitAction(
        key="open_material_analysis",
        label="Material importieren",
        description="Importiere Audio und Video oder waehle bestehendes Material.",
        target_workspace=1,
    ),
    "run_audio_complete": CockpitAction(
        key="run_audio_complete",
        label="Audio analysieren",
        description="Erzeugt Beats, Waveform, Tonart, LUFS, Mood/Genre, Spektral-Daten, Songstruktur und Stems.",
        target_workspace=1,
        command="run_audio_complete",
    ),
    "run_video_pipeline": CockpitAction(
        key="run_video_pipeline",
        label="Video analysieren",
        description="Erzeugt Szenen, Bewegung, Keyframes und Suchdaten fuer Matching.",
        target_workspace=1,
        command="run_video_pipeline",
    ),
    "open_schnitt": CockpitAction(
        key="open_schnitt",
        label="Schnitt oeffnen",
        description="Auto-Edit starten oder Timeline pruefen.",
        target_workspace=2,
    ),
    # Legacy aliases (Phase 10): both fold into open_schnitt but keep
    # distinct labels/descriptions so existing call sites stay readable.
    "open_auto_edit": CockpitAction(
        key="open_schnitt",
        label="Schnitt oeffnen (Auto-Edit)",
        description="Audio und Video sind bereit. Erzeuge die beat-synchrone Timeline im SCHNITT-Workspace.",
        target_workspace=2,
    ),
    "open_review": CockpitAction(
        key="open_schnitt",
        label="Schnitt oeffnen (Review)",
        description="Timeline ist vorhanden. Pruefe Schnitt, Vorschau und Inspector im SCHNITT-Workspace.",
        target_workspace=2,
    ),
    "open_export": CockpitAction(
        key="open_export",
        label="Export vorbereiten",
        description="Timeline ist vorhanden. Rendere Preview oder finales Video.",
        target_workspace=3,
    ),
}


def get_cockpit_readiness(project_id: int | None) -> CockpitReadiness:
    if project_id is None:
        return CockpitReadiness(
            project_id=None,
            blockers=["Kein Projekt geladen"],
            next_action=ACTIONS["open_project"],
            cards=_cards(False, False, False, False),
            missing_steps_per_card={
                "audio": ["kein_projekt"],
                "video": ["kein_projekt"],
                "auto_edit": ["kein_projekt"],
                "export": ["kein_projekt"],
            },
        )

    with database.nullpool_session() as session:
        project = session.get(database.Project, project_id)
        if project is None:
            return CockpitReadiness(
                project_id=project_id,
                blockers=["Projekt nicht gefunden"],
                next_action=ACTIONS["open_project"],
                cards=_cards(False, False, False, False),
                missing_steps_per_card={
                    "audio": ["kein_projekt"],
                    "video": ["kein_projekt"],
                    "auto_edit": ["kein_projekt"],
                    "export": ["kein_projekt"],
                },
            )

        audio_ids = session.execute(
            select(database.AudioTrack.id).where(
                database.AudioTrack.project_id == project_id,
                database.AudioTrack.deleted_at.is_(None),
            )
        ).scalars().all()
        video_ids = session.execute(
            select(database.VideoClip.id).where(
                database.VideoClip.project_id == project_id,
                database.VideoClip.deleted_at.is_(None),
            )
        ).scalars().all()
        timeline_count = session.scalar(
            select(func.count(database.TimelineEntry.id)).where(
                database.TimelineEntry.project_id == project_id
            )
        ) or 0

        audio_status = _status_by_media(session, "audio", audio_ids)
        video_status = _status_by_media(session, "video", video_ids)

        audio_ready = bool(audio_ids) and _all_required_done(audio_status, AUDIO_STEP_SPECS)
        video_ready = bool(video_ids) and _all_required_done(video_status, VIDEO_STEP_SPECS)
        can_auto_edit = audio_ready and video_ready
        can_export = timeline_count > 0

        blockers: list[str] = []
        warnings: list[str] = []
        if not audio_ids and not video_ids:
            blockers.append("Kein Audio oder Video importiert")
        elif not audio_ids:
            blockers.append("Kein Audio importiert")
        elif not video_ids:
            blockers.append("Kein Video importiert")
        if audio_ids and not audio_ready:
            blockers.append("Audioanalyse fehlt")
        if video_ids and not video_ready:
            blockers.append("Videoanalyse fehlt")
        if audio_ids and _missing_optional(audio_status, AUDIO_STEP_SPECS):
            warnings.append("Stems fehlen: Auto-Schnitt geht, Qualitaet kann aber geringer sein")
        if video_ids and _missing_step(video_status, "ai_scene_caption"):
            warnings.append("Captioning fehlt: kein Blocker, aber weniger Kontext fuer Review")

        next_action = _next_action(
            audio_ids=audio_ids,
            video_ids=video_ids,
            audio_ready=audio_ready,
            video_ready=video_ready,
            can_auto_edit=can_auto_edit,
            can_export=can_export,
        )

        missing_steps = {
            "audio": _missing_required_steps(audio_status, AUDIO_STEP_SPECS) if audio_ids else ["kein_audio"],
            "video": _missing_required_steps(video_status, VIDEO_STEP_SPECS) if video_ids else ["kein_video"],
            "auto_edit": [] if can_auto_edit else ["audio_video_unvollstaendig"],
            "export": [] if can_export else ["timeline_leer"],
        }

        return CockpitReadiness(
            project_id=project_id,
            project_name=project.name,
            project_path=project.path,
            audio_ready=audio_ready,
            video_ready=video_ready,
            can_auto_edit=can_auto_edit,
            can_export=can_export,
            blockers=blockers,
            warnings=warnings,
            next_action=next_action,
            counts={
                "audio": len(audio_ids),
                "video": len(video_ids),
                "timeline": int(timeline_count),
            },
            cards=_cards(audio_ready, video_ready, can_auto_edit, can_export),
            missing_steps_per_card=missing_steps,
        )


def dispatch_cockpit_action(
    action_key: str,
    payload: dict[str, Any] | None = None,
    task_manager: Any | None = None,
) -> bool:
    """Dispatch ueber bestehendes Command-Pattern, falls Worker registriert ist."""
    action = ACTIONS.get(action_key)
    if action is None or action.command is None:
        return False
    if task_manager is None:
        from services.task_manager import GlobalTaskManager

        task_manager = GlobalTaskManager.instance()
    registry = getattr(task_manager, "_WORKER_REGISTRY", {})
    if action.command not in registry:
        return False
    task_manager.agent_command_signal.emit(action.command, payload or {})
    return True


def _status_by_media(session, media_type: str, media_ids: list[int]) -> dict[int, dict[str, str]]:
    if not media_ids:
        return {}
    rows = session.execute(
        select(database.AnalysisStatus).where(
            database.AnalysisStatus.media_type == media_type,
            database.AnalysisStatus.media_id.in_(media_ids),
        )
    ).scalars().all()
    result: dict[int, dict[str, str]] = {mid: {} for mid in media_ids}
    for row in rows:
        result.setdefault(row.media_id, {})[row.step_key] = row.status
    return result


def _all_required_done(status_by_media: dict[int, dict[str, str]], specs: list[PipelineStepSpec]) -> bool:
    required = [spec.key for spec in specs if spec.required_for_auto_edit]
    if not status_by_media:
        return False
    return all(
        all(status.get(key) == "done" for key in required)
        for status in status_by_media.values()
    )


def _missing_optional(status_by_media: dict[int, dict[str, str]], specs: list[PipelineStepSpec]) -> bool:
    optional = [spec.key for spec in specs if not spec.required_for_auto_edit]
    return any(
        any(status.get(key) != "done" for key in optional)
        for status in status_by_media.values()
    )


def _missing_step(status_by_media: dict[int, dict[str, str]], step_key: str) -> bool:
    return any(status.get(step_key) != "done" for status in status_by_media.values())


def _missing_required_steps(
    status_by_media: dict[int, dict[str, str]],
    specs: list["PipelineStepSpec"],
) -> list[str]:
    """B-292/D: required Step-Keys die fuer mindestens ein Medium offen sind."""
    required = [spec.key for spec in specs if spec.required_for_auto_edit]
    if not status_by_media:
        # Konsistent mit _all_required_done: kein Status-Eintrag = nichts ist done.
        return sorted(required)
    missing: set[str] = set()
    for status in status_by_media.values():
        for key in required:
            if status.get(key) != "done":
                missing.add(key)
    return sorted(missing)


def _next_action(
    audio_ids: list[int],
    video_ids: list[int],
    audio_ready: bool,
    video_ready: bool,
    can_auto_edit: bool,
    can_export: bool,
) -> CockpitAction:
    if can_export:
        return ACTIONS["open_review"]
    if can_auto_edit:
        return ACTIONS["open_auto_edit"]
    if audio_ids and not audio_ready:
        return ACTIONS["run_audio_complete"]
    if video_ids and not video_ready:
        return ACTIONS["run_video_pipeline"]
    if not audio_ids or not video_ids:
        return ACTIONS["open_material_analysis"]
    return ACTIONS["open_material_analysis"]


def _cards(audio_ready: bool, video_ready: bool, can_auto_edit: bool, can_export: bool) -> dict[str, str]:
    return {
        "audio": "ready" if audio_ready else "blocked",
        "video": "ready" if video_ready else "blocked",
        "auto_edit": "ready" if can_auto_edit else "blocked",
        "export": "ready" if can_export else "blocked",
    }
