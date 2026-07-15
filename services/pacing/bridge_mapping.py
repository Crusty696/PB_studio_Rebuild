"""P1.1 / Cycle 11: Mapping zwischen `auto_edit_phase3` Cut-Loop und
`PacingPipeline.select_best`.

Pure Funktionen — keine DB-Calls, keine GPU-Direktzugriffe. Caller muss
die DB-Daten (audio_track, scenes, clip_offsets, ...) bereits aufgelöst
übergeben.

Wird von `services/pacing/bridge.py:maybe_use_studio_brain_pipeline()`
konsumiert, sobald das Feature-Flag aktiv ist.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import logging

import numpy as np

from services.pacing.scorer import AudioContext, ClipFeatures


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _safe_attr(obj, name, default=None):
    return getattr(obj, name, default)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AVPacingCurves:
    """Vorgeladene AV-Pacing-Kurven eines Tracks (aus ``av_pacing_data``).

    Reiner Daten-Container, damit ``build_audio_context`` pure bleiben kann.
    Gefuellt von ``load_av_pacing_curves`` — einmal pro Track, nicht pro
    Cut-Punkt.

    ``spectral_flux`` wird beim Laden auf 0..1 normiert (Rohwerte sind
    unbeschraenkt); ``stereo_width``/``percussive_ratio`` liegen bereits in
    0..1. ``spectral_centroid`` (Hz) wird hier nicht gemappt — dafuer gibt es
    noch keinen Scorer-Term.
    """

    hop_sec: float
    spectral_flux: list[float]
    stereo_width: list[float]
    percussive_ratio: list[float]
    # RMS liegt in voller 0.1s-Aufloesung vor und hat damit ein ANDERES Raster
    # als die drei Kurven oben (0.4s) -> eigenes Hop-Feld.
    rms_hop_sec: float = 0.0
    rms_curve: tuple[float, ...] = ()

    def rms_window(self, t_sec: float, max_sec: float = 60.0):
        """RMS-Fenster ab dem Cut-Punkt als np.ndarray (oder None).

        Gegenstueck ist ``ClipFeatures.motion_curve`` (Motion des Clip-
        Kandidaten ab seinem Offset). ``align_lengths`` in
        ``services/pacing/audio_video_curves`` kuerzt beide auf die kuerzere
        Laenge — verglichen wird also genau die Clip-Dauer ab dem Cut-Punkt.
        Deshalb hier ein Fenster AB ``t_sec`` (nicht der ganze Track: sonst
        wuerde align_lengths den Track-Anfang gegen den Clip halten).

        ``max_sec`` deckelt die Fensterlaenge — Clips sind kuerzer, und ein
        ungedeckeltes Fenster wuerde bei langen Tracks unnoetig grosse Arrays
        kopieren.
        """
        if not self.rms_curve or self.rms_hop_sec <= 0:
            return None
        start = max(0, int(t_sec / self.rms_hop_sec))
        if start >= len(self.rms_curve):
            return None
        end = start + max(1, int(max_sec / self.rms_hop_sec))
        return np.asarray(self.rms_curve[start:end], dtype=np.float32)

    def at(self, t_sec: float) -> tuple[float | None, float | None, float | None]:
        """Snapshot (flux, width, percussive) zum Zeitpunkt ``t_sec``."""
        if self.hop_sec <= 0 or not self.spectral_flux:
            return (None, None, None)
        idx = int(t_sec / self.hop_sec)
        if idx < 0:
            idx = 0

        def _pick(seq):
            if not seq:
                return None
            return _clamp01(float(seq[min(idx, len(seq) - 1)]))

        return (_pick(self.spectral_flux), _pick(self.stereo_width),
                _pick(self.percussive_ratio))


def load_av_pacing_curves(session, audio_track_id: int) -> "AVPacingCurves | None":
    """Laedt die AV-Pacing-Kurven eines Tracks — EINMAL, vor dem Cut-Loop.

    Bewusst als column-select (kein ORM-Voll-Laden): die Zeitreihen sind gross,
    und ``AudioTrack.av_pacing_data`` ist ``lazy='select'``, damit sie nicht bei
    jedem Track-Laden mitkommen (B-090). Hier werden sie gezielt geholt.

    Returns:
        ``AVPacingCurves`` oder None wenn der Track keine Daten hat (Analyse
        aelter als die Stage, oder Stage fehlgeschlagen). None ist ein
        regulaerer Zustand — der Scorer faellt dann auf seine Bestands-Terme
        zurueck.
    """
    try:
        from sqlalchemy import select

        from database import AVPacingData
    except ImportError:
        return None
    try:
        row = session.execute(
            select(
                AVPacingData.hop_sec,
                AVPacingData.spectral_flux,
                AVPacingData.stereo_width,
                AVPacingData.percussive_ratio,
                AVPacingData.rms_hop_sec,
                AVPacingData.rms_curve,
            ).where(AVPacingData.audio_track_id == audio_track_id)
        ).first()
    except Exception as e:  # noqa: BLE001
        logger.debug("load_av_pacing_curves(track=%s) fehlgeschlagen: %s",
                     audio_track_id, e)
        return None
    if row is None:
        return None

    hop_sec, flux, width, perc, rms_hop_sec, rms_curve = row
    flux = list(flux or [])
    # spectral_flux ist unbeschraenkt (Norm der Magnitude-Differenzen) —
    # auf 0..1 normieren, sonst clampt at() alles > 1.0 auf 1.0 platt.
    if flux:
        peak = max(flux)
        if peak > 1e-9:
            flux = [v / peak for v in flux]
    return AVPacingCurves(
        hop_sec=float(hop_sec or 0.0),
        spectral_flux=flux,
        stereo_width=list(width or []),
        percussive_ratio=list(perc or []),
        # RMS bleibt roh — cosine_similarity_curves ist skaleninvariant, und
        # eine Normierung ueber den ganzen Track wuerde leise Passagen
        # kuenstlich anheben.
        rms_hop_sec=float(rms_hop_sec or 0.0),
        rms_curve=tuple(rms_curve or ()),
    )


def build_audio_context(
    seg_start_sec: float,
    seg_section_type: str | None,
    audio_track,
    beats,
    energy_per_beat: Iterable[float] | None,
    stem_energies: dict | None = None,
    dominant_stem: str | None = None,
    av_pacing: "AVPacingCurves | None" = None,
) -> AudioContext:
    """Baut einen AudioContext-Snapshot für einen Cut-Punkt.

    Args:
        seg_start_sec: Cut-Zeitpunkt in Sekunden.
        seg_section_type: Section-Name aus structure_detection
            ("intro", "drop", ...). Wird auf lowercase gemappt.
        audio_track: ORM-AudioTrack mit Attributen bpm/key/mood/genre/...
        beats: Beat-Timestamps (np.ndarray oder Liste).
        energy_per_beat: Energie pro Beat (gleich lang wie beats), oder None.
        av_pacing: Vorgeladene AV-Pacing-Kurven (``load_av_pacing_curves``),
            oder None. Wird als Parameter hereingereicht statt aus
            ``audio_track.av_pacing_data`` gelesen: diese Funktion ist pure
            (keine DB-Calls), und die Relationship ist ``lazy='select'`` — ein
            Attribut-Zugriff hier wuerde pro Cut-Punkt eine versteckte Query
            ausloesen bzw. bei geschlossener Session scheitern.

    Returns:
        AudioContext-Dataclass mit allen at_*-Feldern.
    """
    energy_list = list(energy_per_beat) if energy_per_beat is not None else []

    # Beat-Index per binär-Suche
    beats_arr = np.asarray(beats, dtype=np.float64)
    if beats_arr.size == 0:
        beat_idx = 0
    else:
        beat_idx = int(np.searchsorted(beats_arr, seg_start_sec, side="right") - 1)
        beat_idx = max(0, beat_idx)

    if energy_list:
        clamped = min(beat_idx, len(energy_list) - 1)
        energy_val = _clamp01(float(energy_list[clamped]))
    else:
        energy_val = None

    # Harmonic-Tension: Cycle 14 Option A — Reihenfolge der Quellen:
    # 1. Skalar-Spalte audio_track.harmonic_tension (neue Migration b2c3d4e5f6a7)
    # 2. Curve[beat_idx] aus harmonic_tension_curve
    # 3. Energy-basierte Heuristik
    track_tension = _safe_attr(audio_track, "harmonic_tension", None)
    if track_tension is None:
        tension_curve = _safe_attr(audio_track, "harmonic_tension_curve", None)
        if tension_curve and energy_list:
            try:
                idx_in_curve = min(beat_idx, len(tension_curve) - 1)
                track_tension = float(tension_curve[idx_in_curve])
            except (TypeError, IndexError, ValueError):
                track_tension = None
    if track_tension is not None:
        tension = _clamp01(float(track_tension))
    elif energy_val is not None:
        # Heuristik: Tension steigt ab energy >= 0.5 stärker als linear
        tension = _clamp01(energy_val ** 0.85)
    else:
        tension = None

    section_lower = seg_section_type.strip().lower() if seg_section_type else None

    # AV-Pacing-Snapshot am Cut-Zeitpunkt. av_pacing=None (kein Datensatz oder
    # Aufrufer reicht nichts durch) -> alle drei Felder None -> Scorer nutzt
    # seine Fallback-Terme.
    if av_pacing is not None:
        at_flux, at_width, at_perc = av_pacing.at(float(seg_start_sec))
        at_rms = av_pacing.rms_window(float(seg_start_sec))
    else:
        at_flux = at_width = at_perc = None
        at_rms = None

    # Cycle 14 Option A: groove_template lebt auf Beatgrid (FK von AudioTrack),
    # nicht direkt auf AudioTrack. Beatgrid wird via lazy='joined' eager
    # geladen, also ist .beatgrid.groove_template ohne extra-Query verfügbar.
    groove_template = None
    beatgrid = _safe_attr(audio_track, "beatgrid", None)
    if beatgrid is not None:
        groove_template = _safe_attr(beatgrid, "groove_template", None)

    return AudioContext(
        at_timestamp_sec=float(seg_start_sec),
        at_beat_idx=beat_idx if energy_list else None,
        at_section_type=section_lower,
        at_bpm=_safe_attr(audio_track, "bpm", None),
        at_energy=energy_val,
        at_key=_safe_attr(audio_track, "key", None),
        at_key_confidence=_safe_attr(audio_track, "key_confidence", None),
        at_harmonic_tension=tension,
        at_mood_audio=_safe_attr(audio_track, "mood", None),
        at_mood_video=_safe_attr(audio_track, "mood", None),
        at_genre=_safe_attr(audio_track, "genre", None),
        at_sub_genre=_safe_attr(audio_track, "sub_genre", None),
        at_spectral_hash=_safe_attr(audio_track, "spectral_hash", None),
        at_groove_template=groove_template,
        at_lufs=_safe_attr(audio_track, "lufs", None),
        # NEUBAU-VOLLINTEGRATION T2.5.4: Stem-Kontext + Audio-Mood-Vektor.
        # audio_mood_vector braucht Shot-Klassen-Centroids (SigLIP-Text,
        # prozess-gecacht); ohne Centroids/Stems bleiben die Felder None
        # und der Scorer nutzt seine Fallback-Terme.
        at_stem_energies=stem_energies,
        at_dominant_stem=dominant_stem,
        at_audio_mood_vec=_build_audio_mood_vec(stem_energies, section_lower),
        # AV-Pacing (av_pacing_data): Klangfarben-Aenderungsrate, Stereo-Breite
        # und Perkussivitaet am Cut-Punkt.
        at_spectral_flux=at_flux,
        at_stereo_width=at_width,
        at_percussive_ratio=at_perc,
        # RMS-Fenster ab dem Cut-Punkt: aktiviert in scorer.score() den
        # kurvenbasierten Energy-Match gegen ClipFeatures.motion_curve
        # (statt des skalaren energy_match) — sobald beide Kurven vorliegen.
        at_rms_curve=at_rms,
    )


def _build_audio_mood_vec(stem_energies: dict | None, section_type: str | None):
    if not stem_energies:
        return None
    try:
        from services.pacing.audio_mood_vector import compute_audio_mood_vector
        from services.pacing.shot_centroids import get_shot_class_centroids
        centroids = get_shot_class_centroids()
        if not centroids:
            return None
        vec = compute_audio_mood_vector(stem_energies, section_type, centroids)
        return vec
    except Exception as exc:  # defensiv: Kontextbau darf nie crashen
        logger.debug("audio_mood_vec nicht berechenbar: %s", exc)
        return None


def build_motion_curve(
    scenes: Iterable[dict] | None,
    offset_sec: float = 0.0,
    window_sec: float = 60.0,
):
    """Motion-Kurve eines Clips ab ``offset_sec`` auf dem 100ms-Grid.

    Gegenstueck zu ``AVPacingCurves.rms_window``: beide starten an der Stelle,
    die als Naechstes zu sehen/hoeren waere (Clip-Offset bzw. Cut-Punkt), und
    ``align_lengths`` in ``audio_video_curves`` kuerzt sie auf die kuerzere
    Laenge. So vergleicht ``compute_energy_match_reward`` genau das Material,
    das tatsaechlich nebeneinander laufen wuerde.

    Nutzt bewusst ``compute_motion_curve_from_scenes`` statt eigener
    Bin-Logik. Die Szenen kommen hier als Dicts (``start``/``end``/
    ``motion_score``) aus ``video_info[vid]["scenes"]``, die Funktion erwartet
    Objekt-Attribute (``start_time``/``end_time``) -> duenner Adapter.

    Returns:
        np.ndarray (float32) oder None, wenn keine brauchbaren Szenen.
    """
    if not scenes:
        return None
    try:
        from types import SimpleNamespace

        from services.pacing.audio_video_curves import (
            DEFAULT_BIN_MS,
            compute_motion_curve_from_scenes,
        )
    except ImportError:
        return None

    infos = []
    max_end = 0.0
    for s in scenes:
        try:
            start = float(s.get("start", 0.0) or 0.0)
            end = float(s.get("end", 0.0) or 0.0)
        except (AttributeError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        score = s.get("motion_score")
        if score is None:
            score = s.get("energy")
        try:
            score = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            score = 0.0
        infos.append(SimpleNamespace(start_time=start, end_time=end,
                                     motion_score=score))
        max_end = max(max_end, end)
    if not infos or max_end <= 0.0:
        return None

    bin_sec = DEFAULT_BIN_MS / 1000.0
    full = compute_motion_curve_from_scenes(infos, max_end, DEFAULT_BIN_MS)
    start_idx = max(0, int(float(offset_sec) / bin_sec))
    if start_idx >= len(full):
        return None
    end_idx = start_idx + max(1, int(float(window_sec) / bin_sec))
    return full[start_idx:end_idx]


def build_clip_features(
    video_clip_id: int,
    scene,
    scenes: Iterable[dict] | None = None,
    offset_sec: float = 0.0,
) -> ClipFeatures:
    """Baut ClipFeatures aus einer (anchor-)Scene + Video-Clip-ID.

    Args:
        video_clip_id: ID des VideoClips (FK).
        scene: ORM-Scene oder Stub mit Feldern id/motion_score/energy/
            ai_mood/role/style_bucket_id/embedding.
        scenes: Optional ALLE Szenen des Clips (Dicts mit start/end/
            motion_score) fuer die Motion-Kurve. None -> ``motion_curve``
            bleibt None und der Scorer nutzt den skalaren energy_match.
        offset_sec: Abspiel-Offset im Clip — ab hier startet die Motion-Kurve.

    Returns:
        ClipFeatures-Dataclass für PacingPipeline.
    """
    scene_id = int(_safe_attr(scene, "id", 0))

    # Motion-Score: bevorzugt scene.motion_score, sonst scene.energy
    raw_motion = _safe_attr(scene, "motion_score", None)
    if raw_motion is None:
        raw_motion = _safe_attr(scene, "energy", 0.5)
    motion = _clamp01(float(raw_motion))

    role = _safe_attr(scene, "role", None) or "unknown"
    mood = _safe_attr(scene, "ai_mood", None) or _safe_attr(scene, "mood_refined", None) or "unknown"
    bucket = _safe_attr(scene, "style_bucket_id", None)
    if bucket is None:
        bucket = 0  # Sentinel für unbekannten Style-Bucket

    embedding = _safe_attr(scene, "embedding", None)
    # Falls embedding bytes/list ist, in np.float32-Array wandeln
    if embedding is not None and not isinstance(embedding, np.ndarray):
        try:
            embedding = np.asarray(embedding, dtype=np.float32)
        except (TypeError, ValueError):
            embedding = None

    # NEUBAU-VOLLINTEGRATION T2.5.5 (FR-S2-1): Shot-Klassen-Konfidenzen.
    # Entweder vom Caller vorberechnet (scene.shot_confidences) oder — wenn
    # ein Embedding + Centroids vorliegen — hier on-the-fly klassifiziert.
    shot_conf = _safe_attr(scene, "shot_confidences", None)
    if shot_conf is None and embedding is not None:
        try:
            from services.pacing.shot_centroids import get_shot_class_centroids
            from services.pacing.shot_type_classifier import classify
            _cents = get_shot_class_centroids()
            if _cents:
                shot_conf = classify(embedding, _cents)
        except Exception as exc:  # defensiv: Feature-Bau darf nie crashen
            logger.debug("shot_confidences nicht berechenbar: %s", exc)
            shot_conf = None

    return ClipFeatures(
        clip_id=int(video_clip_id),
        scene_id=scene_id,
        role=str(role),
        mood_refined=str(mood),
        style_bucket_id=int(bucket),
        motion_score=motion,
        embedding=embedding,
        shot_confidences=shot_conf,
        # Aktiviert zusammen mit AudioContext.at_rms_curve den kurvenbasierten
        # Energy-Match (scorer.score) statt des skalaren energy_match.
        motion_curve=build_motion_curve(scenes, offset_sec),
    )
