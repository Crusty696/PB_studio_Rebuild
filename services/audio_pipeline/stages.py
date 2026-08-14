"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T1.3 + T2.1/T2.2: Pipeline-Stages (Stem-Generierung + Beat-Grid + 6 DSP).

Service-Mapping siehe A-8 + RED-Pre-Check-Updates aus T1.0-Migration:
- StemGenStage          StemSeparator.separate_to (T2.1)
- BeatGridStage         BeatAnalysisService.analyze_and_store(trigger_onset=False)
- OnsetStage            OnsetRhythmService.analyze_and_store(track_id)
                        (drums-Pfad aus DB-Field stem_drums_path; T2.1 schreibt)
- KeyStage              KeyDetectionService.detect_key(original, bass_path, other_path)
- StructureStage        StructureDetectionService.detect(original, stem_paths=dict)
- LUFSStage             LUFSService.analyze(original)
- SpectralStage         SpectralAnalysisService.analyze(original)
- AVPacingStage         AVPacingService.analyze(original)
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from services.audio_pipeline.context import PipelineContext

logger = logging.getLogger(__name__)


# Lazy imports zum Stage-Modul-Load-Time vermeiden.
# T2.1: GPU_EXECUTION_LOCK + torch + nullpool_session werden zur Test-Zeit mockbar
# wenn als Modul-Level-Symbol importiert.
try:
    from services.model_manager import GPU_EXECUTION_LOCK
except ImportError:
    import threading as _t
    GPU_EXECUTION_LOCK = _t.RLock()

try:
    from database import nullpool_session
except ImportError:
    nullpool_session = None

try:
    import torch
except ImportError:
    torch = None


class StageInputMissingError(RuntimeError):
    """A-1 / fixt R-01: Stage benoetigt Stem das fehlt -> Pipeline-Stop."""


def _raise_if_cancelled(context: PipelineContext, stage_name: str) -> None:
    if context.should_stop and context.should_stop():
        raise RuntimeError(f"Audio-V2 Stage '{stage_name}' abgebrochen (User-Cancel)")


@contextmanager
def _audio_gpu_execution_lease(reason: str):
    wait_start = time.perf_counter()
    logger.info("B-597 GPU_EXECUTION_LOCK wait reason=%s", reason)
    with GPU_EXECUTION_LOCK:
        acquired_at = time.perf_counter()
        logger.info(
            "B-597 GPU_EXECUTION_LOCK acquired reason=%s wait_ms=%.1f",
            reason,
            (acquired_at - wait_start) * 1000.0,
        )
        try:
            yield
        finally:
            logger.info(
                "B-597 GPU_EXECUTION_LOCK released reason=%s held_ms=%.1f",
                reason,
                (time.perf_counter() - acquired_at) * 1000.0,
            )


class Stage:
    """Abstract base. Subclass muss .name setzen und .run(context) implementieren."""
    name: str = "abstract"

    def run(self, context: PipelineContext) -> None:
        raise NotImplementedError("Stage.run must be implemented by subclass")

    def rehydrate(self, context: PipelineContext) -> None:
        """Resume-Hook: wird vom Orchestrator aufgerufen, wenn die Stage per
        Checkpoint uebersprungen wird (bereits erfolgreich gelaufen). Default no-op.

        OTK-018: StemGenStage ueberschreibt dies, um ``context.stem_paths`` aus
        Cache/DB zu rehydrieren — sonst stehen nachfolgende stem-geroutete Stages
        (Onset/Key/Structure) nach einem Resume ohne Stem-Pfade da und brechen ab.
        """
        return None


def _require_stems(context: PipelineContext, names: tuple[str, ...], stage_name: str) -> None:
    missing = [n for n in names if n not in context.stem_paths]
    if missing:
        raise StageInputMissingError(
            f"{stage_name}: erforderliche Stems fehlen in Context: {missing}"
        )


