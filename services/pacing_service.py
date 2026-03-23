"""Phase 3 Pacing-Service: DJ-Pacing Engine mit OTIO Timeline.

REGELN:
- Das Audio-File diktiert die Gesamtlaenge der OTIO Timeline.
- Jeder Schnitt faellt AUSNAHMSLOS auf einen Beat-Timestamp.
- Energy Reactivity moduliert die Cut-Rate basierend auf RMS-Energie.
- Breakdown Behavior aendert das Verhalten bei niedrigem RMS.
- Anker (OTIO Marker) werden respektiert und erzwingen bestimmte Videos.
- LanceDB Semantic Search fuer Keyword-Matching, sonst Motion/Random.
"""

import copy
import json
import logging
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session
from database import engine, AudioTrack, VideoClip, Scene, Beatgrid

logger = logging.getLogger(__name__)


def invalidate_pacing_caches():
    """Cache leeren nach Media-Import oder DB-Änderung."""
    _get_audio_duration.cache_clear()
    _get_audio_path.cache_clear()
    _get_bpm.cache_clear()
    _get_video_info_cached.cache_clear()


# ── Backward-compatible types ──

@dataclass
class PacingSettings:
    """Legacy UI-Slider-Einstellungen (Phase 2 compat)."""
    tempo: int = 50
    energy: int = 50
    cut_density: int = 50
    vibe: str = ""
    manual_density_curve: list[float] | None = None


@dataclass
class CutPoint:
    """Ein einzelner Schnittpunkt auf der Timeline."""
    time: float
    source: str       # "beat", "scene", "energy", "drum", "anchor"
    strength: float   # 0.0-1.0


# ── Phase 3: Advanced DJ Pacing ──

@dataclass
class AdvancedPacingSettings:
    """Phase 3 DJ-Regler Einstellungen."""
    base_cut_rate: int = 4          # 1, 2, 4, 8, 16 Beats
    energy_reactivity: int = 50     # 0-100%
    breakdown_behavior: str = "halve"  # "halve", "force16", "none"
    vibe: str = ""                  # Keyword fuer LanceDB Suche
    manual_density_curve: list[float] | None = None
    anchors: list[dict] | None = None  # [{"time": float, "scene_id": str}, ...]


@dataclass
class TimelineSegment:
    """Ein Segment auf der OTIO-Timeline."""
    video_id: int
    video_path: str
    start: float          # Timeline-Zeitpunkt (Sekunden)
    end: float            # Timeline-Zeitpunkt (Sekunden)
    source_start: float   # Quell-Video Offset (Sekunden)
    source_end: float     # Quell-Video Ende (Sekunden)
    is_anchor: bool = False
    scene_id: str = ""


# ── Data Access ──

def _get_beat_positions(audio_id: int | None) -> list[float]:
    """Laedt die exakten Beat-Positionen aus dem Beatgrid der DB."""
    if audio_id is None:
        return []
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.beatgrid:
            return []
        bg = track.beatgrid
        if bg.beat_positions:
            try:
                positions = json.loads(bg.beat_positions)
                return [float(p) for p in positions]
            except (json.JSONDecodeError, TypeError):
                pass
        if bg.bpm and bg.bpm > 0:
            interval = 60.0 / bg.bpm
            duration = track.duration or 300.0
            t = bg.offset or 0.0
            positions = []
            while t < duration:
                positions.append(round(t, 4))
                t += interval
            return positions
    return []


def _get_downbeat_positions(audio_id: int | None) -> list[float]:
    """Laedt die Downbeat-Positionen aus der DB."""
    if audio_id is None:
        return []
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.beatgrid:
            return []
        bg = track.beatgrid
        if bg.downbeat_positions:
            try:
                return [float(p) for p in json.loads(bg.downbeat_positions)]
            except (json.JSONDecodeError, TypeError):
                pass
    return []


