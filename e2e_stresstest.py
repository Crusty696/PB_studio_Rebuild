# -*- coding: utf-8 -*-
"""E2E Stresstest — Prüft die gesamte PB Studio Pipeline OHNE GUI.

Simuliert den realen Workflow:
1. DB initialisieren
2. Audio-Datei generieren und ingestieren
3. Video-Datei generieren und ingestieren
4. Audio analysieren (BPM, Beats, Energie)
5. Pacing berechnen (Cut Points)
6. Timeline-Einträge erstellen
7. Export-Pipeline prüfen (Struktur-Check, kein voller FFmpeg-Export)
8. Alle DB-Relationen validieren

Exit Code 0 = Alles OK.
"""

import sys
import os
import json
import tempfile
import logging
import traceback
import time
from pathlib import Path

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("e2e_stresstest")

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        log.info("  PASS: %s %s", name, detail)
    else:
        FAIL += 1
        msg = f"  FAIL: {name} {detail}"
        log.error(msg)
        ERRORS.append(msg)


def section(title: str):
    log.info("=" * 60)
    log.info("  %s", title)
    log.info("=" * 60)


# ══════════════════════════════════════════════════════════════
# Phase 1: Test-Medien generieren
# ══════════════════════════════════════════════════════════════

def create_test_audio(path: str, duration: float = 5.0, sr: int = 44100):
    """Erzeugt eine synthetische WAV-Datei (Sinuston 440Hz)."""
    import numpy as np
    import struct
    import wave

    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # 440 Hz Sinus + leichter Kick-Pattern bei 120 BPM
    beat_interval = 0.5  # 120 BPM
    kick = np.zeros_like(t)
    for beat_time in np.arange(0, duration, beat_interval):
        mask = (t >= beat_time) & (t < beat_time + 0.05)
        kick[mask] = 0.8 * np.sin(2 * np.pi * 60 * (t[mask] - beat_time))

    signal = 0.3 * np.sin(2 * np.pi * 440 * t) + kick
    signal = np.clip(signal, -1.0, 1.0)
    samples = (signal * 32767).astype(np.int16)

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