def _is_fallback_result(result: Any) -> bool:
    """B-066-Muster fuer die V2-Pipeline. Vorbild: ``workers/audio_analysis.py``
    ``BaseAnalysisWorker._is_fallback_result`` (dort Zeile ~108).

    Die Heuristik ist bewusst 1:1 vom V1-Worker uebernommen (kein neues
    Konzept), damit V1 und V2 dieselben Rate-Ergebnisse erkennen:

    1. ``is_fallback is True``           — explizites Flag (LUFSResult,
                                           SpectralResult).
    2. ``method == "fallback"``          — KeyResult-Pattern.
    3. ``confidence == 0.0`` und
       ``description`` beginnt mit
       "Klassifikation nicht moeglich"   — ClassifyResult-Pattern.

    Die Heuristik ist nicht beweisbar vollstaendig: ein Service, der weder
    Flag noch ``method``/``description``-Marker setzt, wird hier NICHT
    erkannt (gleiche Luecke wie in V1).

    Kein Import aus ``workers.audio_analysis``, weil das PySide6 in die
    Pipeline ziehen wuerde — die Pipeline-Stages sind bewusst Qt-frei.
    """
    if getattr(result, "is_fallback", False) is True:
        return True
    method = getattr(result, "method", None)
    if isinstance(method, str) and method.lower() == "fallback":
        return True
    confidence = getattr(result, "confidence", None)
    description = getattr(result, "description", "")
    if (
        confidence == 0.0
        and isinstance(description, str)
        and description.lower().startswith("klassifikation nicht moeglich")
    ):
        return True
    return False


def _fallback_reason(result: Any) -> str:
    """Lesbarer Grund fuers Logging — identisch zu V1 (``workers/audio_analysis.py``)."""
    for attr in ("fallback_reason", "description", "method"):
        v = getattr(result, attr, None)
        if isinstance(v, str) and v.strip():
            return v
    return "kein Grund verfuegbar"


def _guard_no_fallback_persist(
    result: Any, stage_name: str, context: Any = None
) -> bool:
    """Blockt das Persistieren von Fallback-/Rate-Ergebnissen (B-066 fuer V2).

    V1 macht das in ``BaseAnalysisWorker.run`` (workers/audio_analysis.py:108
    ff.): erkanntes Fallback-Result -> ``RuntimeError`` -> ``mark_error``, die
    DB-Spalten bleiben ``None``. V2 hatte diesen Schutz nicht, deshalb landeten
    Key ``Am``/``8A`` mit confidence 0.0, Spektral-Baender mit lauter 0.0 und
    LUFS ``-14.0`` als scheinbar gueltige Messwerte in ``audio_tracks``.

    Unterschied zu V1 — bewusst: V1 hat pro Analyse-Schritt einen eigenen
    Worker, dort beendet die Exception nur diesen einen Schritt. V2 ist eine
    strikt sequentielle Pipeline mit fail-fast (Orchestrator A-1); eine
    Exception hier wuerde alle FOLGENDEN Stages mitreissen — ein
    LUFS-Fallback in Stage 6 hiesse: kein Classify, keine Waveform, kein
    AV-Pacing. Das waere ein Rueckschritt gegenueber dem alten Verhalten.

    Deshalb: nicht werfen. Die Stage persistiert das Rate-Ergebnis nicht,
    vermerkt den Grund im Context und laeuft weiter. Der
    ``AudioPipelineV2Worker`` liest den Vermerk aus dem Stage-Payload und
    setzt ``mark_degraded`` statt ``mark_done`` — der Schritt ist damit in
    der UI sichtbar geraten statt faelschlich gruen.

    Returns:
        ``True`` wenn persistiert werden darf, ``False`` bei erkanntem
        Fallback.
    """
    if not _is_fallback_result(result):
        return True
    reason = _fallback_reason(result)
    logger.error(
        "B-066/V2 %s: Fallback-Result erkannt — NICHT persistiert (%s)",
        stage_name, reason,
    )
    if context is not None:
        try:
            context.mark_degraded(stage_name, reason)
        except AttributeError:  # aeltere/gemockte Contexte in Tests
            logger.debug(
                "Context ohne mark_degraded — Stage '%s' bleibt ungemarkt",
                stage_name,
            )
    return False


def _persist_to_track(track_id: int, fields: dict) -> None:
    """OTK-018: schreibt berechnete Analyse-Felder an den AudioTrack.

    Die V2-Stages rufen die reinen ``detect()``/``analyze()``-Services (kein
    DB-Write); ohne dieses Persistieren landen Key/LUFS/Spectral nicht in der DB
    (analog zu den klassischen Worker-``_save_to_db``). None-Werte werden
    uebersprungen. DB nicht verfuegbar (headless) -> no-op.
    """
    fields = {k: v for k, v in fields.items() if v is not None}
    if nullpool_session is None or not fields:
        return
    try:
        from database import AudioTrack
    except ImportError:
        return
    try:
        with nullpool_session() as sess:
            # team-sweep 2026-07-15: PB-Studio-Norm — nicht in soft-deleted Track schreiben
            track = sess.query(AudioTrack).filter(AudioTrack.id == track_id, AudioTrack.deleted_at.is_(None)).first()
            if track is None:
                return
            for key, value in fields.items():
                setattr(track, key, value)
            sess.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("Persist track=%s fehlgeschlagen: %s", track_id, e)


