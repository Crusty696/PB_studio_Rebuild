"""Phase 3 Pacing-Service: DJ-Pacing Engine mit OTIO Timeline.

REGELN:
- Das Audio-File diktiert die Gesamtlaenge der OTIO Timeline.
- Jeder Schnitt faellt AUSNAHMSLOS auf einen Beat-Timestamp.
- Energy Reactivity moduliert die Cut-Rate basierend auf RMS-Energie.
- Breakdown Behavior aendert das Verhalten bei niedrigem RMS.
- Anker (OTIO Marker) werden respektiert und erzwingen bestimmte Videos.
- LanceDB Semantic Search fuer Keyword-Matching, sonst Motion/Random.

Dieses Modul ist die oeffentliche API. Die Implementierung ist aufgeteilt in:
- pacing_beat_grid.py  — Typen, Datenzugriff, Section-Detection
- pacing_edit_helpers.py — Kandidaten-Auswahl, Clip-Scoring
- pacing_memory.py     — KI-Langzeitgedaechtnis
"""

import bisect
import copy
import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import engine, Scene

# ── Re-Exports aus Sub-Modulen (Backward-Compat) ──
# Alle Namen die vorher direkt aus pacing_service importiert wurden
# sind weiterhin hier verfuegbar.

from services.pacing_beat_grid import (
    # Typen / Dataclasses
    PacingSettings,
    CutPoint,
    AdvancedPacingSettings,
    TimelineSegment,
    StemEnergy,
    Section,
    DropEvent,
    # Konstanten
    SECTION_PACING_MAP,
    HARD_MIN_DURATION,
    SECTION_MIN_DURATION,
    SECTION_CROSSFADE_MAP,
    _STEP_NO_CUT,
    # Cache-Management
    _get_cached_stem_audio,
    invalidate_pacing_caches,
    # Datenzugriff
    _get_beat_positions,
    _get_beat_data_combined,
    _get_audio_duration,
    _get_audio_path,
    _get_bpm,
    _get_video_info,
    _get_video_info_cached,
    _get_scenes,
    # Beat-Grid & Section-Detection
    compute_stem_weighted_energy,
    detect_sections,
    get_section_at_time,
    compute_vocal_activity,
    detect_drops,
    section_to_crossfade,
    detect_transitions,
    # F-010/F-011: Stem-Quality + Drum-Onset
    StemSNR,
    compute_stem_snr,
    detect_dj_mix_from_stems,
    DrumOnset,
    compute_drum_onsets,
)

from services.pacing_edit_helpers import (
    _density_to_beat_step,
    _compute_effective_step,
    _select_cut_beats_advanced,
    _enforce_minimum_durations,
    finalize_cut_beats,
    SECTION_MOOD_QUERIES,
    _precompute_mood_embeddings,
    _precompute_clip_fitness_matrix,
    _compute_clip_fitness,
    _match_video_by_motion,
    _match_video_for_segment,
    _motion_category,
    generate_keyframe_string,
    generate_keyframe_strings_for_project,
    # AUD-82: Cross-Modal Matching
    CrossModalMatcher,
    AudioContext,
)

from services.pacing_memory import (
    learn_from_anchor,
    record_rl_feedback,
    _get_ai_memory_bias,
    auto_edit_to_beats,
)

logger = logging.getLogger(__name__)


def _create_mem_pacing_run(
    *,
    audio_id: int,
    total_duration: float,
    is_dj_mix: bool,
    weights_profile: str = "default",
) -> int:
    """Create the run row required before DecisionRecorder can persist cuts."""
    from database import nullpool_session

    with nullpool_session() as session:
        row = session.execute(
            text(
                "INSERT INTO mem_pacing_run "
                "(audio_track_id, started_at, is_dj_mix, total_duration_sec, "
                "total_cuts, agent_version, weights_profile) "
                "VALUES (:audio_id, :started_at, :is_dj_mix, :duration, 0, "
                ":agent_version, :weights_profile) "
                "RETURNING id"
            ),
            {
                "audio_id": audio_id,
                "started_at": datetime.now(timezone.utc),
                "is_dj_mix": bool(is_dj_mix),
                "duration": float(total_duration),
                "agent_version": "pacing_service.auto_edit_phase3",
                "weights_profile": weights_profile,
            },
        ).fetchone()
        session.commit()
        if row is None:
            row = session.execute(text("SELECT last_insert_rowid()")).fetchone()
        return int(row[0])


def _complete_mem_pacing_run(run_id: int, total_cuts: int) -> None:
    from database import nullpool_session

    with nullpool_session() as session:
        session.execute(
            text(
                "UPDATE mem_pacing_run "
                "SET completed_at = :completed_at, total_cuts = :total_cuts "
                "WHERE id = :run_id"
            ),
            {
                "completed_at": datetime.now(timezone.utc),
                "total_cuts": int(total_cuts),
                "run_id": int(run_id),
            },
        )
        session.commit()


# ── Legacy Phase 2 functions — in pacing_service.py behalten fuer Test-Compat ──
# Tests patchen svc._get_beat_positions / svc._get_bpm / svc._get_scenes via
# patch.object(svc, ...) — das funktioniert nur wenn die Funktion im selben
# Modul-Namespace lebt wie die gepatchten Namen.

def calculate_cut_points(
    audio_id: int | None,
    video_id: int | None,
    settings: PacingSettings,
    total_duration: float = 60.0,
) -> list[CutPoint]:
    """Phase 2 compat: Berechnet Schnittpunkte EXAKT auf Beat-Timestamps."""
    beats = _get_beat_positions(audio_id)
    cuts: list[CutPoint] = []

    if beats:
        if settings.tempo >= 80:
            base_step = 1
        elif settings.tempo >= 60:
            base_step = 2
        elif settings.tempo >= 40:
            base_step = 4
        elif settings.tempo >= 20:
            base_step = 8
        else:
            base_step = 16

        curve = settings.manual_density_curve
        num_curve_samples = len(curve) if curve else 0

        for i, beat_time in enumerate(beats):
            if beat_time >= total_duration:
                break
            if curve and num_curve_samples > 0:
                curve_idx = int((beat_time / max(total_duration, 1e-9)) * (num_curve_samples - 1))
                curve_idx = max(0, min(curve_idx, num_curve_samples - 1))
                density = curve[curve_idx]
                curve_step = _density_to_beat_step(density)
                effective_step = min(base_step, curve_step) if density >= 0.5 else max(base_step, curve_step)
            else:
                effective_step = base_step

            if i % effective_step == 0:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                if i % 4 == 0:
                    strength = min(1.0, strength + 0.15)
                cuts.append(CutPoint(
                    time=round(beat_time, 4), source="beat", strength=round(strength, 3),
                ))
    else:
        bpm = _get_bpm(audio_id)
        if bpm and bpm > 0:
            interval = 60.0 / bpm
            t, i = 0.0, 0
            while t < total_duration:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                if i % 4 == 0:
                    strength = min(1.0, strength + 0.15)
                cuts.append(CutPoint(time=round(t, 3), source="beat", strength=strength))
                t += interval
                i += 1
        else:
            interval = max(1.0, 8.0 - (settings.tempo / 100.0 * 7.0))
            t = interval
            while t < total_duration:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                cuts.append(CutPoint(time=round(t, 3), source="energy", strength=strength))
                t += interval

    scenes = _get_scenes(video_id)
    if beats and scenes:
        beats_arr = np.array(beats)
        # O(N log N): Existierende Cut-Zeiten als sortiertes Array für schnelle Duplikat-Prüfung
        cut_times = np.array(sorted(c.time for c in cuts)) if cuts else np.array([])
        for scene in scenes:
            idx = np.searchsorted(beats_arr, scene["start_time"])
            if idx < len(beats_arr):
                snapped = float(beats_arr[idx])
                # Binary search statt linearem any()
                pos = np.searchsorted(cut_times, snapped)
                is_dup = False
                for check in (pos - 1, pos):
                    if 0 <= check < len(cut_times) and abs(cut_times[check] - snapped) < 0.05:
                        is_dup = True
                        break
                if not is_dup:
                    new_cut = CutPoint(
                        time=round(snapped, 4), source="scene",
                        strength=min(1.0, (scene["energy"] or 0.5) + 0.2),
                    )
                    cuts.append(new_cut)
                    # cut_times aktuell halten für nächste Iteration
                    ins = np.searchsorted(cut_times, snapped)
                    cut_times = np.insert(cut_times, ins, snapped)

    threshold = 1.0 - (settings.cut_density / 100.0)
    cuts = [c for c in cuts if c.strength >= threshold]
    cuts.sort(key=lambda c: c.time)
    filtered: list[CutPoint] = []
    for cut in cuts:
        if not filtered or (cut.time - filtered[-1].time) >= 0.1:
            filtered.append(cut)
    return filtered


