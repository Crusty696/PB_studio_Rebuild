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

import numpy as np
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
    # B-158: try/finally garantiert Engine-Dispose auch bei uncaught Exceptions
    # zwischen Engine-Erzeugung und finalem Return. Bisher fuehrten nur die
    # explizit abgefangenen Pfade (early return) zum Dispose, nicht aber
    # raise-Pfade aus _precompute_mood_embeddings/CrossModalMatcher/etc.
    _ae_eng = _make_auto_edit_engine()  # P7-FIX: siehe _make_auto_edit_engine Docstring
    try:
        return _auto_edit_phase3_inner(
            _ae_eng, audio_id, video_clip_ids, settings,
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

    if not beats or not video_clip_ids:
        return [], []

    if progress_cb:
        progress_cb(20, "Lade Video-Metadaten...")
    # 3. Video-Info laden
    video_info = _get_video_info(video_clip_ids)
    if not video_info:
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

    # F-005: Makro-Sektionserkennung
    sections = detect_sections(energy_per_beat, beats, total_duration)
    logger.info("Erkannte Sektionen: %s",
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
    cut_beats = _enforce_minimum_durations(cut_beats, sections, total_duration)

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

    if progress_cb:
        progress_cb(60, "Erzeuge Timeline-Segmente...")
    # 6. Segmente erzeugen
    segments: list[TimelineSegment] = []
    cut_points: list[CutPoint] = []
    available_ids = [vid for vid in video_clip_ids if vid in video_info]
    if not available_ids:
        return [], []

    # F-001 Fix: Load playback_offset from database for persistence
    clip_offsets: dict[int, float] = {}
    with Session(_ae_eng) as session:
        from database import VideoClip
        for vid in available_ids:
            video_clip = session.query(VideoClip).filter(
                VideoClip.id == vid, VideoClip.deleted_at.is_(None)
            ).first()
            clip_offsets[vid] = video_clip.playback_offset if video_clip else 0.0
    used_recently: list[int] = []
    prev_clip_idx: int | None = None

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

        if seg_duration < HARD_MIN_DURATION:
            continue

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

            # Normaler Clip-Match (+ Cross-Modal wenn verfuegbar)
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
            )
            prev_clip_idx = _clip_idx

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

    if progress_cb:
        progress_cb(100, "Timeline fertig")
    logger.info(
        "Phase 3: %d Segmente, %d CutPoints, %.1fs Gesamtdauer",
        len(segments), len(cut_points), total_duration,
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