# AV-Pacing wird auf AV_PACING_HOP_SEC (0.1s) gerechnet, aber downgesampelt
# gespeichert: jeder 4. Frame -> 0.4s-Raster. Vorbild: onset_rhythm_service.py
# :213 (curve[::4], "downsampled fuer DB-Storage"). Bei einem 60-min-Track
# schrumpft das von ~36.000 auf ~9.000 Werte je Kurve.
_AV_PACING_DECIMATE = 4


def _decimate(seq, step: int = _AV_PACING_DECIMATE, ndigits: int = 4) -> list:
    """Jeden ``step``-ten Wert behalten und runden (DB-Storage-Groesse).

    Defensiv: unerwartete/nicht-iterierbare Werte ergeben eine leere Liste
    statt einer Exception — das Persistieren darf die Analyse-Stage nie
    reissen (der Aufrufer behandelt [] als "nichts zu speichern").
    """
    if not seq:
        return []
    try:
        return [round(float(v), ndigits) for v in list(seq)[::step]]
    except (TypeError, ValueError):
        return []


def _persist_av_pacing(track_id: int, result) -> int:
    """Schreibt die AV-Pacing-Kurven downgesampelt in ``av_pacing_data``.

    Eigene 1:1-Tabelle statt JSON-Spalten auf AudioTrack — Begruendung siehe
    ``database/models.py`` AVPacingData-Docstring (Blob/B-090). Upsert, weil
    ``audio_track_id`` unique ist und eine Re-Analyse denselben Track trifft.
    DB nicht verfuegbar (headless) -> no-op, wie ``_persist_to_track``.

    Returns:
        Anzahl persistierter Samples (0 wenn nichts geschrieben wurde).
    """
    if nullpool_session is None or result is None:
        return 0
    times = _decimate(getattr(result, "times_sec", None))
    if not times:
        return 0
    try:
        from database import AudioTrack, AVPacingData
    except ImportError:
        return 0

    centroid = _decimate(getattr(result, "spectral_centroid", None))
    flux = _decimate(getattr(result, "spectral_flux", None))
    width = _decimate(getattr(result, "stereo_width", None))
    perc = _decimate(getattr(result, "percussive_ratio", None))
    # RMS in voller Aufloesung (step=1) — siehe row.rms_curve unten.
    rms = _decimate(getattr(result, "rms", None), step=1)

    # Die Kurven muessen gleich lang sein — der Consumer indiziert alle vier
    # ueber denselben Zeitindex. Auf die kuerzeste kuerzen statt zu raten.
    n = min(len(times), len(centroid), len(flux), len(width), len(perc))
    if n <= 0:
        return 0
    times, centroid, flux, width, perc = (
        times[:n], centroid[:n], flux[:n], width[:n], perc[:n],
    )
    hop = float(getattr(result, "hop_sec", 0.1) or 0.1) * _AV_PACING_DECIMATE

    try:
        with nullpool_session() as sess:
            # PB-Studio-Norm: nicht in soft-deleted Track schreiben.
            track = sess.query(AudioTrack).filter(
                AudioTrack.id == track_id, AudioTrack.deleted_at.is_(None),
            ).first()
            if track is None:
                return 0
            row = sess.query(AVPacingData).filter(
                AVPacingData.audio_track_id == track_id,
            ).first()
            if row is None:
                row = AVPacingData(audio_track_id=track_id)
                sess.add(row)
            row.hop_sec = hop
            row.num_samples = n
            row.duration = float(times[-1]) if times else 0.0
            row.times_sec = times
            row.spectral_centroid = centroid
            row.spectral_flux = flux
            row.stereo_width = width
            row.percussive_ratio = perc
            # RMS bewusst NICHT decimiert: der Energy-Match in
            # services/pacing/audio_video_curves arbeitet auf einem 100ms-Grid
            # (DEFAULT_BIN_MS) — ein 0.4s-Raster passt dort nicht. Eigenes
            # Hop-Feld, weil es sich vom Raster der vier Kurven unterscheidet.
            row.rms_curve = rms
            row.rms_hop_sec = float(
                getattr(result, "hop_sec", 0.1) or 0.1
            ) if rms else None
            sess.commit()
            return n
    except Exception as e:  # noqa: BLE001
        logger.warning("Persist av_pacing track=%s fehlgeschlagen: %s", track_id, e)
        return 0


_DEMUCS_VERSION = "htdemucs"
_TARGET_WAV_SUBTYPE = "PCM_24"