def calculate_drum_cuts(audio_id: int, total_duration: float = 60.0,
                        energy_threshold: float = 0.3) -> list[CutPoint]:
    """Berechnet Schnittpunkte basierend auf dem Drums-Stem."""
    from database import AudioTrack as _AudioTrack
    with Session(engine) as session:
        track = session.query(_AudioTrack).filter(
            _AudioTrack.id == audio_id, _AudioTrack.deleted_at.is_(None)
        ).first()
        if not track or not track.stem_drums_path:
            return []
        drums_path = track.stem_drums_path
    try:
        from services.audio_constants import DEFAULT_SR
        import librosa
        y, sr = librosa.load(drums_path, sr=DEFAULT_SR, mono=True)
    except (OSError, IOError, ValueError, RuntimeError) as e:
        logger.warning("librosa.load fehlgeschlagen für Drums-Stem '%s': %s", drums_path, e)
        return []
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, backtrack=False
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    beats = _get_beat_positions(audio_id)
    beats_arr = np.array(beats) if beats else None
    rms = librosa.feature.rms(y=y)[0]
    max_rms = rms.max() if rms.max() > 0 else 1.0
    cuts = []
    used_beats = set()
    for onset_time in onset_times:
        if onset_time >= total_duration:
            break
        frame_idx = min(librosa.time_to_frames(onset_time, sr=sr), len(rms) - 1)
        strength = float(rms[frame_idx] / max_rms)
        if strength >= energy_threshold:
            if beats_arr is not None and len(beats_arr) > 0:
                idx = np.argmin(np.abs(beats_arr - onset_time))
                snapped_time = float(beats_arr[idx])
                if abs(snapped_time - onset_time) <= 0.15 and snapped_time not in used_beats:
                    used_beats.add(snapped_time)
                    cuts.append(CutPoint(
                        time=round(snapped_time, 4), source="drum",
                        strength=round(strength, 3),
                    ))
            else:
                cuts.append(CutPoint(
                    time=round(float(onset_time), 3), source="drum",
                    strength=round(strength, 3),
                ))
    return cuts


# ======================================================================
# Phase 3: AdvancedPacingEngine — Haupt-API
# ======================================================================

def _select_scene_for_offset(scenes: list, offset_sec: float) -> dict:
    """Cycle 14 Option A: Wählt die Scene aus die zum aktuellen
    clip_offset gehört.

    Statt unkonditional ``scenes[0]`` zu nehmen, findet diese Funktion die
    Scene die ``offset_sec`` enthält. Dadurch reflektieren die Scoring-
    Features in ``build_clip_features`` (motion_score, role, mood) die
    tatsächliche Stelle im Clip.

    Args:
        scenes: Liste von Scene-Dicts mit ``start``/``end``-Keys.
        offset_sec: Aktueller Playback-Offset im Clip.

    Returns:
        Erstes passendes Scene-Dict, oder ``scenes[0]`` als Fallback.
    """
    if not scenes:
        return {}
    for scene in scenes:
        start = float(scene.get("start", scene.get("start_time", 0.0)))
        end = float(scene.get("end", scene.get("end_time", 0.0)))
        if start <= offset_sec < end:
            return scene
    # Offset >= ende der letzten Scene → nach Reset (offset=0) wäre die
    # erste Scene die richtige; vor Reset oft die letzte. Nimm die letzte
    # weil der globale Reset (Zeile 851) eh auf 0.0 zurücksetzt.
    return scenes[-1] if offset_sec >= float(scenes[-1].get("end", scenes[-1].get("end_time", 0.0))) else scenes[0]


def _make_auto_edit_engine():
    """P7-FIX: Lokale NullPool-Engine fuer auto_edit_phase3.

    Der gemeinsame Pool (pool_size=10, overflow=30) wird bei parallelen
    Workern (StemSeparator, Export, etc.) zusaetzlich belastet. Auto-Edit
    oeffnet bis zu 4 Sessions auf 101+ Clips. Eigene NullPool-Engine pro
    Worker-Aufruf entkoppelt den langen DB-intensiven Pfad vom UI-Pool.
    """
    from sqlalchemy import create_engine as _create_engine
    from sqlalchemy.pool import NullPool
    import database.session as _session
    return _create_engine(
        f"sqlite:///{_session.APP_ROOT / 'pb_studio.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=NullPool,
    )


def auto_edit_phase3(
    audio_id: int,
    video_clip_ids: list[int],
    settings: AdvancedPacingSettings,
    progress_cb=None,
    should_stop_cb=None,
) -> tuple[list[TimelineSegment], list[CutPoint]]:
    """Phase 3: DJ-Pacing Engine — OTIO-konforme Timeline-Generierung.

    ZWINGENDE REGEL: Das Audio-File diktiert die Gesamtlaenge der Timeline.

    Returns:
        (segments, cut_points) — Segmente fuer OTIO + CutPoints fuer UI-Visualisierung
    """
    # Studio-Brain-Pipeline-Bridge ist der eine offizielle Feature-Flag-
    # Entscheidungspunkt. Default = False → unveränderter Legacy-Pfad.
    from services.pacing.bridge import maybe_use_studio_brain_pipeline
    _studio_brain_requested = maybe_use_studio_brain_pipeline(
        audio_id=audio_id, video_clip_ids=video_clip_ids,
    )

    # B-158: try/finally garantiert Engine-Dispose auch bei uncaught Exceptions
    # zwischen Engine-Erzeugung und finalem Return. Bisher fuehrten nur die
    # explizit abgefangenen Pfade (early return) zum Dispose, nicht aber
    # raise-Pfade aus _precompute_mood_embeddings/CrossModalMatcher/etc.
    _ae_eng = _make_auto_edit_engine()  # P7-FIX: siehe _make_auto_edit_engine Docstring
    try:
        return _auto_edit_phase3_inner(
            _ae_eng, audio_id, video_clip_ids, settings,
            studio_brain_requested=_studio_brain_requested,
            progress_cb=progress_cb, should_stop_cb=should_stop_cb,
        )
    finally:
        _ae_eng.dispose()