def _get_energy_per_beat(audio_id: int | None) -> list[float]:
    """Laedt die RMS-Energie pro Beat aus der DB."""
    if audio_id is None:
        return []
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.beatgrid:
            return []
        bg = track.beatgrid
        if bg.energy_per_beat:
            try:
                return [float(e) for e in json.loads(bg.energy_per_beat)]
            except (json.JSONDecodeError, TypeError):
                pass
    return []


@lru_cache(maxsize=64)
def _get_audio_duration(audio_id: int) -> float:
    """Gibt die Dauer des Audio-Tracks in Sekunden zurueck."""
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.duration if track and track.duration else 60.0


@lru_cache(maxsize=64)
def _get_audio_path(audio_id: int) -> str:
    """Gibt den Dateipfad des Audio-Tracks zurueck."""
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.file_path if track else ""


@lru_cache(maxsize=64)
def _get_bpm(audio_id: int | None) -> float | None:
    if audio_id is None:
        return None
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.bpm if track else None


def _get_video_info(video_ids: list[int]) -> dict[int, dict]:
    """Holt Video-Metadaten (Dauer, Pfad) fuer alle IDs. Cached intern."""
    return copy.deepcopy(_get_video_info_cached(tuple(sorted(video_ids))))


@lru_cache(maxsize=32)
def _get_video_info_cached(video_ids: tuple[int, ...]) -> dict[int, dict]:
    """Cached-Backend fuer _get_video_info (tuple ist hashable)."""
    info = {}
    if not video_ids:
        return info
    with Session(engine) as session:
        clips = session.query(VideoClip).filter(VideoClip.id.in_(video_ids)).all()
        for clip in clips:
            info[clip.id] = {
                "duration": clip.duration or 10.0,
                "path": clip.file_path,
                "scenes": [
                    {"start": s.start_time, "end": s.end_time,
                     "energy": s.energy or 0.5, "id": s.id}
                    for s in clip.scenes
                ],
            }
    return info


def _get_scenes(video_id: int | None) -> list[Scene]:
    if video_id is None:
        return []
    with Session(engine) as session:
        clip = session.get(VideoClip, video_id)
        if clip is None:
            return []
        # Eager-load scenes innerhalb der Session, sonst DetachedInstanceError nach Session-Close
        scenes = list(clip.scenes)
        return scenes


# ── Legacy Phase 2 functions (kept for backward compat) ──

def _density_to_beat_step(density: float) -> int:
    if density >= 0.8:
        return 1
    elif density >= 0.5:
        return 2
    elif density >= 0.3:
        return 4
    elif density >= 0.15:
        return 8
    else:
        return 16


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
            idx = np.searchsorted(beats_arr, scene.start_time)
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
                        strength=min(1.0, (scene.energy or 0.5) + 0.2),
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
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.stem_drums_path:
            return []
        drums_path = track.stem_drums_path
    try:
        import librosa
        y, sr = librosa.load(drums_path, sr=22050, mono=True)
    except Exception as e:
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
# Phase 3: Advanced DJ Pacing Engine
# ======================================================================