class StemGenStage(Stage):
    """T2.1 + T3.2: Demucs-First-Stage mit GPU-Lock + PCM_24 + track-id-Layout
    + DB-Write + Reuse via Hash-Cache.

    - T3.2 Pre-Check: wenn Cache-Meta + 4 WAVs + all-hash-match + Subtype OK
      -> skip Demucs, set context.stem_paths aus Existing.
    - Sonst: Acquires GPU_EXECUTION_LOCK, ruft StemSeparator.separate_to,
      schreibt PCM_24 nach storage/stems/<track_id>/, setzt DB stem_*_path,
      schreibt Cache-Meta mit Stem-Hashes.
    """
    name = "stem_gen"

    _stems_root: Path | None = None  # test-override

    def __init__(self, separator_cls: Any = None):
        self._separator_cls = separator_cls

    def _resolve_stems_dir(self, track_id: int) -> Path:
        if self._stems_root is not None:
            root = self._stems_root
        else:
            import database.session as db_session

            root = Path(db_session.APP_ROOT) / "storage" / "stems"
        return root / str(track_id)

    def _try_reuse(self, context: PipelineContext) -> dict[str, str] | None:
        """T3.2 Pre-Check. Returns Stem-Pfad-Dict bei Reuse, sonst None."""
        from services.audio_pipeline import stem_cache

        meta = stem_cache.load_cache_meta(context.track_id)
        if not meta:
            return self._try_db_stem_references(context.track_id)
        # Subtype-Check (Q-C Migration)
        if meta.get("wav_subtype") != _TARGET_WAV_SUBTYPE:
            return self._try_db_stem_references(context.track_id)
        # Demucs-Version-Check
        if meta.get("demucs_version") != _DEMUCS_VERSION:
            return self._try_db_stem_references(context.track_id)
        # Original-Hash-Check
        try:
            orig_hash = stem_cache.compute_audio_hash(context.original_path)
        except OSError:
            return self._try_db_stem_references(context.track_id)
        if meta.get("original_hash") != orig_hash:
            # B-702: Hash-Mismatch = der Audio-Inhalt hat sich GEAENDERT. Die
            # DB-Referenzen zeigen dann genauso auf Stems des alten Inhalts —
            # ein Fallback dorthin wuerde die Invalidierung aushebeln. Kein
            # Reuse: Demucs muss neu laufen.
            return None
        # 4 WAVs existieren + Hash-Match (fixt R-07 partial-Crash)
        stems_dir = self._resolve_stems_dir(context.track_id)
        cached_stem_hashes = meta.get("stem_hashes", {})
        result_paths: dict[str, str] = {}
        for name in ("drums", "bass", "vocals", "other"):
            p = stems_dir / f"{name}.wav"
            if not p.exists():
                return self._try_db_stem_references(context.track_id)
            cached = cached_stem_hashes.get(name)
            actual = stem_cache.compute_stem_wav_hash(str(p))
            if cached != actual:
                return self._try_db_stem_references(context.track_id)
            result_paths[name] = str(p.resolve())
        return result_paths

    @staticmethod
    def _try_db_stem_references(track_id: int) -> dict[str, str] | None:
        if nullpool_session is None:
            return None
        try:
            from database import AudioTrack
        except ImportError:
            return None
        try:
            with nullpool_session() as sess:
                track = sess.query(AudioTrack).filter(AudioTrack.id == track_id).first()
                if track is None:
                    return None
                paths = {
                    "drums": getattr(track, "stem_drums_path", None),
                    "bass": getattr(track, "stem_bass_path", None),
                    "vocals": getattr(track, "stem_vocals_path", None),
                    "other": getattr(track, "stem_other_path", None),
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("StemGenStage DB-Reuse track=%s fehlgeschlagen: %s", track_id, e)
            return None
        # B-822: gespeicherte Pfade ans aktive Projekt binden. Nach einer
        # Projektkopie zeigen sie sonst auf den alten Ort und der Reuse
        # griffe an den Stems eines fremden Projekts vorbei.
        from services.stem_router import resolve_stem_paths
        resolved = resolve_stem_paths(paths)
        if len(resolved) != len(paths):
            return None
        return {name: str(Path(path).resolve()) for name, path in resolved.items()}

    def _persist_cache_meta(self, context: PipelineContext, result: dict[str, str]) -> None:
        from services.audio_pipeline import stem_cache
        try:
            orig_hash = stem_cache.compute_audio_hash(context.original_path)
            stem_hashes = {n: stem_cache.compute_stem_wav_hash(p) for n, p in result.items()}
        except OSError:
            return
        meta = {
            "version": 1,
            "original_hash": orig_hash,
            "stem_hashes": stem_hashes,
            "demucs_version": _DEMUCS_VERSION,
            "wav_subtype": _TARGET_WAV_SUBTYPE,
            "stages_done": ["stem_gen"],
        }
        stem_cache.save_cache_meta(context.track_id, meta)

    def run(self, context: PipelineContext) -> None:
        # T3.2 Reuse-Check
        reuse = self._try_reuse(context)
        if reuse is not None:
            context.stem_paths.update(reuse)
            context.set_result(self.name, {"stem_paths": dict(reuse), "reused": True})
            self._record_stem_provenance(context, reuse)
            return

        if self._separator_cls is None:
            from services.ai_audio_service import StemSeparator
            self._separator_cls = StemSeparator

        out_dir = str(self._resolve_stems_dir(context.track_id))

        progress_cb = None
        if context.on_progress:
            def _progress_wrapper(pct: int, msg: str) -> None:
                context.on_progress(pct, f"Stems: {msg}")
            progress_cb = _progress_wrapper

        # T2.1: GPU-Lock + Demucs + VRAM-Cleanup
        _raise_if_cancelled(context, "stem_gen")
        with _audio_gpu_execution_lease("audio_v2.stem_gen"):
            try:
                separator = self._separator_cls()
                if progress_cb:
                    result = separator.separate_to(
                        file_path=context.original_path,
                        out_dir=out_dir,
                        subtype=_TARGET_WAV_SUBTYPE,
                        model="htdemucs",
                        progress_cb=progress_cb,
                        should_stop=context.should_stop,
                    )
                else:
                    result = separator.separate_to(
                        file_path=context.original_path,
                        out_dir=out_dir,
                        subtype=_TARGET_WAV_SUBTYPE,
                        should_stop=context.should_stop,
                    )
            finally:
                if torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()
        _raise_if_cancelled(context, "stem_gen")

        # Context + DB-Write nur bei Erfolg.
        context.stem_paths.update(result)
        context.set_result(self.name, {"stem_paths": dict(result), "reused": False})

        # T2.1 / R-09 Vorbereitung: Stem-Pfade in DB schreiben
        self._persist_stem_paths_to_db(context.track_id, result)

        # T3.2: Cache-Meta + Stem-Hashes persistieren
        self._persist_cache_meta(context, result)
        self._record_stem_provenance(context, result)

    @staticmethod
    def _persist_stem_paths_to_db(track_id: int, stem_paths: dict[str, str]) -> None:
        if nullpool_session is None:
            return  # DB nicht verfuegbar (z.B. headless-Test)
        try:
            from database import AudioTrack
        except ImportError:
            return
        # B-824: projektrelativ ablegen. Ein absoluter Pfad ueberlebt keine
        # Projektkopie und keinen Laufwerkswechsel; der relative Wert gilt in
        # jeder Kopie unveraendert.
        from services.stem_router import to_project_relative
        with nullpool_session() as sess:
            track = sess.query(AudioTrack).filter(AudioTrack.id == track_id).first()
            if track is None:
                return
            if "drums" in stem_paths:
                track.stem_drums_path = to_project_relative(stem_paths["drums"])
            if "bass" in stem_paths:
                track.stem_bass_path = to_project_relative(stem_paths["bass"])
            if "vocals" in stem_paths:
                track.stem_vocals_path = to_project_relative(stem_paths["vocals"])
            if "other" in stem_paths:
                track.stem_other_path = to_project_relative(stem_paths["other"])
            sess.commit()

    @staticmethod
    def _record_stem_provenance(context: PipelineContext, stem_paths: dict[str, str]) -> None:
        """OTK-021/40: V2 stem stage writes analysis_jobs/artifacts."""
        if nullpool_session is None:
            return
        try:
            from database import AudioTrack
            from services.storage_provenance.caller_migration import ProvenanceRecorder
        except ImportError:
            return
        try:
            with nullpool_session() as sess:
                track = sess.query(AudioTrack).filter(AudioTrack.id == context.track_id).first()
                if track is None or not getattr(track, "project_id", None):
                    return
                source_path = getattr(track, "file_path", None) or context.original_path
                if not source_path:
                    return
                ProvenanceRecorder(sess).record_done(
                    project_id=track.project_id,
                    source_path=source_path,
                    media_type="audio",
                    step_id="audio.v2.stems",
                    params={
                        "stage": StemGenStage.name,
                        "demucs_version": _DEMUCS_VERSION,
                        "wav_subtype": _TARGET_WAV_SUBTYPE,
                    },
                    artifacts={
                        "vocals_stem": stem_paths.get("vocals"),
                        "drums_stem": stem_paths.get("drums"),
                        "bass_stem": stem_paths.get("bass"),
                        "other_stem": stem_paths.get("other"),
                    },
                    produced_by_model="Demucs",
                    produced_by_model_version=_DEMUCS_VERSION,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("StemGenStage provenance track=%s fehlgeschlagen: %s", context.track_id, e)


    def rehydrate(self, context: PipelineContext) -> None:
        """Resume: stem_gen war schon erfolgreich -> Stem-Pfade in den frischen
        Context zurueckholen, damit Onset/Key/Structure nicht an fehlenden Stems
        scheitern. Erst Cache-Reuse (Hash-validiert), sonst DB-Fallback."""
        reuse = self._try_reuse(context)
        if reuse is not None:
            context.stem_paths.update(reuse)
            return
        # DB-Fallback: persistierte stem_*_path-Felder.
        if nullpool_session is None:
            return
        try:
            from database import AudioTrack
        except ImportError:
            return
        mapping: dict[str, str | None] = {}
        try:
            with nullpool_session() as sess:
                track = sess.query(AudioTrack).filter(AudioTrack.id == context.track_id).first()
                if track is None:
                    return
                mapping = {
                    "drums": getattr(track, "stem_drums_path", None),
                    "bass": getattr(track, "stem_bass_path", None),
                    "vocals": getattr(track, "stem_vocals_path", None),
                    "other": getattr(track, "stem_other_path", None),
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("StemGenStage.rehydrate DB-Fallback fehlgeschlagen: %s", e)
            return
        # B-822: Pfad ans aktive Projekt binden, wo es dort eine Entsprechung
        # gibt. Laesst er sich nicht aufloesen, bleibt der gespeicherte Wert
        # stehen — die missing-Erkennung unten braucht ihn und meldet den
        # Schritt dann korrekt als degradiert statt still auf einen fremden
        # Ordner auszuweichen.
        from services.stem_router import resolve_stem_path
        mapping = {
            name: (resolve_stem_path(path) or path)
            for name, path in mapping.items()
        }
        for name, path in mapping.items():
            if path:
                context.stem_paths[name] = path
        # Die Pfade werden bewusst auch dann gesetzt, wenn die Dateien fehlen:
        # sonst wirft _require_stems StageInputMissingError und der Orchestrator
        # bricht fail-fast ab — es gaebe dann gar keine Key/Structure/LUFS-Werte
        # mehr (OTK-018, tests/test_services/test_pipeline_resume_after_crash.py).
        # Fehlt die Datei aber, laeuft z.B. KeyStage ueber den stem-losen
        # Legacy-Pfad (key_detection_service.py:235 faengt den Mix-Fehler). Das
        # Ergebnis ist echt, das Stem-Routing fand aber nicht statt — deshalb
        # nicht gruen melden, sondern wie bei _guard_no_fallback_persist als
        # degradiert vermerken.
        missing = sorted(
            name for name, path in mapping.items()
            if path and not Path(path).is_file()
        )
        if missing:
            reason = (
                "Stem-Dateien aus der DB fehlen auf der Platte: "
                + ", ".join(missing)
                + " — Analyse laeuft ohne Stem-Routing weiter"
            )
            logger.error("StemGenStage.rehydrate track=%s: %s", context.track_id, reason)
            try:
                context.mark_degraded(self.name, reason)
            except AttributeError:  # aeltere/gemockte Contexte in Tests
                logger.debug("Context ohne mark_degraded — stem_gen bleibt ungemarkt")


class BeatGridStage(Stage):
    """A-7 + T2.2: ruft BeatAnalysisService.analyze_and_store(trigger_onset=False).

    GPU-Lock pflichtig (beat_this nutzt CUDA). Sequenz garantiert NACH StemGen-Release
    (Orchestrator-Reihenfolge); kein Race mit Demucs.
    Onset wird durch OnsetStage separat ausgefuehrt (drums-Stem-Routing).
    """
    name = "beat_grid"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        if self._service_cls is None:
            from services.beat_analysis_service import BeatAnalysisService
            self._service_cls = BeatAnalysisService

        _raise_if_cancelled(context, "beat_grid")
        with _audio_gpu_execution_lease("audio_v2.beat_grid"):
            try:
                svc = self._service_cls()
                # B-703: Cancel-Callback in den Chunk-Loop reichen — Abbruch
                # wirkt jetzt pro Chunk statt erst an der Stage-Grenze.
                result = svc.analyze_and_store(
                    context.track_id, trigger_onset=False,
                    should_stop=context.should_stop,
                )
            finally:
                if torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()
        _raise_if_cancelled(context, "beat_grid")

        context.set_result(self.name, {"bpm": (result or {}).get("bpm")})


class OnsetStage(Stage):
    """C-01: Service zieht drums-Pfad aus DB. Pre-Condition: T2.1 schrieb stem_drums_path."""
    name = "onset"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _raise_if_cancelled(context, "onset")
        _require_stems(context, ("drums",), self.name)
        if self._service_cls is None:
            from services.onset_rhythm_service import OnsetRhythmService
            self._service_cls = OnsetRhythmService
        svc = self._service_cls()
        result = svc.analyze_and_store(context.track_id)
        _raise_if_cancelled(context, "onset")
        context.set_result(self.name, {"ok": result is not None})


class KeyStage(Stage):
    """C-02: detect_key(original, bass_path=..., other_path=...). Service mischt intern."""
    name = "key"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _require_stems(context, ("bass", "other"), self.name)
        if self._service_cls is None:
            from services.key_detection_service import KeyDetectionService
            self._service_cls = KeyDetectionService
        svc = self._service_cls()
        result = svc.detect_key(
            context.original_path,
            bass_path=context.stem_paths["bass"],
            other_path=context.stem_paths["other"],
        )
        # result = KeyResult dataclass. OTK-018: an AudioTrack persistieren.
        # B-066/V2: Fallback ("Am"/"8A", confidence 0.0, method="fallback")
        # darf NICHT als Messwert in die DB.
        if _guard_no_fallback_persist(result, self.name, context):
            conf = getattr(result, "confidence", None)
            if conf is not None:
                conf = max(0.0, min(1.0, float(conf)))
            _persist_to_track(context.track_id, {
                "key": getattr(result, "key", None),
                "key_confidence": conf,
                "key_modulation_data": getattr(result, "modulation_segments", None) or None,
                "harmonic_tension_curve": getattr(result, "harmonic_tension_curve", None) or None,
            })
        context.set_result(self.name, {
            "key": getattr(result, "key", None),
            "camelot": getattr(result, "camelot", None),
            "confidence": getattr(result, "confidence", None),
        })


class StructureStage(Stage):
    """C-03 fuer Structure: dict-arg ohne 'other'-Stem."""
    name = "structure"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _require_stems(context, ("bass", "drums", "vocals"), self.name)
        if self._service_cls is None:
            from services.structure_detection_service import StructureDetectionService
            self._service_cls = StructureDetectionService
        svc = self._service_cls()
        filtered = {k: context.stem_paths[k] for k in ("bass", "drums", "vocals")}
        bpm = context.results.get("beat_grid", {}).get("bpm")
        result = svc.detect(context.original_path, bpm=bpm, stem_paths=filtered)
        # OTK-018: Segmente in structure_segments persistieren (Service-Methode).
        try:
            svc.save_to_db(context.track_id, result)
        except Exception as e:  # noqa: BLE001
            logger.warning("StructureStage save_to_db track=%s fehlgeschlagen: %s",
                           context.track_id, e)
        context.set_result(self.name, {"segments_count": len(getattr(result, "segments", []) or [])})


class LUFSStage(Stage):
    name = "lufs"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _raise_if_cancelled(context, "lufs")
        if self._service_cls is None:
            from services.lufs_service import LUFSService
            self._service_cls = LUFSService
        svc = self._service_cls()

        progress_cb = None
        if context.on_progress:
            def _progress_wrapper(pct: int, msg: str) -> None:
                context.on_progress(pct, f"LUFS: {msg}")
            progress_cb = _progress_wrapper

        if progress_cb:
            result = svc.analyze(context.original_path, progress_cb=progress_cb)
        else:
            result = svc.analyze(context.original_path)
        _raise_if_cancelled(context, "lufs")
        # OTK-018: LUFS an AudioTrack persistieren (Worker-konform: result.integrated).
        # B-066/V2: LUFSService setzt is_fallback bei -14.0-Default korrekt —
        # hier wird es jetzt auch ausgewertet statt blind zu persistieren.
        integrated = getattr(result, "integrated", None)
        if integrated is None:
            integrated = getattr(result, "integrated_lufs", None)
        if _guard_no_fallback_persist(result, self.name, context):
            _persist_to_track(context.track_id, {"lufs": integrated})
        context.set_result(self.name, {
            "integrated_lufs": integrated,
            "true_peak": getattr(result, "true_peak", None),
        })


class SpectralStage(Stage):
    name = "spectral"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _raise_if_cancelled(context, "spectral")
        if self._service_cls is None:
            from services.spectral_analysis_service import SpectralAnalysisService
            self._service_cls = SpectralAnalysisService
        svc = self._service_cls()
        bpm = context.results.get("beat_grid", {}).get("bpm")
        result = svc.analyze(context.original_path, bpm=bpm)
        _raise_if_cancelled(context, "spectral")
        # OTK-018: Spektral-Baender an AudioTrack persistieren (Worker-konform).
        # B-066/V2: 8 Baender mit energy 0.0 aus dem Fehlerpfad sind ein
        # Rate-Ergebnis (SpectralResult.is_fallback) — nicht persistieren.
        if _guard_no_fallback_persist(result, self.name, context):
            try:
                bands_json = svc.get_bands_json(result)
            except Exception:  # noqa: BLE001
                bands_json = None
            _persist_to_track(context.track_id, {"spectral_bands": bands_json})
        context.set_result(self.name, {
            "dominant_band": getattr(result, "dominant_band", None),
            "centroid_mean": getattr(result, "spectral_centroid_mean", None),
        })


class AVPacingStage(Stage):
    name = "av_pacing"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _raise_if_cancelled(context, "av_pacing")
        if self._service_cls is None:
            from services.av_pacing_service import AVPacingService
            self._service_cls = AVPacingService
        svc = self._service_cls()
        # AVPacingService.analyze prueft should_stop pro Stream-Chunk
        # (av_pacing_service.py:120). Ohne Durchreichen greift der Abbruch erst
        # an der Stage-Grenze — bei einem langen Mix laeuft HPSS danach noch
        # minutenlang weiter und die Batch-Restliste steht. Analog zu
        # StemGenStage/BeatGridStage, die should_stop bereits durchreichen.
        # Verzweigt wie der progress_cb-Pfad in StemGenStage: ohne Cancel-
        # Callback bleibt der Aufruf unveraendert.
        if context.should_stop:
            result = svc.analyze(context.original_path, should_stop=context.should_stop)
        else:
            result = svc.analyze(context.original_path)
        _raise_if_cancelled(context, "av_pacing")
        # Frueher wurde hier nur len(times_sec) behalten und das Ergebnis
        # verworfen — die HPSS-Rechnung lief also fuer nichts. Jetzt werden die
        # Kurven downgesampelt in av_pacing_data persistiert und von
        # services/pacing/bridge_mapping.py als AudioContext-Felder gelesen.
        stored = _persist_av_pacing(context.track_id, result)
        context.set_result(self.name, {
            "samples": len(getattr(result, "times_sec", []) or []),
            "stored_samples": stored,
        })


class ClassifyStage(Stage):
    name = "classify"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _raise_if_cancelled(context, "classify")
        if self._service_cls is None:
            from services.audio_classify_service import AudioClassifyService
            self._service_cls = AudioClassifyService
        svc = self._service_cls()
        bpm = context.results.get("beat_grid", {}).get("bpm")
        result = svc.classify(context.original_path, bpm=bpm)
        _raise_if_cancelled(context, "classify")
        # B-066/V2: ClassifyResult-Fallback ("Klassifikation nicht moeglich",
        # confidence 0.0) nicht als Mood/Genre in die DB schreiben.
        if _guard_no_fallback_persist(result, self.name, context):
            _persist_to_track(context.track_id, {
                "mood": result.mood,
                "genre": result.genre,
                "sub_genre": result.sub_genre,
                "is_dj_mix": result.is_dj_mix,
            })
        context.set_result(self.name, {
            "mood": result.mood,
            "genre": result.genre,
            "sub_genre": result.sub_genre,
            "is_dj_mix": result.is_dj_mix,
            "confidence": result.confidence,
        })


class WaveformStage(Stage):
    name = "waveform"

    def __init__(self, service_cls: Any = None):
        self._service_cls = service_cls

    def run(self, context: PipelineContext) -> None:
        _raise_if_cancelled(context, "waveform")
        if self._service_cls is None:
            from services.ai_audio_service import FrequencyAnalyzer
            self._service_cls = FrequencyAnalyzer
        analyzer = self._service_cls()
        result = analyzer.analyze_and_store(context.track_id, progress_cb=context.on_progress)
        _raise_if_cancelled(context, "waveform")
        context.set_result(self.name, {
            "num_samples": result.get("num_samples"),
            "duration": result.get("duration"),
        })


# Plan-Reihenfolge fuer Default-Pipeline.
DEFAULT_STAGE_ORDER: tuple[type, ...] = (
    StemGenStage,
    BeatGridStage,
    OnsetStage,
    KeyStage,
    StructureStage,
    LUFSStage,
    SpectralStage,
    ClassifyStage,
    WaveformStage,
    AVPacingStage,
)


def build_default_stages() -> list[Stage]:
    """Default-Pipeline-Stage-Liste in Plan-Reihenfolge."""
    return [cls() for cls in DEFAULT_STAGE_ORDER]