def _auto_edit_phase3_inner(
    _ae_eng,
    audio_id: int,
    video_clip_ids: list[int],
    settings: AdvancedPacingSettings,
    *,
    studio_brain_requested: bool = False,
    progress_cb=None,
    should_stop_cb=None,
) -> tuple[list[TimelineSegment], list[CutPoint]]:
    """Innerer Auto-Edit-Body. Engine-Cleanup uebernimmt der aeussere
    Wrapper via try/finally (B-158)."""
    # 1. Audio-Dauer = Timeline-Laenge
    if progress_cb:
        progress_cb(0, "Lade Audio-Daten...")
    total_duration = _get_audio_duration(audio_id)
    logger.info("Phase 3 Auto-Edit: Audio-Dauer = %.1fs", total_duration)

    # 2. Beats + Downbeats + Energie laden
    # Bug-14 Fix: _get_beat_data_combined() öffnet nur EINE Session statt 3
    beats, downbeats, energy_per_beat = _get_beat_data_combined(audio_id)

    # Fallback: Beats aus BPM generieren
    if not beats:
        bpm = _get_bpm(audio_id)
        if bpm and bpm > 0:
            interval = 60.0 / bpm
            t = 0.0
            beats = []
            while t < total_duration:
                beats.append(round(t, 4))
                t += interval

    if not beats:
        logger.warning(
            "auto_edit_phase3: keine Beat-Daten und kein BPM-Fallback fuer audio_id=%s",
            audio_id,
        )
        return [], []
    if not video_clip_ids:
        logger.warning("auto_edit_phase3: keine Video-Clips fuer audio_id=%s", audio_id)
        return [], []

    if progress_cb:
        progress_cb(20, "Lade Video-Metadaten...")
    # 3. Video-Info laden
    video_info = _get_video_info(video_clip_ids)
    if not video_info:
        logger.warning(
            "auto_edit_phase3: keine Video-Metadaten fuer %d Clip-IDs",
            len(video_clip_ids),
        )
        return [], []

    # 4. Anker sammeln (erzwungene Video-Zuweisungen)
    anchors = settings.anchors or []
    anchor_times = {a["time"]: a for a in anchors}

    if progress_cb:
        progress_cb(30, "Analysiere Stems und Motion...")

    # F-010: SNR-Qualitaets-Metriken — Stem-Weights proportional zur Trennungsqualitaet anpassen.
    # Stems mit niedrigem SNR (viel Bleed-Through) erhalten weniger Gewicht.
    stem_snr = compute_stem_snr(audio_id)
    _w_drums, _w_bass, _w_vocals, _w_other = 0.40, 0.30, 0.10, 0.20
    if stem_snr is not None:
        def _snr_factor(snr_db: float) -> float:
            # SNR >= 20 dB → volles Gewicht (1.0); SNR < 6 dB → Mindestgewicht (0.3)
            return min(1.0, max(0.3, snr_db / 20.0))
        _w_drums  = 0.40 * _snr_factor(stem_snr.drums)
        _w_bass   = 0.30 * _snr_factor(stem_snr.bass)
        _w_vocals = 0.10 * _snr_factor(stem_snr.vocals)
        _w_other  = 0.20 * _snr_factor(stem_snr.other)
        _total_w = _w_drums + _w_bass + _w_vocals + _w_other
        if _total_w > 0:
            _w_drums /= _total_w; _w_bass /= _total_w
            _w_vocals /= _total_w; _w_other /= _total_w
        logger.info(
            "F-010 SNR-Weights: drums=%.2f (%.1fdB) bass=%.2f (%.1fdB) "
            "vocals=%.2f (%.1fdB) other=%.2f (%.1fdB)",
            _w_drums, stem_snr.drums, _w_bass, stem_snr.bass,
            _w_vocals, stem_snr.vocals, _w_other, stem_snr.other,
        )

    # F-004: Stem-gewichtete Energie (SNR-adjustierte Weights, ersetzt Stereo-Summe wenn Stems vorhanden)
    stem_energy = compute_stem_weighted_energy(audio_id, beats, _w_drums, _w_bass, _w_vocals, _w_other)
    if stem_energy is not None:
        energy_per_beat = stem_energy.weighted
        logger.info("Nutze Stem-gewichtete Energie statt Stereo-Summe")

    # FIX-2.3: Wird ggf. vom LLM Strategist ueberschrieben
    _pacing_map_override = None

    def _sections_from_structure_db(audio_id: int, total_duration: float):
        """Laedt die echte Song-Struktur (structure_detection) als Sections.

        Labels der Audio-Analyse werden auf die Pacing-Section-Typen
        gemappt (INTRO->WARMUP etc.); unbekannte Labels -> TRANSITION.
        Returns [] wenn keine (oder zu wenige) Struktur-Daten vorliegen.
        """
        _label_map = {
            "INTRO": "WARMUP", "WARMUP": "WARMUP", "OUTRO": "COOLDOWN",
            "COOLDOWN": "COOLDOWN", "BRIDGE": "TRANSITION",
            "TRANSITION": "TRANSITION", "DROP": "DROP", "CHORUS": "CHORUS",
            "BUILDUP": "BUILDUP", "BREAKDOWN": "BREAKDOWN", "VERSE": "VERSE",
        }
        try:
            from database import StructureSegment
            with Session(_ae_eng) as _s:
                rows = (
                    _s.query(StructureSegment)
                    .filter_by(audio_track_id=audio_id)
                    .order_by(StructureSegment.start_time)
                    .all()
                )
                data = [(float(r.start_time), float(r.end_time or 0.0),
                         str(r.label or ""), float(r.energy or 0.5))
                        for r in rows]
        except Exception as exc:
            logger.debug("Struktur-Segmente nicht ladbar: %s", exc)
            return []
        if len(data) < 3:
            return []
        result = []
        for start, end, label, energy in data:
            if end <= start:
                continue
            stype = _label_map.get(label.strip().upper(), "TRANSITION")
            result.append(Section(
                start=start, end=min(end, total_duration),
                section_type=stype, avg_energy=energy,
            ))
        return result

    # Pacing-Tuning 2026-07-07: ECHTE Song-Struktur aus der Audio-Analyse
    # (structure_detection -> structure_segments) hat Vorrang vor der groben
    # Energie-Heuristik. Vorher wurde die DB-Struktur (INTRO/VERSE/DROP...)
    # im Pacing komplett ignoriert — gemessen: nur 2/21 Struktur-Grenzen
    # hatten einen Cut. Fallback bleibt detect_sections().
    sections = _sections_from_structure_db(audio_id, total_duration)
    if sections:
        logger.info("Sektionen aus Struktur-Analyse (DB): %s",
                    [(s.section_type, f"{s.start:.0f}-{s.end:.0f}s") for s in sections])
    else:
        # F-005: Makro-Sektionserkennung (Energie-Heuristik)
        sections = detect_sections(energy_per_beat, beats, total_duration)
        logger.info("Erkannte Sektionen (Heuristik): %s",
                    [(s.section_type, f"{s.start:.0f}-{s.end:.0f}s") for s in sections])

    # FIX-2.1: bpm_val VOR dem LLM-Strategist-Block definieren (war NameError).
    bpm_val = _get_bpm(audio_id) or 120.0

    # Phase 5: Optionaler LLM Pacing-Strategist (lokal, offline)
    if settings.use_llm_strategist:
        if progress_cb:
            progress_cb(35, "LLM Pacing-Strategist generiert Plan...")
        try:
            from services.pacing_strategist import PacingStrategist
            strategist = PacingStrategist()
            sections_dicts = [
                {"type": s.section_type, "start": s.start, "end": s.end, "avg_energy": s.avg_energy}
                for s in sections
            ]
            pacing_plan = strategist.generate_pacing_plan(
                sections=sections_dicts,
                bpm=bpm_val,
                total_duration=total_duration,
                clip_count=len(video_clip_ids),
                user_preferences=settings.user_preferences,
            )
            # LLM-Plan in Section-Overrides anwenden (lokale Kopie, nicht modul-level)
            _pacing_map_override = copy.deepcopy(SECTION_PACING_MAP)
            for override in pacing_plan.section_overrides:
                ov_type = override.get("type", "")
                ov_cut_rate = override.get("cut_rate_beats")
                if ov_type and ov_cut_rate and ov_type in _pacing_map_override:
                    _pacing_map_override[ov_type]["base"] = int(ov_cut_rate)
                    logger.info("LLM Override: %s base → %d beats", ov_type, ov_cut_rate)
            # FIX-2.3: Override-Map als lokale Variable speichern fuer spaetere Nutzung
            # in _select_cut_beats_advanced() → _compute_effective_step(pacing_map=...)
        except (ImportError, ValueError, RuntimeError) as e:
            logger.warning("LLM Pacing-Strategist uebersprungen: %s", e)

    # F-009: Vocal-Activity fuer Vocal-Aware Pacing
    vocal_activity = compute_vocal_activity(audio_id, beats)

    # PhD-Spec Abschnitt 8: Drop-Detection via Bass-Stem
    drops = detect_drops(stem_energy, energy_per_beat, beats)
    drop_times = {d.time for d in drops}

    if progress_cb:
        progress_cb(40, "Berechne Cut-Beats...")

    # Berechne durchschnittlichen Motion-Score aller Szenen (PhD-Spec Schritt 3)
    total_motion = 0.0
    motion_count = 0
    for vid_data in video_info.values():
        for scene in vid_data.get("scenes", []):
            total_motion += scene.get("energy", 0.5)
            motion_count += 1
    avg_motion = total_motion / motion_count if motion_count > 0 else 0.5

    # KI-Gedaechtnis: Aehnliche Audio-Situationen aus Lern-Beispielen abrufen
    avg_energy_val = float(np.mean(energy_per_beat)) if energy_per_beat else 0.5
    # bpm_val wurde bereits oben (vor LLM-Strategist) definiert (FIX-2.1)
    memory_bias = _get_ai_memory_bias(bpm_val, avg_energy_val)
    if memory_bias:
        # Preferred motion aus Gedaechtnis in avg_motion einfliessen lassen (30% Gewicht)
        pref_motion = memory_bias.get("preferred_motion")
        if pref_motion is not None:
            avg_motion = avg_motion * 0.7 + pref_motion * 0.3
            logger.info(
                "AI Memory: avg_motion angepasst auf %.3f (Lernregel: '%s')",
                avg_motion, memory_bias.get("label", ""),
            )

    # DJ-Mix Transition-Erkennung (PhD-Spec Abschnitt 9)
    transitions = detect_transitions(stem_energy, energy_per_beat, beats)
    transition_ranges = [(t[0], t[1]) for t in transitions]
    if transitions:
        logger.info("DJ-Uebergaenge erkannt: %s",
                    [(f"{s:.0f}-{e:.0f}s") for s, e in transition_ranges])

    # 5. Cut-Beats berechnen (Phase 3+4 mit Section-Awareness + Beat-Hierarchie)
    cut_beats = _select_cut_beats_advanced(
        beats, total_duration, settings, energy_per_beat,
        avg_motion=avg_motion,
        vocal_activity=vocal_activity,
        sections=sections,
        downbeats=downbeats,
        pacing_map=_pacing_map_override,
    )

    # Start immer bei 0
    if not cut_beats or cut_beats[0] > 0.01:
        cut_beats.insert(0, 0.0)
    # Ende = Audio-Dauer
    if cut_beats[-1] < total_duration - 0.1:
        cut_beats.append(total_duration)

    # Anker-Zeitpunkte einfuegen (auf naechsten Beat snappen)
    beats_arr = np.array(beats)
    for anchor_time in (anchor_times if beats_arr.size > 0 else []):
        idx = np.argmin(np.abs(beats_arr - anchor_time))
        snapped = float(beats_arr[idx])
        # P-024 Fix: O(log N) bisect statt O(N) any()
        _ai = bisect.bisect_left(cut_beats, snapped - 0.05)
        _anchor_dup = (_ai < len(cut_beats) and abs(cut_beats[_ai] - snapped) < 0.05)
        if not _anchor_dup:
            cut_beats.append(snapped)
    cut_beats.sort()

    # AUD-101: Video-Szenen-Grenzen als zusaetzliche Beat-aligned Cut-Points injizieren.
    # Wenn eine Video-Szene auf einen Beat faellt und dort noch kein Cut existiert,
    # wird sie als "scene"-CutPoint eingefuegt. Nur bei hohen Motion-Deltas (>0.3).
    _scene_cuts_added = 0
    if beats_arr.size > 0:
        for vid_data in video_info.values():
            for scene in vid_data.get("scenes", []):
                scene_time = scene.get("start", 0.0)
                if scene_time <= 0 or scene_time >= total_duration:
                    continue
                # Nur Szenen-Wechsel mit deutlichem Motion-Delta (signifikante visuelle Aenderung)
                motion = scene.get("energy", 0.5)
                if motion < 0.4:
                    continue
                # Snap auf naechsten Beat
                idx = np.searchsorted(beats_arr, scene_time)
                if idx >= len(beats_arr):
                    idx = len(beats_arr) - 1
                snapped = float(beats_arr[idx])
                if abs(snapped - scene_time) > 0.15:
                    continue  # Szene liegt zu weit vom naechsten Beat entfernt
                # Duplikat-Check via bisect
                _si = bisect.bisect_left(cut_beats, snapped - 0.05)
                _scene_dup = (_si < len(cut_beats) and abs(cut_beats[_si] - snapped) < 0.05)
                if not _scene_dup:
                    cut_beats.append(snapped)
                    _scene_cuts_added += 1
        if _scene_cuts_added > 0:
            cut_beats.sort()
            logger.info("AUD-101: %d Video-Szenen-Grenzen als Beat-aligned Cuts injiziert",
                        _scene_cuts_added)

    # Phase 2: Mindestdauer erzwingen — zu kurze Segmente entfernen
    # NEUBAU-VOLLINTEGRATION T2.5.3 (FR-S1-2): Vocal-on-Hold.
    # Pro Section werden die vorhandenen per-Beat-Stem-Energien (Demucs)
    # L1-normalisiert aggregiert (identische Normierung wie
    # stem_section_aggregator.aggregate — nur ohne doppeltes Audio-Laden);
    # vocal_hold_spacing_modifier liefert 2.0 fuer vocal-dominante Sections
    # -> Mindestdauer dort verdoppelt, Schnitte atmen ueber die Lyric-Phrase.
    _vocal_hold_windows: list[tuple[float, float, float]] = []
    _section_dominant_stems: dict[tuple[float, float], str | None] = {}
    try:
        from services.pacing.stem_section_aggregator import dominant_stem
        from services.pacing.vocal_hold_modifier import vocal_hold_spacing_modifier
        if stem_energy is not None and sections and beats:
            _b_arr = np.asarray(beats)
            for _sec in sections:
                _lo = int(np.searchsorted(_b_arr, _sec.start))
                _hi = max(_lo + 1, int(np.searchsorted(_b_arr, _sec.end)))
                _means = {}
                for _name in ("drums", "bass", "vocals", "other"):
                    _vals = getattr(stem_energy, _name, None) or []
                    _seg_vals = _vals[_lo:_hi]
                    _means[_name] = float(np.mean(_seg_vals)) if _seg_vals else 0.0
                _total_e = sum(_means.values())
                if _total_e > 1e-9:
                    _means = {k: v / _total_e for k, v in _means.items()}
                _mult = vocal_hold_spacing_modifier(_means)
                _section_dominant_stems[(_sec.start, _sec.end)] = dominant_stem(_means)
                if _mult > 1.0:
                    _vocal_hold_windows.append((_sec.start, _sec.end, _mult))
            if _vocal_hold_windows:
                logger.info(
                    "T2.5.3 Vocal-on-Hold: %d Sections mit Modifier 2.0: %s",
                    len(_vocal_hold_windows),
                    [f"{a:.0f}-{b:.0f}s" for a, b, _ in _vocal_hold_windows],
                )
    except Exception as _vh_exc:
        logger.warning("T2.5.3 Vocal-on-Hold uebersprungen: %s", _vh_exc)

    cut_beats = _enforce_minimum_durations(
        cut_beats, sections, total_duration,
        min_multiplier_windows=_vocal_hold_windows or None,
    )

    # Pacing-Tuning 2026-07-07: finaler Pass — Beat/Downbeat-Snap aller Cuts,
    # Pflicht-Cuts an Section-Grenzen, Timeline-Ende exakt = Audio-Ende,
    # Max-Segment-Laenge = laengster verfuegbarer Clip (verhindert
    # Material-Kappung + gap-close-Kaskade in apply/repair).
    _max_clip_dur = max(
        (video_info[v].get("duration", 0.0) for v in video_info), default=0.0)
    cut_beats = finalize_cut_beats(
        cut_beats, beats, downbeats, sections, total_duration,
        max_segment_duration=_max_clip_dur if _max_clip_dur > 1.0 else None,
    )

    # NEUBAU-VOLLINTEGRATION T2.5.2 (FR-S1-3): Drop-Burst + Hold-Bars.
    # 3 Cuts in 800ms um jeden Drop, danach 4 Bars Halten — die klassische
    # EDM-Editor-Heuristik fuer Drop-Impact. Rahmen (0.0/Audio-Ende) bleibt
    # fixiert. Hinweis: apply_bpm_adaptation aus demselben Modul wird
    # BEWUSST NICHT verdrahtet — SECTION_PACING_MAP + BUILDUP-Progression
    # leisten dieselbe Aufgabe feiner; doppeltes Ausduennen wuerde die
    # BUILDUP-Beschleunigung zerstoeren (Entscheidung T2.5.2, dokumentiert).
    try:
        from services.pacing.cut_density_modulator import apply_drop_burst
        if drop_times and bpm_val > 0:
            _pre_n = len(cut_beats)
            _burst = apply_drop_burst(
                cut_beats, sorted(float(d) for d in drop_times), bpm=bpm_val)
            _inner = sorted({
                round(float(t), 4) for t in _burst
                if 0.05 < t < total_duration - 0.05
            })
            cut_beats = [0.0] + _inner + [round(total_duration, 4)]
            while (len(cut_beats) >= 3
                   and (cut_beats[-1] - cut_beats[-2]) < HARD_MIN_DURATION * 0.6):
                cut_beats.pop(-2)
            logger.info(
                "T2.5.2 Drop-Burst: %d -> %d Cuts (%d Drops, Burst 3x/800ms, "
                "Hold 4 Bars)", _pre_n, len(cut_beats), len(drop_times),
            )
    except Exception as _burst_exc:
        logger.warning("T2.5.2 Drop-Burst fehlgeschlagen: %s", _burst_exc)

    # NEUBAU-VOLLINTEGRATION T2.5.1 (FR-S1-1): Onset-Feinsnap. Cuts werden
    # innerhalb +-50ms auf den naechsten persistierten Kick/Snare-Onset
    # geschoben (Beatgrid.onset_*_data, Writer: onset_rhythm_service).
    # 50ms < 70ms-Beat-Sync-Toleranz -> SCHNITT-Garantie bleibt erhalten;
    # Start (0.0) und Ende (=Audio-Dauer) werden nie verschoben.
    try:
        from services.pacing.cut_snapper import snap_to_onset
        _onset_times: list[float] = []
        with Session(_ae_eng) as _os_session:
            from database import Beatgrid as _Beatgrid
            _bg_row = (
                _os_session.query(
                    _Beatgrid.onset_kick_data, _Beatgrid.onset_snare_data,
                )
                .filter_by(audio_track_id=audio_id)
                .first()
            )
        if _bg_row:
            for _data in _bg_row:
                if _data:
                    _onset_times.extend(
                        float(p[0]) for p in _data
                        if isinstance(p, (list, tuple)) and p
                    )
        if _onset_times and len(cut_beats) > 2:
            _onset_arr = sorted(_onset_times)
            _snapped_mid = [
                round(snap_to_onset(t, _onset_arr, max_shift_ms=50.0), 4)
                for t in cut_beats[1:-1]
            ]
            _moved = sum(
                1 for a, b in zip(cut_beats[1:-1], _snapped_mid) if a != b)
            # Reihenfolge/Dedupe wahren, Rahmen fixieren
            _mid_sorted = sorted(set(_snapped_mid))
            cut_beats = [cut_beats[0]] + _mid_sorted + [cut_beats[-1]]
            logger.info(
                "T2.5.1 Onset-Snap: %d/%d Cuts auf Kick/Snare-Onsets "
                "verschoben (+-50ms, %d Onsets)",
                _moved, len(_snapped_mid), len(_onset_arr),
            )
        else:
            logger.debug(
                "T2.5.1 Onset-Snap uebersprungen (Onsets=%d)", len(_onset_times))
    except Exception as _onset_exc:
        logger.warning("T2.5.1 Onset-Snap fehlgeschlagen: %s", _onset_exc)

    # Phase 3: Mood-Embeddings + Fitness-Matrix pre-compute
    if progress_cb:
        progress_cb(55, "Lade KI-Modell fuer Video-Matching...")
    try:
        mood_embeddings = _precompute_mood_embeddings()
    except (ImportError, RuntimeError, OSError) as e:
        logger.warning("Mood-Embeddings uebersprungen: %s", e)
        mood_embeddings = {}

    clip_embeddings_matrix = np.empty((0, 1152), dtype=np.float32)
    clip_metadata_list: list[dict] = []
    fitness_matrix: dict[tuple, float] = {}
    if mood_embeddings:
        try:
            from services.vector_db_service import VectorDBService
            vdb = VectorDBService()
            clip_embeddings_matrix, clip_metadata_list = vdb.get_all_embeddings()
            if clip_embeddings_matrix.shape[0] > 0:
                fitness_matrix = _precompute_clip_fitness_matrix(
                    mood_embeddings, clip_embeddings_matrix, clip_metadata_list,
                )
                # Fixplan 2026-07-07: Caption-Mood aus der Szenen-DB in die
                # Kandidaten-Metadaten mischen (Vector-Store kennt ai_mood
                # nicht). Join ueber VideoClip.file_path + Szenen-Start.
                try:
                    from database import Scene as _Scene, VideoClip as _VC
                    with Session(_ae_eng) as _s:
                        _rows = (
                            _s.query(_VC.file_path, _Scene.start_time,
                                     _Scene.ai_mood, _Scene.ai_tags)
                            .join(_Scene, _Scene.video_clip_id == _VC.id)
                            .filter(_VC.deleted_at.is_(None))
                            .all()
                        )
                    _mood_by_key = {
                        (fp, round(float(st or 0.0), 1)): (mood, tags)
                        for fp, st, mood, tags in _rows
                    }
                    _enriched = 0
                    for _meta in clip_metadata_list:
                        _key = (_meta.get("video_path"),
                                round(float(_meta.get("scene_start", 0.0)), 1))
                        _mood_tags = _mood_by_key.get(_key)
                        if _mood_tags and _mood_tags[0]:
                            _meta["ai_mood"] = _mood_tags[0]
                            _meta["ai_tags"] = _mood_tags[1]
                            _enriched += 1
                    logger.info(
                        "Caption-Mood-Anreicherung: %d/%d Kandidaten mit "
                        "ai_mood aus Szenen-DB", _enriched, len(clip_metadata_list),
                    )
                except Exception as _mood_exc:
                    logger.warning(
                        "Caption-Mood-Anreicherung uebersprungen: %s", _mood_exc)
        except (ImportError, ValueError, RuntimeError) as e:
            logger.warning("Fitness-Matrix uebersprungen: %s", e)

    # AUD-97: DJ-Mix-Flag aus DB lesen (Fallback: Stem-basierte BPM-Analyse)
    track_is_dj_mix = False

    # AUD-82: Cross-Modal Matching Engine initialisieren
    # FIX: DB-Session schnell schliessen, DANN schwere Berechnung ausfuehren.
    # Vorher: Session blieb offen waehrend detect_dj_mix_from_stems() (Audio laden + Beat-Tracking)
    # UND compute_audio_mood_embedding() (SigLIP GPU-Inferenz) liefen — Pool-Exhaustion.
    cross_modal_matcher: CrossModalMatcher | None = None
    try:
        from database import AudioTrack as _AudioTrack
        # Schritt 1: Nur DB-Daten lesen, Session sofort schliessen
        _track_mood = ""
        _track_genre = ""
        _track_key = ""
        _track_found = False
        with Session(_ae_eng) as session:
            _track = session.query(_AudioTrack).filter(
                _AudioTrack.id == audio_id, _AudioTrack.deleted_at.is_(None)
            ).first()
            if _track:
                _track_found = True
                track_is_dj_mix = bool(getattr(_track, "is_dj_mix", False))
                _track_mood = _track.mood or ""
                _track_genre = _track.genre or ""
                _track_key = _track.key or ""

        # Schritt 2: Schwere Berechnung AUSSERHALB der Session
        if _track_found:
            if not track_is_dj_mix:
                track_is_dj_mix = detect_dj_mix_from_stems(audio_id)
                if track_is_dj_mix:
                    logger.info(
                        "AUD-97: Stem-BPM-Analyse erkennt DJ-Mix (audio_id=%d)", audio_id,
                    )
            else:
                logger.info("AUD-97: DJ-Mix via DB-Flag (audio_id=%d)", audio_id)

            # Stem-Energie-Verhaeltnisse berechnen
            _drum_ratio, _bass_ratio, _vocal_ratio = 0.4, 0.3, 0.1
            if stem_energy is not None and energy_per_beat:
                _n = len(energy_per_beat)
                if _n > 0:
                    _d_mean = np.mean(stem_energy.drums[:_n]) if stem_energy.drums else 0.4
                    _b_mean = np.mean(stem_energy.bass[:_n]) if stem_energy.bass else 0.3
                    _v_mean = np.mean(stem_energy.vocals[:_n]) if stem_energy.vocals else 0.1
                    _total = _d_mean + _b_mean + _v_mean + 1e-8
                    _drum_ratio = float(_d_mean / _total)
                    _bass_ratio = float(_b_mean / _total)
                    _vocal_ratio = float(_v_mean / _total)

            audio_ctx = AudioContext(
                bpm=bpm_val,
                mood=_track_mood,
                genre=_track_genre,
                key=_track_key,
                avg_energy=avg_energy_val,
                drum_ratio=_drum_ratio,
                bass_ratio=_bass_ratio,
                vocal_ratio=_vocal_ratio,
            )
            cross_modal_matcher = CrossModalMatcher(
                audio_ctx=audio_ctx,
                mood_embeddings=mood_embeddings,
                beats=beats,
            )
            # Audio-Mood-Embedding berechnen (nutzt SigLIP, entlaedt sofort)
            cross_modal_matcher.compute_audio_mood_embedding()
            logger.info("AUD-82: CrossModalMatcher aktiv (mood=%s, genre=%s, bpm=%.0f)",
                        audio_ctx.mood, audio_ctx.genre, audio_ctx.bpm)
    except (ImportError, ValueError, RuntimeError) as e:
        logger.warning("AUD-82: CrossModalMatcher uebersprungen: %s", e)
        cross_modal_matcher = None

    # ── Ollama Direct EDL Reasoning (Stufe 3) ──────────────────────
    if getattr(settings, "use_llm_pacing", False):
        try:
            from services.pacing.ollama_pacing import OllamaPacingService
            logger.info("Ollama direct EDL reasoning aktiv: Generiere EDL...")
            if progress_cb:
                progress_cb(58, "Ollama generiert direkte EDL...")
            ollama_service = OllamaPacingService()
            edl = ollama_service.generate_edl(
                audio_id=audio_id,
                video_clip_ids=video_clip_ids,
                user_preferences=settings.user_preferences
            )
            if edl:
                segments: list[TimelineSegment] = []
                cut_points: list[CutPoint] = []
                
                with Session(_ae_eng) as session:
                    from database import VideoClip
                    video_paths = {
                        vc.id: vc.file_path
                        for vc in session.query(VideoClip).filter(VideoClip.id.in_(video_clip_ids)).all()
                    }
                
                for entry in edl:
                    vid = entry["video_id"]
                    if vid not in video_paths:
                        continue
                    vpath = video_paths[vid]
                    v_start = entry["start"]
                    v_end = entry["end"]
                    scene_id = entry.get("scene_id")
                    
                    segments.append(TimelineSegment(
                        video_id=vid,
                        video_path=vpath,
                        start=v_start,
                        end=v_end,
                        source_start=0.0,
                        source_end=v_end - v_start,
                        is_anchor=False,
                        scene_id=str(scene_id) if scene_id is not None else ""
                    ))
                    
                    cut_points.append(CutPoint(
                        time=v_start,
                        source="llm",
                        strength=0.8
                    ))
                
                if segments:
                    cut_points.append(CutPoint(
                        time=segments[-1].end,
                        source="llm",
                        strength=0.8
                    ))
                    cut_points.sort(key=lambda c: c.time)
                    logger.info("EDL von Ollama erfolgreich in %d Segmente und %d CutPoints übersetzt.", len(segments), len(cut_points))
                    return segments, cut_points
        except Exception as e:
            logger.warning("Ollama direct EDL reasoning fehlgeschlagen, Fallback auf Standard: %s", e)

    if progress_cb:
        progress_cb(60, "Erzeuge Timeline-Segmente...")
    # 6. Segmente erzeugen
    segments: list[TimelineSegment] = []
    cut_points: list[CutPoint] = []
    available_ids = [vid for vid in video_clip_ids if vid in video_info]
    if not available_ids:
        return [], []

    # F-001 Fix: Load playback_offset from database for persistence.
    # B-055/N+1 Fix: Single bulk-query statt einer Query pro Clip.
    clip_offsets: dict[int, float] = {vid: 0.0 for vid in available_ids}
    with Session(_ae_eng) as session:
        from database import VideoClip
        rows = session.query(VideoClip.id, VideoClip.playback_offset).filter(
            VideoClip.id.in_(available_ids),
            VideoClip.deleted_at.is_(None),
        ).all()
        for vid, offset in rows:
            clip_offsets[vid] = offset or 0.0
    used_recently: list[int] = []
    # Fixplan 2026-07-07 Schritt 3: globale Nutzungs-Zaehlung + Cap + Sampling.
    # Cap = ceil(Segmente/Videos)+1 → bei 58 Segmenten und 39 Videos max. 3
    # Verwendungen pro Video (vorher real: 1 Video 58x, dann Top-Videos 8x).
    usage_counts: dict[int, int] = {}
    _n_slots = max(1, len(cut_beats) - 1)
    max_uses_per_video = int(np.ceil(_n_slots / max(1, len(available_ids)))) + 1
    # Seed: PB_PACING_SEED (Tests/Repro) oder zufaellig pro Run (geloggt).
    import os as _os_seed
    import random as _random
    try:
        _seed = int(_os_seed.environ.get("PB_PACING_SEED", ""))
    except ValueError:
        _seed = int.from_bytes(_os_seed.urandom(4), "little")
    selection_rng = _random.Random(_seed)
    logger.info(
        "Schritt-3-Diversitaet: %d Slots, %d Videos, max_uses=%d, seed=%d",
        _n_slots, len(available_ids), max_uses_per_video, _seed,
    )
    prev_clip_idx: int | None = None
    # T2.5.2: ai_mood des zuletzt gewaehlten Clips (Phrase-Boundary-Constraint)
    _prev_clip_mood: str | None = None
    # B-371: ClipFeatures der zuletzt vom Studio-Brain gewaehlten Scene.
    # Wird als predecessor an select_best uebergeben, damit PacingScorer
    # Style-Kompatibilitaet/Collision-Penalty gegen die Vorgaenger-Wahl
    # bewerten kann statt neutral (predecessor=None) zu bleiben.
    _sb_predecessor = None

    # Pre-resolve anchor scenes to avoid DB session per segment
    anchor_scene_map: dict[str, int] = {}  # scene_id_str -> video_clip_id
    if anchor_times:
        scene_ids = []
        for anchor_data in anchor_times.values():
            sid = anchor_data.get("scene_id", "")
            if sid:
                try:
                    scene_ids.append(int(sid))
                except (ValueError, TypeError) as exc:
                    logger.warning("Failed to parse scene_id in auto_edit_phase3: %s", exc)
        if scene_ids:
            with Session(_ae_eng) as session:
                for scene in session.query(Scene).filter(Scene.id.in_(scene_ids)).all():
                    anchor_scene_map[str(scene.id)] = scene.video_clip_id

    # P0 #1 Cycle 11: Bridge-Pipeline-Setup wenn Studio-Brain-Flag aktiv.
    # Default-off — Legacy-Pfad bleibt unverändert. Setup ist defensive:
    # bei Fehler fällt der Loop auf Legacy zurück (Snapshot-Test schützt).
    _studio_brain_pipeline = None
    _studio_brain_audio_track = None
    _studio_brain_run_id = None
    try:
        if studio_brain_requested:
            from services.pacing.pipeline import PacingPipeline
            from services.pacing.scorer import PacingScorer
            from services.pacing.decision_recorder import DecisionRecorder
            from database import AudioTrack, nullpool_session
            # B-197 F-4: ohne ``decision_recorder=`` blieben mem_decision +
            # mem_pacing_run leer. Damit waren AuditTab/MemoryTab/
            # PacingDecisionExplorer ohne Daten — siehe
            # ``wiki/synthesis/brain-audit-2026-04-27.md``.
            # B-326: DecisionRecorder persistiert nur, wenn die Pipeline eine
            # run_id hat. Der Auto-Edit-Livepfad muss deshalb vor select_best()
            # eine mem_pacing_run-Zeile erzeugen.
            _studio_brain_run_id = _create_mem_pacing_run(
                audio_id=audio_id,
                total_duration=total_duration,
                is_dj_mix=track_is_dj_mix,
                weights_profile="default",
            )
            _studio_brain_pipeline = PacingPipeline(
                scorer=PacingScorer(weights_profile="default"),
                decision_recorder=DecisionRecorder(
                    session_factory=nullpool_session,
                ),
                run_id=_studio_brain_run_id,
                # B-370: DJ-Mix-Budget muss in die Pipeline durchgereicht
                # werden, sonst greift die globale Scene-Wiederholungsgrenze
                # (VariationsBudget.DJ_MIX_SCENE_ID_GLOBAL_MAX) nie, obwohl der
                # Run als DJ-Mix erkannt und in mem_pacing_run markiert wird.
                dj_mix=track_is_dj_mix,
            )
            with Session(_ae_eng) as _sb_session:
                _studio_brain_audio_track = (
                    _sb_session.query(AudioTrack)
                    .filter_by(id=audio_id)
                    .first()
                )
            logger.info(
                "Studio-Brain-Pipeline aktiv (PB_USE_STUDIO_BRAIN_PIPELINE=1) — "
                "Cuts werden zusätzlich via select_best gerated, Legacy-Fallback bei None. "
                "mem_pacing_run=%s",
                _studio_brain_run_id,
            )
    except (ImportError, RuntimeError, AttributeError) as _sb_exc:
        logger.warning(
            "Studio-Brain-Pipeline-Setup fehlgeschlagen, falle auf Legacy: %s", _sb_exc
        )
        _studio_brain_pipeline = None

    # P-022 Fix: Sortierte Drop-Zeiten fuer O(log N) bisect statt O(N) any()
    sorted_drops = sorted(drop_times)
    # P-023 Fix: Sortierte Transition-Ranges fuer O(log N) bisect statt O(N) any()
    _sorted_transitions = sorted(transition_ranges)
    sorted_trans_starts = [t[0] for t in _sorted_transitions]
    sorted_trans_ends = [t[1] for t in _sorted_transitions]

    for i in range(len(cut_beats) - 1):
        # B-157: Cancel-Check im Hot-Loop. Bei 60+ Cuts × Cross-Modal-Match
        # darf der User den Lauf abbrechen koennen ohne auf alle Segmente
        # zu warten. Engine-Cleanup uebernimmt der finally-Block (B-158).
        if should_stop_cb is not None and should_stop_cb():
            logger.info("auto_edit_phase3: cancel-request bei Segment %d/%d",
                        i, len(cut_beats) - 1)
            return segments, cut_points
        seg_start = cut_beats[i]
        seg_end = cut_beats[i + 1]
        seg_duration = seg_end - seg_start

        # Pacing-Tuning 2026-07-07: Mindestdauern erzwingt bereits
        # _enforce_minimum_durations (section-aware, DROP darf 2.0s).
        # Der alte HARD_MIN-Skip hier warf legitime kurze DROP-Segmente
        # weg und riss Luecken in die Timeline (4.6s-Loch am Track-Ende).
        if seg_duration < 0.2:
            # T2.5.2: Schwelle 0.5 -> 0.2, damit Drop-Burst-Segmente
            # (3 Cuts / 800ms => ~0.4s) nicht verworfen werden.
            continue  # nur degenerierte Rest-Segmente ueberspringen

        # Section-Type frueh bestimmen (wird fuer Video-Matching benoetigt)
        seg_section = get_section_at_time(sections, seg_start)
        seg_section_type = seg_section.section_type if seg_section else "TRANSITION"

        # Pruefen ob ein Anker dieses Segment erzwingt
        is_anchor = False
        anchor_scene_id = ""
        anchor_vid = None

        for anchor_time, anchor_data in anchor_times.items():
            if abs(seg_start - anchor_time) < 0.5 or (seg_start <= anchor_time < seg_end):
                is_anchor = True
                anchor_scene_id = anchor_data.get("scene_id", "")
                # Scene-ID zu Video-ID aufloesen (pre-resolved)
                if anchor_scene_id:
                    vid = anchor_scene_map.get(anchor_scene_id)
                    if vid is not None:
                        anchor_vid = vid
                break

        if is_anchor and anchor_vid and anchor_vid in video_info:
            vid = anchor_vid
            # Szene finden und deren Start nutzen
            scene_info = None
            if anchor_scene_id:
                for s in video_info[vid].get("scenes", []):
                    if str(s["id"]) == str(anchor_scene_id):
                        scene_info = s
                        break
            source_start = scene_info["start"] if scene_info else 0.0
        else:
            # AUD-82: Section-Progress fuer Cross-Modal Matcher berechnen
            _seg_section_progress = 0.0
            if seg_section:
                _sec_dur = max(seg_section.end - seg_section.start, 0.001)
                _seg_section_progress = (seg_start - seg_section.start) / _sec_dur
                _seg_section_progress = max(0.0, min(1.0, _seg_section_progress))

            # P0 #1 Cycle 11: Studio-Brain-Pfad wenn aktiv.
            _sb_chosen_vid = None
            if _studio_brain_pipeline is not None and _studio_brain_audio_track is not None:
                try:
                    from services.pacing.bridge_mapping import (
                        build_audio_context, build_clip_features,
                    )
                    # Build AudioContext
                    _sb_ctx = build_audio_context(
                        seg_start_sec=seg_start,
                        seg_section_type=seg_section_type,
                        audio_track=_studio_brain_audio_track,
                        beats=beats,
                        energy_per_beat=energy_per_beat,
                    )
                    # Cycle 14 Option A: Build ClipFeatures pro Clip mit der
                    # Scene die zum aktuellen clip_offsets[vid] passt — nicht
                    # mehr unkonditional _scenes[0]. Damit reflektieren die
                    # Scoring-Features (motion_score, role, mood) die tatsächliche
                    # Stelle im Clip die als Nächstes abgespielt würde.
                    _sb_candidates = []
                    for _vid in available_ids:
                        _scenes = video_info[_vid].get("scenes", [])
                        if not _scenes:
                            continue
                        _sc = _select_scene_for_offset(
                            _scenes, clip_offsets.get(_vid, 0.0),
                        )
                        # Stub-Scene-Objekt mit den nötigen Feldern
                        _sb_candidates.append(build_clip_features(
                            video_clip_id=_vid,
                            scene=type("_SbScene", (), {
                                "id": _sc.get("id", _vid * 100),
                                "motion_score": _sc.get("motion_score", _sc.get("energy", 0.5)),
                                "ai_mood": _sc.get("ai_mood"),
                                "role": _sc.get("role"),
                                "style_bucket_id": _sc.get("style_bucket_id"),
                                # B-371: predecessor wird jetzt an select_best
                                # uebergeben; Embedding-Lookup (Style/Collision-
                                # Signal) bleibt deferred (Cycle 12 — VectorDB-
                                # Join video_path/scene_index noch nicht verdrahtet).
                                "embedding": None,
                            })(),
                        ))
                    if _sb_candidates:
                        _sb_result = _studio_brain_pipeline.select_best(
                            candidates=_sb_candidates,
                            ctx=_sb_ctx,
                            predecessor=_sb_predecessor,
                            recent_clip_ids=used_recently[-3:] if used_recently else None,
                        )
                        if _sb_result.chosen is not None:
                            _sb_chosen_vid = _sb_result.chosen.clip_id
                            # B-371: gewaehlte Scene als predecessor fuer das
                            # naechste Segment merken (Style/Collision-Signal).
                            _sb_predecessor = _sb_result.chosen
                except (ImportError, RuntimeError, AttributeError, KeyError) as _sb_loop_exc:
                    logger.debug(
                        "Studio-Brain select_best fehlgeschlagen für seg=%.2f, falle "
                        "auf Legacy zurück: %s", seg_start, _sb_loop_exc,
                    )

            if _sb_chosen_vid is not None and _sb_chosen_vid in video_info:
                vid = _sb_chosen_vid
                source_start = clip_offsets.get(vid, 0.0)
                # Cycle 13 BUG-4: Intelligent-Looping-Reset nachholen, wenn
                # Restlaufzeit < seg_duration ist — sonst kommt der globale
                # Reset (Zeile 851) erst NACH der Wahl und korrigiert
                # source_start ohne dass die Pipeline-Entscheidung
                # reflektiert.
                _vid_dur = video_info[vid].get("duration", 0.0)
                if _vid_dur - source_start < seg_duration:
                    source_start = 0.0
                _clip_idx = (
                    available_ids.index(vid) if vid in available_ids else None
                )
            else:
                # NEUBAU-VOLLINTEGRATION T2.5.2: Kontext fuer Phrase-Boundary-
                # Constraint (Beat-Index des Cuts) + Section-Coherence
                # (Abstand zur naechsten Section-Grenze) berechnen.
                _t252_beat_idx = int(np.searchsorted(beats_arr, seg_start)) \
                    if beats_arr.size else None
                _t252_bdist = None
                if seg_section is not None:
                    _t252_bdist = float(min(
                        max(0.0, seg_start - seg_section.start),
                        max(0.0, seg_section.end - seg_start),
                    ))

                # Legacy-Pfad (default oder Studio-Brain-Fallback)
                vid, source_start, _clip_idx = _match_video_for_segment(
                    seg_start, seg_end, settings.vibe,
                    video_info, available_ids, clip_offsets, used_recently,
                    energy_per_beat=energy_per_beat, beats=beats,
                    memory_bias=memory_bias,
                    section_type=seg_section_type,
                    fitness_matrix=fitness_matrix,
                    clip_embeddings=clip_embeddings_matrix,
                    clip_metadata=clip_metadata_list,
                    prev_clip_idx=prev_clip_idx,
                    cross_modal_matcher=cross_modal_matcher,
                    section_progress=_seg_section_progress,
                    usage_counts=usage_counts,
                    max_uses=max_uses_per_video,
                    rng=selection_rng,
                    cut_beat_idx=_t252_beat_idx,
                    boundary_distance_sec=_t252_bdist,
                    prev_mood=_prev_clip_mood,
                )
            prev_clip_idx = _clip_idx
            # T2.5.2: Mood des gewaehlten Clips fuer den Phrase-Constraint
            # des naechsten Segments merken.
            if (_clip_idx is not None and clip_metadata_list
                    and _clip_idx < len(clip_metadata_list)):
                _prev_clip_mood = clip_metadata_list[_clip_idx].get("ai_mood")

            # Fixplan 2026-07-07 Schritt 4: 36/39 Testvideos haben genau EINE
            # Szene mit start=0 — Wiederholungen desselben Videos zeigten
            # deshalb immer denselben Bildausschnitt ab Sekunde 0. Bei
            # Wiederverwendung eines Ein-Szenen-Videos wird der Startpunkt
            # innerhalb des nutzbaren Bereichs variiert (seed-gesteuert).
            if vid != -1 and vid in video_info and usage_counts.get(vid, 0) >= 1:
                _v_scenes = video_info[vid].get("scenes", [])
                if len(_v_scenes) <= 1:
                    _v_dur = video_info[vid].get("duration", 0.0)
                    _headroom = _v_dur - (seg_end - seg_start)
                    if _headroom > 0.5:
                        source_start = round(
                            selection_rng.uniform(0.0, _headroom), 4)

        if vid == -1:
            logger.warning("Kein Video fuer Segment %.2f-%.2f verfuegbar, ueberspringe.", seg_start, seg_end)
            continue

        vid_duration = video_info[vid]["duration"]
        vid_path = video_info[vid]["path"]

        # Intelligent looping: Reset wenn nicht genug Material
        remaining = vid_duration - source_start
        if remaining < seg_duration:
            source_start = 0.0
            clip_offsets[vid] = 0.0

        source_end = min(source_start + seg_duration, vid_duration)

        # PhD-Spec: Crossfade-Dauer basierend auf bereits bestimmtem Section-Type
        seg_crossfade = section_to_crossfade(seg_section_type)

        # Bei Drops: Hard Cut erzwingen (0ms crossfade)
        # P-022 Fix: O(log N) bisect statt O(N) any()
        _di = bisect.bisect_left(sorted_drops, seg_start - 0.5)
        is_drop = _di < len(sorted_drops) and abs(sorted_drops[_di] - seg_start) < 0.5
        if is_drop:
            seg_crossfade = 0.0

        # DJ-Mix Transition: Laengerer Crossfade + "transition" Source-Tag
        # P-023 Fix: O(log N) bisect statt O(N) any()
        _ti = bisect.bisect_right(sorted_trans_starts, seg_start) - 1
        is_in_transition = (_ti >= 0 and _ti < len(sorted_trans_ends) and seg_start < sorted_trans_ends[_ti])
        if is_in_transition and not is_drop:
            # DJ-Uebergang: Laengerer Crossfade als SECTION_CROSSFADE_MAP["TRANSITION"]=1.5s
            # AUD-97: Bei erkanntem DJ-Mix noch weichere Transitions (3.0s statt 2.0s)
            _dj_crossfade_base = 3.0 if track_is_dj_mix else 2.0
            seg_crossfade = max(seg_crossfade, _dj_crossfade_base)

        segments.append(TimelineSegment(
            video_id=vid,
            video_path=vid_path,
            start=round(seg_start, 4),
            end=round(seg_end, 4),
            source_start=round(source_start, 4),
            source_end=round(source_end, 4),
            is_anchor=is_anchor,
            scene_id=anchor_scene_id,
            crossfade_duration=round(seg_crossfade, 2),
            section_type=seg_section_type,
        ))

        # CutPoint fuer UI-Visualisierung
        if is_in_transition:
            source_type = "transition"
        elif is_drop:
            source_type = "drop"
        elif is_anchor:
            source_type = "anchor"
        else:
            source_type = "beat"
        # Energie-basierte Staerke
        beat_idx = np.searchsorted(beats_arr, seg_start)
        beat_idx = min(beat_idx, len(energy_per_beat) - 1) if energy_per_beat else 0
        strength = energy_per_beat[beat_idx] if beat_idx < len(energy_per_beat) else 0.5
        cut_points.append(CutPoint(
            time=round(seg_start, 4),
            source=source_type,
            strength=round(min(1.0, strength + 0.2), 3),
        ))

        # Offsets aktualisieren (F-018: gecappte source_end nutzen)
        clip_offsets[vid] = source_end
        if clip_offsets[vid] >= vid_duration:
            clip_offsets[vid] = 0.0

        # F-019: Begrenze used_recently auf 10 Eintraege (nur letzte 3 werden gelesen)
        used_recently.append(vid)
        if len(used_recently) > 10:
            used_recently[:] = used_recently[-10:]
        # Schritt 3: globale Nutzung zaehlen (fuer Cap + Freshness-Strafe)
        usage_counts[vid] = usage_counts.get(vid, 0) + 1

    if progress_cb:
        progress_cb(100, "Timeline fertig")
    logger.info(
        "Phase 3: %d Segmente, %d CutPoints, %.1fs Gesamtdauer",
        len(segments), len(cut_points), total_duration,
    )
    if _studio_brain_run_id is not None:
        try:
            _complete_mem_pacing_run(_studio_brain_run_id, len(cut_points))
        except Exception as exc:  # broad: timeline output must not be lost
            logger.warning(
                "mem_pacing_run completion failed for run_id=%s: %s",
                _studio_brain_run_id,
                exc,
            )

    # F-001 Fix: Save playback_offset to database for persistence
    with Session(_ae_eng) as session:
        from database import VideoClip
        for vid, offset in clip_offsets.items():
            video_clip = session.query(VideoClip).filter(
                VideoClip.id == vid, VideoClip.deleted_at.is_(None)
            ).first()
            if video_clip:
                video_clip.playback_offset = offset
        session.commit()

    return segments, cut_points