def _compute_effective_step(
    base_step: int,
    beat_index: int,
    beat_time: float,
    total_duration: float,
    energy_per_beat: list[float],
    energy_reactivity: float,
    breakdown_behavior: str,
    pacing_curve: list[float] | None,
) -> int:
    """Berechnet den effektiven Beat-Schritt fuer einen bestimmten Beat.

    Kombiniert:
    - base_cut_rate (aus UI)
    - energy_reactivity (erhoeht Cuts bei hohem RMS)
    - breakdown_behavior (reduziert Cuts bei niedrigem RMS)
    - manual_density_curve (optionale Ueberschreibung)
    """
    effective = base_step

    # 1. Pacing-Kurve (wenn vorhanden, hat hoechste Prioritaet)
    if pacing_curve and len(pacing_curve) > 0:
        curve_idx = int((beat_time / max(total_duration, 0.1)) * (len(pacing_curve) - 1))
        curve_idx = max(0, min(curve_idx, len(pacing_curve) - 1))
        density = pacing_curve[curve_idx]
        curve_step = _density_to_beat_step(density)
        # Mische Kurve mit Base: bei hoher Dichte kuerzeren Step
        if density >= 0.5:
            effective = min(base_step, curve_step)
        else:
            effective = max(base_step, curve_step)

    # 2. Energy Reactivity
    reactivity = energy_reactivity / 100.0
    if reactivity > 0 and beat_index < len(energy_per_beat):
        energy = energy_per_beat[beat_index]

        # Hohe Energie (>0.7): Step reduzieren (mehr Cuts)
        if energy > 0.7:
            speed_boost = 1.0 + (energy - 0.7) * 3.0 * reactivity  # max ~1.9x
            effective = max(1, int(effective / speed_boost))

        # Niedrige Energie (<0.3): Breakdown-Verhalten anwenden
        elif energy < 0.3:
            if breakdown_behavior == "halve":
                effective = min(16, effective * 2)
            elif breakdown_behavior == "force16":
                effective = 16
            elif breakdown_behavior == "none":
                effective = 9999  # Kein Cut

        # Mittlere Energie (0.3-0.7): Leichte Modulation
        elif 0.3 <= energy <= 0.5:
            # Leicht verlangsamen bei niedrig-mittel
            effective = min(16, int(effective * 1.5))

    return max(1, effective)


def _select_cut_beats_advanced(
    beats: list[float],
    total_duration: float,
    settings: AdvancedPacingSettings,
    energy_per_beat: list[float],
) -> list[float]:
    """Phase 3: Waehlt Cut-Beats basierend auf DJ-Reglern aus."""
    if not beats:
        return []

    selected: list[float] = []
    beats_since_last_cut = 0

    for i, beat_time in enumerate(beats):
        if beat_time >= total_duration:
            break

        step = _compute_effective_step(
            base_step=settings.base_cut_rate,
            beat_index=i,
            beat_time=beat_time,
            total_duration=total_duration,
            energy_per_beat=energy_per_beat,
            energy_reactivity=settings.energy_reactivity,
            breakdown_behavior=settings.breakdown_behavior,
            pacing_curve=settings.manual_density_curve,
        )

        beats_since_last_cut += 1
        if beats_since_last_cut >= step:
            selected.append(beat_time)
            beats_since_last_cut = 0

    return selected


def _match_video_for_segment(
    seg_start: float,
    seg_end: float,
    vibe: str,
    video_info: dict[int, dict],
    available_ids: list[int],
    clip_offsets: dict[int, float],
    used_recently: list[int],
) -> tuple[int, float]:
    """Waehlt den besten Video-Clip fuer ein Segment.

    Bei Vibe-Keyword: LanceDB Semantic Search.
    Sonst: Motion-Score oder Round-Robin mit Varianz.

    Returns: (video_id, source_start)
    """
    # LanceDB Semantic Search bei Vibe-Keyword
    if vibe and vibe.strip():
        try:
            from services.video_analysis_service import search_videos_by_text
            results = search_videos_by_text(vibe.strip(), top_k=5)
            if results:
                # Finde Video-ID aus dem Suchergebnis
                for r in results:
                    r_path = r.get("video_path", "")
                    for vid, info in video_info.items():
                        if info["path"] == r_path:
                            scene_start = r.get("scene_start", 0.0)
                            return vid, scene_start
        except Exception as e:
            logger.warning("LanceDB Suche fehlgeschlagen: %s", e)

    # Fallback: Motion-basiertes Matching
    # Berechne Audio-Energie fuer diesen Zeitpunkt (fuer Motion-Match)
    energy_value = 0.5  # Default
    # Versuche Energie aus dem Video-Kontext abzuleiten
    seg_mid = (seg_start + seg_end) / 2.0

    vid, source_start = _match_video_by_motion(
        energy_value, video_info, available_ids, used_recently,
    )
    # Fallback source_start aus clip_offsets wenn kein Scene-Match
    if source_start == 0.0:
        source_start = clip_offsets.get(vid, 0.0)
    return vid, source_start


