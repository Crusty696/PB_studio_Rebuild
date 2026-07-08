"""DB-Persist-Stage — schreibt Engine-Artefakte in Scene + VectorDB.

NEUBAU-VOLLINTEGRATION M3 / Paket 3 (USE-003 / PIPE-018), Decision D-065:
Die DAG-Engine schrieb bisher nur Datei-Artefakte
(``scenes.json``/``keyframes.json``/``embeddings.npy``/``motion.json``/
``captions.json``) und NICHT in die von der App gelesenen Senken. Damit sah
UI/Suche/Pacing/Studio-Brain nach einem Engine-Lauf nichts.

Diese Stage laeuft ZULETZT und ueberbrueckt die Luecke, indem sie die
Artefakte einliest, pro Szene ein ``SceneInfo`` (Monolith-Dataclass) baut und
die **bewaehrten** Monolith-Writer wiederverwendet:

- ``store_scenes_in_db``  -> Scene-Tabelle (energy, ai_caption/mood/tags),
  inkl. Projekt-Token-Guard + Soft-Delete/FK-Guard.
- ``store_embeddings``    -> LanceDB (delete_by_clip_ids vor add).

Bewusst KEINE Neuimplementierung der DB-Logik — nur ein Adapter von
Engine-Artefakt-Formaten auf ``SceneInfo``.

Parität/Toleranzen (ehrlich dokumentiert):
- Motion: die Engine-``mean_magnitude`` entsteht auf anderer Aufloesung als
  der Monolith-520x320-Referenz. Wir aggregieren pro Szene und wenden die
  IDENTISCHE Normalisierung ``_normalize_motion`` (1-exp(-raw/40)) an; die
  ABSOLUTE Skala kann daher vom Monolith abweichen (Toleranz-Item fuer den
  Paritaets-Test, kein Byte-Match).
- Captions: die ``VlmCaptionStage`` laeuft als Stub, solange kein echtes
  Ollama-Backend verdrahtet ist. Wir schreiben den Text als
  ``ai_caption={"description": text}``; strukturierte ``ai_mood``/``ai_tags``
  bleiben None bis das VLM-Backend steht (kein erfundenes Signal).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np

from services.video_pipeline.stages.base import StageResult

logger = logging.getLogger(__name__)

__all__ = ["DbPersistStage"]


class DbPersistStage:
    stage_id = "db_persist"

    def __init__(
        self,
        *,
        clip_id: int,
        expected_db_url: str | None = None,
    ) -> None:
        """Args:
        clip_id: VideoClip-ID (== Orchestrator ``track_id``) — Ziel der
            Scene-/Embedding-Writes.
        expected_db_url: Projekt-Token vom Pipeline-Start
            (``_current_db_url()``). Wird an ``store_scenes_in_db``
            durchgereicht, damit ein mid-run Projektwechsel NICHT in die
            falsche DB schreibt.
        """
        self.clip_id = int(clip_id)
        self.expected_db_url = expected_db_url

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("DbPersistStage: %s nicht lesbar: %s", path.name, exc)
            return default

    @staticmethod
    def _scene_motion(
        motion_rows: list[dict[str, Any]], start_s: float, end_s: float,
    ) -> float:
        """Aggregiert die Frame-Paar-Magnituden einer Szene und normalisiert
        mit der Monolith-Formel (identisch zu Scene.energy im Legacy-Pfad)."""
        from services.video_analysis_service import _normalize_motion

        mags = [
            float(r.get("mean_magnitude", 0.0))
            for r in motion_rows
            if start_s <= float(r.get("time_a_s", -1.0)) < end_s
        ]
        if not mags:
            return 0.0
        return _normalize_motion(float(np.mean(mags)))

    def run(
        self,
        source_path: Path,
        storage_dir: Path,
        *,
        cancel_token: Any | None = None,
    ) -> StageResult:
        from services.video_analysis_service import (
            SceneInfo,
            store_embeddings,
            store_scenes_in_db,
        )

        source_path = Path(source_path)
        storage_dir = Path(storage_dir)
        t0 = time.monotonic()

        scenes_data = self._load_json(storage_dir / "scenes.json", [])
        if not scenes_data:
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0,
                error="scenes.json fehlt oder leer — nichts zu persistieren.",
            )
        keyframes = self._load_json(storage_dir / "keyframes.json", [])
        captions = self._load_json(storage_dir / "captions.json", [])
        motion_rows = self._load_json(storage_dir / "motion.json", [])

        # Embedding-Zeilen sind in keyframes.json-Reihenfolge gestapelt.
        embeddings = None
        emb_path = storage_dir / "embeddings.npy"
        if emb_path.exists():
            try:
                embeddings = np.load(emb_path)
            except (OSError, ValueError) as exc:
                logger.warning("DbPersistStage: embeddings.npy nicht ladbar: %s", exc)

        # scene_idx -> Embedding-Row (erste Keyframe-Zeile je Szene).
        emb_by_scene: dict[int, np.ndarray] = {}
        cap_by_scene: dict[int, str] = {}
        for row_i, kf in enumerate(keyframes):
            sidx = int(kf.get("scene_idx", row_i))
            if (embeddings is not None and row_i < embeddings.shape[0]
                    and sidx not in emb_by_scene):
                emb_by_scene[sidx] = embeddings[row_i]
        for cap in captions:
            sidx = int(cap.get("scene_idx", -1))
            txt = str(cap.get("text", "")).strip()
            if sidx >= 0 and txt and sidx not in cap_by_scene:
                cap_by_scene[sidx] = txt

        scene_infos: list[SceneInfo] = []
        for s in scenes_data:
            idx = int(s.get("index", len(scene_infos)))
            start_s = float(s.get("start_s", 0.0))
            end_s = float(s.get("end_s", start_s))
            emb = emb_by_scene.get(idx)
            cap_text = cap_by_scene.get(idx)
            scene_infos.append(SceneInfo(
                index=idx,
                start_time=start_s,
                end_time=end_s,
                motion_score=self._scene_motion(motion_rows, start_s, end_s),
                embedding=emb,
                # Stub-VLM: nur description; mood/tags bleiben None (kein
                # erfundenes Signal, siehe Modul-Docstring).
                ai_caption={"description": cap_text} if cap_text else None,
                ai_mood=None,
                ai_tags=None,
            ))

        # 1) Scene-Tabelle (mit Projekt-Token-/FK-Guards des Monolith).
        try:
            scenes_ok = store_scenes_in_db(
                self.clip_id, scene_infos,
                expected_db_url=self.expected_db_url,
            )
        except Exception as exc:  # Writer wirft nur bei echtem DB-Fehler
            logger.exception("DbPersistStage: store_scenes_in_db fehlgeschlagen")
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0,
                error=f"store_scenes_in_db: {type(exc).__name__}: {exc}",
            )
        if not scenes_ok:
            # Skip (Projekt-Mismatch / Clip fehlt) — kein Embedding-Write,
            # sonst haengen Embeddings ohne Scenes in VectorDB.
            return StageResult(
                stage_id=self.stage_id, status="failed",
                duration_s=time.monotonic() - t0,
                error="store_scenes_in_db skip (Projekt-Mismatch oder Clip "
                      "fehlt in aktiver DB) — Embeddings NICHT geschrieben.",
            )

        # 2) VectorDB (nur Szenen mit Embedding).
        embeds_written = 0
        try:
            embeds_written = store_embeddings(
                str(source_path), scene_infos, self.clip_id,
            )
        except Exception as exc:
            logger.exception("DbPersistStage: store_embeddings fehlgeschlagen")
            return StageResult(
                stage_id=self.stage_id, status="partial",
                duration_s=time.monotonic() - t0,
                metrics={"scenes_written": len(scene_infos), "embeddings_written": 0},
                error=f"store_embeddings: {type(exc).__name__}: {exc}",
            )

        return StageResult(
            stage_id=self.stage_id, status="done",
            duration_s=time.monotonic() - t0,
            metrics={
                "scenes_written": len(scene_infos),
                "embeddings_written": embeds_written,
                "captions_available": len(cap_by_scene),
                "motion_rows": len(motion_rows),
            },
        )