def create_test_video(path: str, duration: float = 5.0, fps: int = 30,
                      width: int = 320, height: int = 240):
    """Erzeugt eine minimale MP4-Datei mit FFmpeg (Farbbalken)."""
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-v", "quiet",
        path,
    ]
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(cmd, capture_output=True, timeout=30, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg Test-Video fehlgeschlagen: {result.stderr.decode(errors='replace')[:300]}")
    return path


# ══════════════════════════════════════════════════════════════
# Main Test
# ══════════════════════════════════════════════════════════════

def run_stresstest():
    global PASS, FAIL
    start_time = time.time()

    # ── Temp-Verzeichnis für Test-Medien ──
    tmp_dir = tempfile.mkdtemp(prefix="pb_e2e_")
    test_audio = os.path.join(tmp_dir, "test_audio.wav")
    test_video = os.path.join(tmp_dir, "test_video.mp4")

    # ══════════════════════════════════════════════════════════
    section("Phase 1: Test-Medien generieren")
    # ══════════════════════════════════════════════════════════

    try:
        create_test_audio(test_audio, duration=10.0)
        check("Audio-Generierung", os.path.exists(test_audio) and os.path.getsize(test_audio) > 0,
              f"({os.path.getsize(test_audio)} bytes)")
    except Exception as e:
        check("Audio-Generierung", False, str(e))
        log.error(traceback.format_exc())

    try:
        create_test_video(test_video, duration=10.0)
        check("Video-Generierung", os.path.exists(test_video) and os.path.getsize(test_video) > 0,
              f"({os.path.getsize(test_video)} bytes)")
    except Exception as e:
        check("Video-Generierung", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 2: Datenbank initialisieren")
    # ══════════════════════════════════════════════════════════

    try:
        from database import init_db, engine, Base, AudioTrack, VideoClip, Project, Beatgrid
        from database import TimelineEntry, Scene, WaveformData, ClipAnchor, PacingBlueprint
        from sqlalchemy.orm import Session as DBSession

        init_db()
        check("DB init_db()", True)

        # Tabellen prüfen
        from sqlalchemy import inspect
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        expected_tables = {
            "projects", "audio_tracks", "video_clips", "scenes",
            "beatgrids", "waveform_data", "pacing_blueprints",
            "audio_video_anchors", "clip_anchors", "timeline_entries",
        }
        missing = expected_tables - tables
        check("Alle Tabellen vorhanden", len(missing) == 0,
              f"Missing: {missing}" if missing else f"({len(expected_tables)} Tabellen)")

        # FK CASCADE prüfen
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SELECT sql FROM sqlite_master WHERE name='scenes'"))
            row = result.fetchone()
            has_cascade = row and row[0] and "ON DELETE CASCADE" in row[0].upper()
            check("FK CASCADE aktiv", has_cascade)

        # Default-Projekt prüfen
        with DBSession(engine) as session:
            project = session.query(Project).first()
            check("Default-Projekt existiert", project is not None,
                  f"(id={project.id}, name='{project.name}')" if project else "")

    except Exception as e:
        check("DB-Initialisierung", False, str(e))
        log.error(traceback.format_exc())
        log.error("FATAL: DB-Init fehlgeschlagen, Abbruch.")
        return

    # ══════════════════════════════════════════════════════════
    section("Phase 3: Media-Ingest")
    # ══════════════════════════════════════════════════════════

    audio_track_id = None
    video_clip_id = None

    try:
        from services.ingest_service import ingest_audio, ingest_video

        track = ingest_audio(test_audio, project_id=1)
        check("Audio ingestiert", track is not None, f"(id={track.id})" if track else "")
        if track:
            audio_track_id = track.id

        # Duplikat-Check
        track2 = ingest_audio(test_audio, project_id=1)
        check("Audio Duplikat-Schutz", track2 is None, "(korrekt abgewiesen)")

    except Exception as e:
        check("Audio-Ingest", False, str(e))
        log.error(traceback.format_exc())

    try:
        clip = ingest_video(test_video, project_id=1)
        check("Video ingestiert", clip is not None, f"(id={clip.id})" if clip else "")
        if clip:
            video_clip_id = clip.id

    except Exception as e:
        check("Video-Ingest", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 4: Audio-Analyse (BPM + Beats)")
    # ══════════════════════════════════════════════════════════

    if audio_track_id:
        try:
            from services.audio_service import AudioAnalyzer
            analyzer = AudioAnalyzer()
            result = analyzer.analyze_and_store(audio_track_id)
            check("AudioAnalyzer.analyze_and_store()", result is not None)
            if result:
                check("BPM erkannt", result.get("bpm", 0) > 0,
                      f"(bpm={result.get('bpm')})")
                check("Duration erkannt", result.get("duration", 0) > 0,
                      f"(duration={result.get('duration')}s)")

                # Beatgrid manuell erstellen (BeatAnalysisService braucht GPU/beat_this)
                # AudioAnalyzer liefert beat_positions von librosa
                beat_positions = result.get("beat_positions", [])
                if beat_positions:
                    with DBSession(engine) as session:
                        existing_bg = session.query(Beatgrid).filter_by(
                            audio_track_id=audio_track_id
                        ).first()
                        if not existing_bg:
                            bg = Beatgrid(
                                audio_track_id=audio_track_id,
                                bpm=result["bpm"],
                                offset=beat_positions[0] if beat_positions else 0.0,
                                beat_positions=json.dumps(beat_positions),
                                downbeat_positions=json.dumps(beat_positions[::4]),
                                energy_per_beat=json.dumps(
                                    result.get("energy_curve", [0.5] * len(beat_positions))
                                ),
                            )
                            session.add(bg)
                            session.commit()
                    check("Beatgrid manuell erstellt", True,
                          f"({len(beat_positions)} beats)")

        except Exception as e:
            check("Audio-Analyse", False, str(e))
            log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 5: Pacing-Engine (Cut Points)")
    # ══════════════════════════════════════════════════════════

    if audio_track_id and video_clip_id:
        try:
            from services.pacing_service import (
                PacingSettings, calculate_cut_points,
                AdvancedPacingSettings, auto_edit_phase3,
                _get_beat_data_combined, _get_audio_duration,
            )

            # Beat-Daten prüfen
            beats, downbeats, energy = _get_beat_data_combined(audio_track_id)
            check("Beat-Positionen vorhanden", len(beats) > 0, f"({len(beats)} beats)")

            # Legacy Cut Points (4 Args: audio_id, video_id, settings, total_duration)
            settings = PacingSettings(tempo=50, energy=50, cut_density=50)
            duration = _get_audio_duration(audio_track_id) or 10.0
            cuts = calculate_cut_points(audio_track_id, video_clip_id, settings, duration)
            check("calculate_cut_points()", len(cuts) > 0, f"({len(cuts)} cuts)")

            # Jeder Cut ist ein CutPoint
            if cuts:
                check("CutPoint-Struktur", hasattr(cuts[0], 'time') and hasattr(cuts[0], 'source'),
                      f"(time={cuts[0].time}, source={cuts[0].source})")

        except Exception as e:
            check("Pacing-Engine", False, str(e))
            log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 6: Phase 3 Auto-Edit")
    # ══════════════════════════════════════════════════════════

    if audio_track_id and video_clip_id:
        try:
            settings = AdvancedPacingSettings(
                base_cut_rate=4,
                energy_reactivity=50,
                breakdown_behavior="halve",
            )
            segments, cut_points = auto_edit_phase3(
                audio_track_id, [video_clip_id], settings,
            )
            check("auto_edit_phase3()", len(segments) > 0,
                  f"({len(segments)} segments, {len(cut_points)} cuts)")

            if segments:
                seg = segments[0]
                check("Segment-Struktur", hasattr(seg, 'video_id') and hasattr(seg, 'start'),
                      f"(video_id={seg.video_id}, start={seg.start:.2f}, end={seg.end:.2f})")

        except Exception as e:
            check("Phase 3 Auto-Edit", False, str(e))
            log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 7: Timeline-Einträge + Export-Struktur")
    # ══════════════════════════════════════════════════════════

    if audio_track_id and video_clip_id:
        try:
            with DBSession(engine) as session:
                # Timeline-Einträge manuell erstellen (simuliert Auto-Edit Persistierung)
                te_audio = TimelineEntry(
                    project_id=1, track="audio", media_id=audio_track_id,
                    start_time=0.0, end_time=10.0, lane=0,
                )
                te_video = TimelineEntry(
                    project_id=1, track="video", media_id=video_clip_id,
                    start_time=0.0, end_time=5.0, lane=0,
                    source_start=0.0, source_end=5.0,
                    crossfade_duration=0.0, brightness=0.0, contrast=1.0,
                )
                session.add_all([te_audio, te_video])
                session.commit()

                # Rücklesen
                entries = session.query(TimelineEntry).filter_by(project_id=1).all()
                check("Timeline-Einträge erstellt", len(entries) >= 2,
                      f"({len(entries)} entries)")

                # Video-Entry mit Source-Offsets prüfen
                video_entries = [e for e in entries if e.track == "video"]
                if video_entries:
                    ve = video_entries[0]
                    check("Source-Offsets korrekt", ve.source_start is not None,
                          f"(source_start={ve.source_start}, source_end={ve.source_end})")
                    check("Crossfade-Feld vorhanden", ve.crossfade_duration is not None,
                          f"(crossfade={ve.crossfade_duration})")

            # Export-Zusammenfassung
            from services.export_service import get_timeline_summary
            summary = get_timeline_summary(project_id=1)
            check("get_timeline_summary()", summary is not None and len(summary) > 0)

        except Exception as e:
            check("Timeline + Export", False, str(e))
            log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 8: DB-Relationen-Integrität")
    # ══════════════════════════════════════════════════════════

    try:
        with DBSession(engine) as session:
            project = session.query(Project).first()
            if project:
                check("Project → audio_tracks Relation",
                      len(project.audio_tracks) > 0,
                      f"({len(project.audio_tracks)} tracks)")
                check("Project → video_clips Relation",
                      len(project.video_clips) > 0,
                      f"({len(project.video_clips)} clips)")
                check("Project → timeline_entries Relation",
                      len(project.timeline_entries) > 0,
                      f"({len(project.timeline_entries)} entries)")

            # AudioTrack → Beatgrid Relation
            if audio_track_id:
                track = session.get(AudioTrack, audio_track_id)
                if track:
                    check("AudioTrack.beatgrid vorhanden",
                          track.beatgrid is not None,
                          f"(bpm={track.beatgrid.bpm})" if track.beatgrid else "")
                    check("AudioTrack.bpm gesetzt",
                          track.bpm is not None and track.bpm > 0,
                          f"(bpm={track.bpm})")

    except Exception as e:
        check("DB-Relationen", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 9: Service-Imports (Rauch-Test)")
    # ══════════════════════════════════════════════════════════

    imports_ok = True
    for module_name in [
        "services.ingest_service",
        "services.audio_service",
        "services.pacing_service",
        "services.export_service",
        "services.timeline_service",
        "services.convert_service",
        "services.action_registry",
        "services.model_manager",
        "services.vector_db_service",
        "database",
    ]:
        try:
            __import__(module_name)
        except Exception as e:
            check(f"Import {module_name}", False, str(e))
            imports_ok = False
    check("Alle Service-Imports OK", imports_ok)

    # ══════════════════════════════════════════════════════════
    section("Phase 9b: ActionRegistry-Dispatch")
    # ══════════════════════════════════════════════════════════

    try:
        from services.action_registry import action_registry
        # Aktionen werden beim Import von register_actions registriert (Dekoratoren)
        import services.register_actions  # noqa: F401 — side-effect import

        # Registry initialisiert?
        all_actions = action_registry.list_actions()
        check("ActionRegistry hat Aktionen", len(all_actions) > 0,
              f"({len(all_actions)} registriert)")

        # Fuzzy-Match Rauch-Test
        if hasattr(action_registry, 'fuzzy_match'):
            matched_name, score = action_registry.fuzzy_match("analyze audio")
            check("Fuzzy-Match funktioniert", score > 0,
                  f"(matched='{matched_name}', score={score})")

    except Exception as e:
        check("ActionRegistry", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 9c: ModelManager Lifecycle")
    # ══════════════════════════════════════════════════════════

    try:
        from services.model_manager import ModelManager

        mm = ModelManager()
        check("ModelManager Singleton", mm is ModelManager(),
              "(gleiche Instanz)")
        check("ModelManager.device gesetzt", mm.device is not None,
              f"(device={mm.device})")

        vram = mm.get_vram_usage()
        check("VRAM-Abfrage funktioniert", vram is not None,
              f"(used={vram.get('used_mb', '?')}MB)" if isinstance(vram, dict) else "")

    except Exception as e:
        check("ModelManager", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 9d: Video-Analyse-Service (Smoke Test)")
    # ══════════════════════════════════════════════════════════

    if video_clip_id and os.path.exists(test_video):
        try:
            from services.video_analysis_service import detect_scenes

            scenes = detect_scenes(test_video)
            check("detect_scenes()", scenes is not None,
                  f"({len(scenes)} scenes)" if scenes else "(None returned)")

        except Exception as e:
            check("Video-Analyse Smoke", False, str(e))
            log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 9e: Stress-Test (20 Clips Batch-Ingest)")
    # ══════════════════════════════════════════════════════════

    stress_track_ids = []
    try:
        for i in range(20):
            stress_audio = os.path.join(tmp_dir, f"stress_{i}.wav")
            create_test_audio(stress_audio, duration=2.0)
            track = ingest_audio(stress_audio, project_id=1)
            if track:
                stress_track_ids.append(track.id)

        check("20 Audio-Dateien ingestiert", len(stress_track_ids) == 20,
              f"({len(stress_track_ids)}/20)")

        # Alle wieder löschen
        with DBSession(engine) as session:
            for tid in stress_track_ids:
                t = session.get(AudioTrack, tid)
                if t:
                    session.delete(t)
            session.commit()
        check("20 Stress-Tracks gelöscht", True)

    except Exception as e:
        check("Stress-Test", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("Phase 10: Cleanup + Test-Daten entfernen")
    # ══════════════════════════════════════════════════════════

    try:
        # Test-Einträge aus DB löschen
        with DBSession(engine) as session:
            # Timeline-Einträge löschen die wir erstellt haben
            session.query(TimelineEntry).filter_by(project_id=1).delete()
            # Test-Media löschen
            if audio_track_id:
                track = session.get(AudioTrack, audio_track_id)
                if track:
                    session.delete(track)
            if video_clip_id:
                clip = session.get(VideoClip, video_clip_id)
                if clip:
                    session.delete(clip)
            session.commit()
        check("DB-Cleanup", True)

        # Temp-Dateien löschen
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        check("Temp-Cleanup", True)

    except Exception as e:
        check("Cleanup", False, str(e))
        log.error(traceback.format_exc())

    # ══════════════════════════════════════════════════════════
    section("ERGEBNIS")
    # ══════════════════════════════════════════════════════════

    elapsed = time.time() - start_time
    total = PASS + FAIL

    log.info("")
    log.info("  Gesamt: %d Tests", total)
    log.info("  PASS:   %d", PASS)
    log.info("  FAIL:   %d", FAIL)
    log.info("  Zeit:   %.1fs", elapsed)
    log.info("")

    if FAIL > 0:
        log.error("FEHLGESCHLAGENE TESTS:")
        for err in ERRORS:
            log.error("  %s", err)
        log.error("")
        log.error("EXIT CODE: 1 (FAIL)")
        return 1
    else:
        log.info("ALLE TESTS BESTANDEN.")
        log.info("EXIT CODE: 0 (OK)")
        return 0


if __name__ == "__main__":
    sys.exit(run_stresstest())