def auto_edit_phase3(
    audio_id: int,
    video_clip_ids: list[int],
    settings: AdvancedPacingSettings,
    progress_cb=None,
) -> tuple[list[TimelineSegment], list[CutPoint]]:
    """Phase 3: DJ-Pacing Engine — OTIO-konforme Timeline-Generierung.

    ZWINGENDE REGEL: Das Audio-File diktiert die Gesamtlaenge der Timeline.

    Returns:
        (segments, cut_points) — Segmente fuer OTIO + CutPoints fuer UI-Visualisierung
    """
    # 1. Audio-Dauer = Timeline-Laenge
    if progress_cb:
        progress_cb(0, "Lade Audio-Daten...")
    total_duration = _get_audio_duration(audio_id)
    logger.info("Phase 3 Auto-Edit: Audio-Dauer = %.1fs", total_duration)

    # 2. Beats + Downbeats + Energie laden
    beats = _get_beat_positions(audio_id)
    downbeats = _get_downbeat_positions(audio_id)
    energy_per_beat = _get_energy_per_beat(audio_id)

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
        progress_cb(40, "Berechne Cut-Beats...")
    # 5. Cut-Beats berechnen (Phase 3 Algorithmus)
    cut_beats = _select_cut_beats_advanced(
        beats, total_duration, settings, energy_per_beat,
    )

    # Start immer bei 0
    if not cut_beats or cut_beats[0] > 0.01:
        cut_beats.insert(0, 0.0)
    # Ende = Audio-Dauer
    if cut_beats[-1] < total_duration - 0.1:
        cut_beats.append(total_duration)

    # Anker-Zeitpunkte einfuegen (auf naechsten Beat snappen)
    beats_arr = np.array(beats)
    for anchor_time in anchor_times:
        idx = np.argmin(np.abs(beats_arr - anchor_time))
        snapped = float(beats_arr[idx])
        if not any(abs(cb - snapped) < 0.05 for cb in cut_beats):
            cut_beats.append(snapped)
    cut_beats.sort()

    if progress_cb:
        progress_cb(60, "Erzeuge Timeline-Segmente...")
    # 6. Segmente erzeugen
    segments: list[TimelineSegment] = []
    cut_points: list[CutPoint] = []
    available_ids = [vid for vid in video_clip_ids if vid in video_info]
    if not available_ids:
        return [], []

    clip_offsets: dict[int, float] = {vid: 0.0 for vid in available_ids}
    used_recently: list[int] = []
    clip_idx = 0

    # Pre-resolve anchor scenes to avoid DB session per segment
    anchor_scene_map: dict[str, int] = {}  # scene_id_str -> video_clip_id
    if anchor_times:
        scene_ids = []
        for anchor_data in anchor_times.values():
            sid = anchor_data.get("scene_id", "")
            if sid:
                try:
                    scene_ids.append(int(sid))
                except (ValueError, TypeError):
                    pass
        if scene_ids:
            with Session(engine) as session:
                for scene in session.query(Scene).filter(Scene.id.in_(scene_ids)).all():
                    anchor_scene_map[str(scene.id)] = scene.video_clip_id

    for i in range(len(cut_beats) - 1):
        seg_start = cut_beats[i]
        seg_end = cut_beats[i + 1]
        seg_duration = seg_end - seg_start

        if seg_duration < 0.1:
            continue

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
            # Normaler Clip-Match
            vid, source_start = _match_video_for_segment(
                seg_start, seg_end, settings.vibe,
                video_info, available_ids, clip_offsets, used_recently,
            )

        vid_duration = video_info[vid]["duration"]
        vid_path = video_info[vid]["path"]

        # Intelligent looping: Reset wenn nicht genug Material
        remaining = vid_duration - source_start
        if remaining < seg_duration:
            source_start = 0.0
            clip_offsets[vid] = 0.0

        source_end = min(source_start + seg_duration, vid_duration)

        segments.append(TimelineSegment(
            video_id=vid,
            video_path=vid_path,
            start=round(seg_start, 4),
            end=round(seg_end, 4),
            source_start=round(source_start, 4),
            source_end=round(source_end, 4),
            is_anchor=is_anchor,
            scene_id=anchor_scene_id,
        ))

        # CutPoint fuer UI-Visualisierung
        source_type = "anchor" if is_anchor else "beat"
        # Energie-basierte Staerke
        beat_idx = np.searchsorted(beats_arr, seg_start)
        beat_idx = min(beat_idx, len(energy_per_beat) - 1) if energy_per_beat else 0
        strength = energy_per_beat[beat_idx] if beat_idx < len(energy_per_beat) else 0.5
        cut_points.append(CutPoint(
            time=round(seg_start, 4),
            source=source_type,
            strength=round(min(1.0, strength + 0.2), 3),
        ))

        # Offsets aktualisieren
        clip_offsets[vid] = source_start + seg_duration
        if clip_offsets[vid] >= vid_duration:
            clip_offsets[vid] = 0.0

        used_recently.append(vid)
        clip_idx += 1

    if progress_cb:
        progress_cb(100, "Timeline fertig")
    logger.info(
        "Phase 3: %d Segmente, %d CutPoints, %.1fs Gesamtdauer",
        len(segments), len(cut_points), total_duration,
    )
    return segments, cut_points


# ======================================================================
# Phase 3: Keyframe-String Generator
# ======================================================================

def _motion_category(score: float) -> str:
    """Ordnet einen RAFT-Motion-Score einer lesbaren Kategorie zu."""
    if score >= 0.8:
        return "Extrem"
    elif score >= 0.6:
        return "Action"
    elif score >= 0.3:
        return "Moderat"
    else:
        return "Ruhig"


def generate_keyframe_string(video_id: int) -> str:
    """Wandelt erkannte Video-Szenen und RAFT-Motion-Werte in einen lesbaren Text-String um.

    Format:
        [Szene 1: Ruhig (motion=0.12), Laenge: 10.3s]
          -> [Szene 2: Action (motion=0.85), Laenge: 4.1s]
    """
    with Session(engine) as session:
        clip = session.get(VideoClip, video_id)
        if not clip:
            return f"[Video {video_id}: nicht gefunden]"

        scenes = sorted(clip.scenes, key=lambda s: s.start_time)
        if not scenes:
            dur = clip.duration or 0.0
            return f"[Video '{Path(clip.file_path).stem}': Keine Szenen erkannt, Laenge: {dur:.1f}s]"

        res = f"{clip.width or '?'}x{clip.height or '?'}" if clip.width else "?"

        parts = []
        for i, scene in enumerate(scenes):
            motion = scene.energy or 0.0  # motion_score als energy gespeichert
            cat = _motion_category(motion)
            length = (scene.end_time or 0.0) - (scene.start_time or 0.0)
            part = f"[Szene {i+1}: {cat} (motion={motion:.2f}), Laenge: {length:.1f}s, {res}]"
            parts.append(part)

        video_name = Path(clip.file_path).stem
        header = f"Video: '{video_name}' ({len(scenes)} Szenen)\n"
        return header + "\n  -> ".join(parts)


def generate_keyframe_strings_for_project(project_id: int = 1) -> str:
    """Generiert Keyframe-Strings fuer ALLE Video-Clips eines Projekts."""
    with Session(engine) as session:
        clips = session.query(VideoClip).filter_by(project_id=project_id).all()
        if not clips:
            return "[Keine Video-Clips im Projekt]"
        clip_ids = [c.id for c in clips]

    all_strings = []
    for vid_id in clip_ids:
        all_strings.append(generate_keyframe_string(vid_id))

    return "\n\n".join(all_strings)


# ======================================================================
# Phase 3: Dynamisches Motion-Pacing
# ======================================================================

def _motion_adjusted_step(
    base_step: int,
    seg_start: float,
    seg_end: float,
    video_info: dict[int, dict],
    available_ids: list[int],
    energy_value: float,
) -> int:
    """Passt den Beat-Schritt dynamisch an die Motion-Werte der Video-Szenen an.

    NICHT stur nach 4 Beats schneiden! Die Schnittlaenge muss sich
    an die Energie des Songs UND die Action im Bild anpassen.
    """
    # Sammle durchschnittlichen Motion-Score aller verfuegbaren Szenen
    # die zeitlich zu diesem Segment passen koennten
    total_motion = 0.0
    motion_count = 0
    for vid in available_ids:
        scenes = video_info.get(vid, {}).get("scenes", [])
        for scene in scenes:
            total_motion += scene.get("energy", 0.5)
            motion_count += 1

    avg_motion = total_motion / motion_count if motion_count > 0 else 0.5

    # Kombination: Audio-Energie + Video-Motion bestimmen Schnittlaenge
    combined_intensity = (energy_value * 0.6 + avg_motion * 0.4)

    if combined_intensity >= 0.8:
        # Hohe Intensitaet: Sehr schnelle Schnitte (1-2 Beats)
        return max(1, base_step // 4)
    elif combined_intensity >= 0.6:
        # Mittel-hoch: Schnelle Schnitte (2 Beats)
        return max(1, base_step // 2)
    elif combined_intensity >= 0.4:
        # Mittel: Normale Schnitte (base_step)
        return base_step
    elif combined_intensity >= 0.2:
        # Ruhig: Langsame Schnitte (doppelt)
        return min(16, base_step * 2)
    else:
        # Sehr ruhig: Sehr langsame Schnitte
        return min(16, base_step * 4)


def _match_video_by_motion(
    energy_value: float,
    video_info: dict[int, dict],
    available_ids: list[int],
    used_recently: list[int],
) -> tuple[int, float]:
    """Waehlt den Video-Clip basierend auf Motion-Score passend zur Audio-Energie.

    Ruhige Szenen (motion < 0.3) fuer ruhige Audio-Abschnitte.
    Action-Szenen (motion > 0.7) fuer energetische Audio-Abschnitte.
    """
    candidates = [v for v in available_ids if v not in used_recently[-3:]]
    if not candidates:
        candidates = available_ids

    best_vid = candidates[0]
    best_score = -1.0
    best_source_start = 0.0

    for vid in candidates:
        scenes = video_info.get(vid, {}).get("scenes", [])
        if not scenes:
            continue

        for scene in scenes:
            motion = scene.get("energy", 0.5)
            # Score: Je naeher motion an energy_value, desto besser
            match_score = 1.0 - abs(motion - energy_value)
            if match_score > best_score:
                best_score = match_score
                best_vid = vid
                best_source_start = scene.get("start", 0.0)

    return best_vid, best_source_start


# ── Legacy wrapper (backward compat) ──

def auto_edit_to_beats(
    audio_id: int,
    video_clip_ids: list[int],
    total_duration: float = 60.0,
    pacing_curve: list[float] | None = None,
    tempo: int = 50,
) -> list[dict]:
    """Legacy Phase 2 wrapper — delegiert an Phase 3 Engine."""
    # Map tempo slider to base_cut_rate
    if tempo >= 80:
        rate = 1
    elif tempo >= 60:
        rate = 2
    elif tempo >= 40:
        rate = 4
    elif tempo >= 20:
        rate = 8
    else:
        rate = 16

    settings = AdvancedPacingSettings(
        base_cut_rate=rate,
        energy_reactivity=50,
        breakdown_behavior="halve",
        manual_density_curve=pacing_curve,
    )
    segments, _ = auto_edit_phase3(audio_id, video_clip_ids, settings)

    return [
        {
            "video_id": seg.video_id,
            "start": seg.start,
            "end": seg.end,
            "source_start": seg.source_start,
        }
        for seg in segments
    ]
