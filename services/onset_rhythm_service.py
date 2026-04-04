"""Onset Rhythm Intelligence Service — AUD-83.

Percussive Onset Detection mit multi-band Spectral Flux:
- Kick/Snare/HiHat Onset Detection (separate Frequenzbänder)
- Onset Strength Curve (für Visualisierung + Cut-Point Refinement)
- Syncopation Score (rhythmische Komplexität 0.0–1.0)
- Groove Template Matching (Techno, House, HipHop, DnB, etc.)
- Cut-Point Refinement (beat-aligned Schnittpunkte auf Onsets snappen)

Funktioniert auf RAW Audio (kein Stem nötig), aber nutzt den Drums-Stem
wenn verfügbar für deutlich präzisere Ergebnisse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from services.audio_constants import DEFAULT_SR, HOP_LENGTH

logger = logging.getLogger(__name__)

# ── Mel-Band Grenzen (bei N_MELS=128, sr=22050) ──────────────────────────────
# Kick:  Mel-Bins  0–20  ≈   0–250 Hz  (Low/Sub, perkussiver Impact)
# Snare: Mel-Bins 20–80  ≈ 250–4000 Hz (Mid, Crack und Body)
# HiHat: Mel-Bins 80–128 ≈ 4000–22050 Hz (High, Brillanz und Attacks)
_N_MELS = 128
_MEL_KICK_LO = 0
_MEL_KICK_HI = 20
_MEL_SNARE_LO = 20
_MEL_SNARE_HI = 80
_MEL_HIHAT_LO = 80
_MEL_HIHAT_HI = _N_MELS

# Syncopation: Onset gilt als "auf dem Beat" wenn ≤ 50ms vom nächsten Beat
_BEAT_TOLERANCE_SEC = 0.05

# ── Groove Templates: Kick/Snare-Slots auf dem 8tel-Raster (0–7) ─────────────
# Slot 0=Beat1, 2=Beat2, 4=Beat3, 6=Beat4 bei 4/4 Takt mit 8 Achteln pro Takt
GROOVE_TEMPLATES: dict[str, dict] = {
    "4on4_techno": {
        "kick": [0, 2, 4, 6],
        "snare": [2, 6],
        "description": "Techno / 4-on-the-floor",
    },
    "standard_rock": {
        "kick": [0, 4],
        "snare": [2, 6],
        "description": "Standard Rock / Pop",
    },
    "hip_hop": {
        "kick": [0, 3, 4],
        "snare": [2, 6],
        "description": "Hip-Hop / Boom Bap",
    },
    "two_step": {
        "kick": [0, 5],
        "snare": [2, 6],
        "description": "2-Step / UK Garage",
    },
    "dnb_halftime": {
        "kick": [0, 6],
        "snare": [4],
        "description": "Drum & Bass / Halftime",
    },
    "house_offbeat": {
        "kick": [0, 2, 4, 6],
        "snare": [1, 3, 5, 7],
        "description": "House / Chicago",
    },
    "trap": {
        "kick": [0, 1, 4],
        "snare": [2, 6],
        "description": "Trap / Modern Hip-Hop",
    },
    "breakbeat": {
        "kick": [0, 3],
        "snare": [2, 5],
        "description": "Breakbeat / Jungle",
    },
    "minimal_techno": {
        "kick": [0, 4],
        "snare": [2, 6],
        "description": "Minimal Techno / Microhouse",
    },
}


@dataclass
class PercussiveOnset:
    """Ein erkannter perkussiver Onset (Kick, Snare oder HiHat)."""

    time: float      # Onset-Zeitpunkt in Sekunden
    strength: float  # Relative Stärke 0.0–1.0 (normalisiert auf Track-Maximum)


@dataclass
class RhythmAnalysis:
    """Vollständige Rhythmus-Analyse eines Audio-Tracks.

    Enthält alle Ergebnisse von OnsetRhythmService.analyze():
    Multi-Band-Onsets, Strength-Curve, Syncopation, Groove-Template.
    """

    # Multi-band Drum Onsets
    onsets_kick: list[PercussiveOnset] = field(default_factory=list)
    onsets_snare: list[PercussiveOnset] = field(default_factory=list)
    onsets_hihat: list[PercussiveOnset] = field(default_factory=list)

    # Onset Strength Curve (downsampled für DB-Storage)
    onset_strength_curve: list[float] = field(default_factory=list)
    onset_strength_hop_sec: float = HOP_LENGTH / DEFAULT_SR

    # Rhythmus-Metriken
    syncopation_score: float = 0.0   # 0.0 = gerade, 1.0 = maximal synkopiert
    groove_template: str = "unknown"
    groove_confidence: float = 0.0

    # Swing-Ratio
    swing_ratio: float = 0.5  # 0.5 = straight, 0.67 = Triplet-Swing


class OnsetRhythmService:
    """Percussive Onset Detection + Rhythmus-Analyse.

    Implementiert multi-band Spectral Flux Onset Detection für präzise
    Kick/Snare/HiHat-Erkennung. Berechnet Syncopation-Score und matched
    Groove-Templates für genre-spezifisches Editing.

    Verwendung:
        service = OnsetRhythmService()
        analysis = service.analyze(y, sr, beats)
        refined_cuts = service.refine_cut_points(cut_times, analysis)
    """

    HOP_LENGTH = HOP_LENGTH
    N_MELS = _N_MELS

    def analyze(
        self,
        y: np.ndarray,
        sr: int,
        beats: list[float],
        drums_y: np.ndarray | None = None,
    ) -> RhythmAnalysis:
        """Analysiert Audio und extrahiert Rhythmus-Informationen.

        Args:
            y: Raw Audio-Signal (mono, float32/float64)
            sr: Sample-Rate
            beats: Beat-Positionen in Sekunden (vom BeatAnalysisService)
            drums_y: Optional: isolierter Drums-Stem (verbessert Genauigkeit)

        Returns:
            RhythmAnalysis mit Onsets, Strength-Curve, Syncopation, Groove
        """
        import librosa

        signal = drums_y if drums_y is not None else y

        # Mel-Spektrogramm einmalig berechnen (für alle Bänder wiederverwendet)
        S = librosa.feature.melspectrogram(
            y=signal,
            sr=sr,
            n_mels=self.N_MELS,
            hop_length=self.HOP_LENGTH,
            n_fft=2048,
        )
        S_db = librosa.power_to_db(S, ref=np.max)

        # Multi-Band Onset Detection
        onsets_kick = self._detect_band_onsets(
            S_db, sr, _MEL_KICK_LO, _MEL_KICK_HI,
        )
        onsets_snare = self._detect_band_onsets(
            S_db, sr, _MEL_SNARE_LO, _MEL_SNARE_HI,
        )
        onsets_hihat = self._detect_band_onsets(
            S_db, sr, _MEL_HIHAT_LO, _MEL_HIHAT_HI,
        )

        # Globale Onset-Strength-Curve (kombiniert alle Bänder)
        onset_env = librosa.onset.onset_strength(
            S=S_db, sr=sr, hop_length=self.HOP_LENGTH,
        )
        max_env = float(onset_env.max()) if onset_env.max() > 0 else 1.0
        # Downsample: jeder 4. Frame (~93ms Auflösung bei sr=22050, hop=512)
        curve_decimated = onset_env[::4] / max_env
        strength_curve = [round(float(v), 4) for v in curve_decimated]

        # Syncopation Score (Kick + Snare Onsets relativ zu Beat-Grid)
        kick_snare_times = [o.time for o in onsets_kick + onsets_snare]
        syncopation = self._compute_syncopation(kick_snare_times, beats)

        # Groove Template Matching
        template_name, template_conf = self._match_groove_template(
            onsets_kick, onsets_snare, beats,
        )

        # Swing-Ratio
        swing = self._compute_swing_ratio(onsets_kick + onsets_snare, beats)

        logger.info(
            "RhythmAnalysis: kick=%d snare=%d hihat=%d syncopation=%.3f "
            "groove=%s(%.2f) swing=%.3f",
            len(onsets_kick), len(onsets_snare), len(onsets_hihat),
            syncopation, template_name, template_conf, swing,
        )

        return RhythmAnalysis(
            onsets_kick=onsets_kick,
            onsets_snare=onsets_snare,
            onsets_hihat=onsets_hihat,
            onset_strength_curve=strength_curve,
            onset_strength_hop_sec=round(self.HOP_LENGTH / sr * 4, 6),
            syncopation_score=round(syncopation, 4),
            groove_template=template_name,
            groove_confidence=round(template_conf, 4),
            swing_ratio=round(swing, 4),
        )

    # ── Band-Onset Detection ──────────────────────────────────────────────────

    def _detect_band_onsets(
        self,
        S_db: np.ndarray,
        sr: int,
        mel_lo: int,
        mel_hi: int,
    ) -> list[PercussiveOnset]:
        """Erkennt Onsets im angegebenen Mel-Frequenzband per Spectral Flux."""
        import librosa

        band = S_db[mel_lo:mel_hi, :]
        if band.shape[0] == 0:
            return []

        onset_env = librosa.onset.onset_strength(
            S=band, sr=sr, hop_length=self.HOP_LENGTH,
        )
        if onset_env.max() <= 0:
            return []

        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=self.HOP_LENGTH,
            backtrack=True,
            units="frames",
        )
        if len(onset_frames) == 0:
            return []

        times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=self.HOP_LENGTH)
        max_strength = float(onset_env.max())

        return [
            PercussiveOnset(
                time=round(float(t), 4),
                strength=round(
                    float(onset_env[f]) / max_strength if f < len(onset_env) else 0.5,
                    4,
                ),
            )
            for f, t in zip(onset_frames, times)
        ]

    # ── Syncopation Score ─────────────────────────────────────────────────────

    def _compute_syncopation(
        self,
        onset_times: list[float],
        beats: list[float],
    ) -> float:
        """Berechnet Syncopation-Score: Anteil der Onsets zwischen den Beats.

        Score 0.0 = alle Onsets exakt auf den Beats (gerader Groove)
        Score 1.0 = alle Onsets zwischen den Beats (maximale Synkopierung)
        """
        if not onset_times or not beats or len(beats) < 2:
            return 0.0

        beats_arr = np.array(beats, dtype=float)
        t_min = float(beats_arr[0]) - 0.1
        t_max = float(beats_arr[-1]) + 0.1

        total = 0
        syncopated = 0

        for t in onset_times:
            if t < t_min or t > t_max:
                continue
            total += 1
            idx = int(np.argmin(np.abs(beats_arr - t)))
            if abs(float(beats_arr[idx]) - t) > _BEAT_TOLERANCE_SEC:
                syncopated += 1

        return syncopated / total if total > 0 else 0.0

    # ── Groove Template Matching ──────────────────────────────────────────────

    def _match_groove_template(
        self,
        kicks: list[PercussiveOnset],
        snares: list[PercussiveOnset],
        beats: list[float],
    ) -> tuple[str, float]:
        """Vergleicht erkannte Kick/Snare-Verteilung mit Groove-Templates.

        Projiziert Onsets auf ein 8tel-Raster (n_slots=8 pro Takt) und
        berechnet Cosine-Ähnlichkeit mit jedem Template.

        Returns:
            (template_name, confidence): Bestes Template und Ähnlichkeitswert
        """
        if not beats or len(beats) < 4:
            return "unknown", 0.0

        n_slots = 8
        intervals = np.diff(beats)
        beat_dur = float(np.median(intervals))
        bar_dur = beat_dur * 4
        eighth_dur = bar_dur / n_slots

        kick_hist = np.zeros(n_slots, dtype=float)
        snare_hist = np.zeros(n_slots, dtype=float)

        for onset in kicks:
            slot = int((onset.time % bar_dur) / eighth_dur) % n_slots
            kick_hist[slot] += onset.strength

        for onset in snares:
            slot = int((onset.time % bar_dur) / eighth_dur) % n_slots
            snare_hist[slot] += onset.strength

        if kick_hist.sum() > 0:
            kick_hist /= kick_hist.sum()
        if snare_hist.sum() > 0:
            snare_hist /= snare_hist.sum()

        best_name = "unknown"
        best_score = 0.0

        for name, template in GROOVE_TEMPLATES.items():
            t_kick = np.zeros(n_slots, dtype=float)
            t_snare = np.zeros(n_slots, dtype=float)
            for slot in template.get("kick", []):
                if slot < n_slots:
                    t_kick[slot] = 1.0
            for slot in template.get("snare", []):
                if slot < n_slots:
                    t_snare[slot] = 1.0
            if t_kick.sum() > 0:
                t_kick /= t_kick.sum()
            if t_snare.sum() > 0:
                t_snare /= t_snare.sum()

            score = 0.6 * _cosine_sim(kick_hist, t_kick) + 0.4 * _cosine_sim(
                snare_hist, t_snare
            )
            if score > best_score:
                best_score = score
                best_name = name

        return best_name, best_score

    # ── Swing-Ratio ───────────────────────────────────────────────────────────

    def _compute_swing_ratio(
        self,
        onsets: list[PercussiveOnset],
        beats: list[float],
    ) -> float:
        """Berechnet Swing-Ratio aus Offbeat-Onset-Positionen.

        0.5 = Straight (gerade Achtel)
        0.67 = Triplet-Swing (Shuffle)
        >0.67 = starker Swing

        Methode: Betrachtet nur Onsets auf der "And"-Position (Offbeats)
        und misst deren normalisierte Position im Beat-Intervall.
        """
        if not beats or len(beats) < 4 or not onsets:
            return 0.5

        beats_arr = np.array(beats, dtype=float)
        beat_dur = float(np.median(np.diff(beats_arr)))
        if beat_dur <= 0:
            return 0.5

        positions = []
        for onset in onsets:
            if onset.time < float(beats_arr[0]) or onset.time > float(beats_arr[-1]):
                continue
            idx = int(np.searchsorted(beats_arr, onset.time, side="right")) - 1
            if idx < 0 or idx >= len(beats_arr) - 1:
                continue
            pos = (onset.time - float(beats_arr[idx])) / beat_dur
            # Nur echte Offbeat-Positionen (30%–70% des Beat-Intervalls)
            if 0.3 < pos < 0.7:
                positions.append(pos)

        if not positions:
            return 0.5
        return round(float(np.median(positions)), 4)

    # ── Cut-Point Refinement ──────────────────────────────────────────────────

    def refine_cut_points(
        self,
        cut_times: list[float],
        analysis: RhythmAnalysis,
        window_sec: float = 0.08,
        min_onset_strength: float = 0.4,
    ) -> list[float]:
        """Snappe Beat-aligned Cut-Zeitpunkte auf den nächsten starken Onset.

        Verbessert die Präzision von Schnittpunkten indem sie zum nächsten
        starken Kick oder Snare Onset innerhalb eines Zeitfensters gezogen
        werden. Cuts ohne starken Onset in der Nähe bleiben unverändert.

        Args:
            cut_times: Beat-aligned Schnittpunkte (von calculate_cut_points)
            analysis: RhythmAnalysis Ergebnis von analyze()
            window_sec: Maximales Snap-Fenster in Sekunden (Standard: 80ms)
            min_onset_strength: Minimale Onset-Stärke für Snapping

        Returns:
            Verfeinerte Schnittpunkte, zeitlich sortiert, ohne Duplikate
        """
        strong_onsets = sorted(
            [
                o
                for o in (analysis.onsets_kick + analysis.onsets_snare)
                if o.strength >= min_onset_strength
            ],
            key=lambda o: o.time,
        )

        if not strong_onsets:
            return list(cut_times)

        onset_arr = np.array([o.time for o in strong_onsets], dtype=float)
        refined: list[float] = []

        for cut_t in cut_times:
            dists = np.abs(onset_arr - cut_t)
            nearest_idx = int(np.argmin(dists))
            if float(dists[nearest_idx]) <= window_sec:
                refined.append(round(float(onset_arr[nearest_idx]), 4))
            else:
                refined.append(round(cut_t, 4))

        # Deduplizieren (kann durch Snapping entstehen)
        seen: set[float] = set()
        result: list[float] = []
        for t in refined:
            if t not in seen:
                seen.add(t)
                result.append(t)

        return sorted(result)

    # ── DB-Integration ────────────────────────────────────────────────────────

    def analyze_and_store(
        self,
        track_id: int,
        progress_cb=None,
    ) -> RhythmAnalysis | None:
        """Analysiert einen AudioTrack und speichert Ergebnisse im Beatgrid.

        Lädt Audio (+ optionalen Drums-Stem), analysiert Rhythmus und
        persistiert Onset-Daten, Syncopation-Score und Groove-Template
        in der beatgrids-Tabelle.

        Voraussetzung: Beatgrid muss bereits existieren (BeatAnalysisService
        muss vorher auf diesem Track gelaufen sein).

        Args:
            track_id: AudioTrack.id aus der DB
            progress_cb: Optional Callback(percent, message)

        Returns:
            RhythmAnalysis oder None bei Fehler
        """
        import librosa
        from database import engine, AudioTrack
        from sqlalchemy.orm import Session

        if progress_cb:
            progress_cb(0, "Lade Audio für Rhythmus-Analyse...")

        with Session(engine) as session:
            track = session.get(AudioTrack, track_id)
            if track is None:
                logger.warning("OnsetRhythmService: AudioTrack %d nicht gefunden", track_id)
                return None
            audio_path = track.file_path
            drums_path = track.stem_drums_path

        try:
            y, sr = librosa.load(audio_path, sr=DEFAULT_SR, mono=True)
        except (OSError, IOError, ValueError) as e:
            logger.error("Audio-Load fehlgeschlagen '%s': %s", audio_path, e)
            return None

        drums_y: np.ndarray | None = None
        if drums_path and Path(drums_path).exists():
            try:
                drums_y, _ = librosa.load(drums_path, sr=DEFAULT_SR, mono=True)
                logger.debug("Drums-Stem geladen: %s", drums_path)
            except (OSError, IOError, ValueError) as e:
                logger.warning("Drums-Stem load fehlgeschlagen '%s': %s", drums_path, e)

        # Beat-Positionen aus DB
        from services.pacing_beat_grid import _get_beat_positions
        beats = _get_beat_positions(track_id)

        if progress_cb:
            progress_cb(20, "Spectral Flux Onset Detection...")

        analysis = self.analyze(y, sr, beats, drums_y=drums_y)

        if progress_cb:
            progress_cb(85, "Speichere Onset-Daten in DB...")

        self._store(track_id, analysis)

        if progress_cb:
            progress_cb(100, "Rhythmus-Analyse abgeschlossen")

        return analysis

    def _store(self, track_id: int, analysis: RhythmAnalysis) -> None:
        """Persistiert Onset-Daten im Beatgrid-Eintrag der DB."""
        from database import Beatgrid, nullpool_session

        kick_json = json.dumps([[o.time, o.strength] for o in analysis.onsets_kick])
        snare_json = json.dumps([[o.time, o.strength] for o in analysis.onsets_snare])
        hihat_json = json.dumps([[o.time, o.strength] for o in analysis.onsets_hihat])

        with nullpool_session() as session:
            bg = session.query(Beatgrid).filter_by(audio_track_id=track_id).first()
            if bg is None:
                logger.warning(
                    "OnsetRhythmService: Kein Beatgrid für track_id=%d — "
                    "bitte BeatAnalysisService zuerst ausführen",
                    track_id,
                )
                return

            bg.onset_kick_data = kick_json
            bg.onset_snare_data = snare_json
            bg.onset_hihat_data = hihat_json
            bg.syncopation_score = analysis.syncopation_score
            bg.groove_template = analysis.groove_template
            session.commit()

        logger.info(
            "OnsetRhythmService gespeichert: track_id=%d kick=%d snare=%d hihat=%d "
            "syncopation=%.3f groove=%s",
            track_id,
            len(analysis.onsets_kick),
            len(analysis.onsets_snare),
            len(analysis.onsets_hihat),
            analysis.syncopation_score,
            analysis.groove_template,
        )

    def load_from_db(self, track_id: int) -> RhythmAnalysis | None:
        """Lädt gespeicherte Onset-Daten aus der DB (ohne Re-Analyse).

        Returns:
            RhythmAnalysis aus Cache oder None wenn nicht vorhanden
        """
        from database import engine, Beatgrid
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            bg = session.query(Beatgrid).filter_by(audio_track_id=track_id).first()
            if bg is None:
                return None

            if not bg.onset_kick_data:
                return None

            try:
                kick_raw = json.loads(bg.onset_kick_data or "[]")
                snare_raw = json.loads(bg.onset_snare_data or "[]")
                hihat_raw = json.loads(bg.onset_hihat_data or "[]")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Onset-Daten konnten nicht geladen werden: %s", e)
                return None

            return RhythmAnalysis(
                onsets_kick=[PercussiveOnset(time=r[0], strength=r[1]) for r in kick_raw],
                onsets_snare=[PercussiveOnset(time=r[0], strength=r[1]) for r in snare_raw],
                onsets_hihat=[PercussiveOnset(time=r[0], strength=r[1]) for r in hihat_raw],
                syncopation_score=float(bg.syncopation_score or 0.0),
                groove_template=bg.groove_template or "unknown",
            )


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine-Ähnlichkeit zwischen zwei numpy-Vektoren."""
    norm_a = float(np.linalg.norm(a))
    norm_b = float(np.linalg.norm(b))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def get_strong_onsets_for_cut_refinement(
    track_id: int,
    min_strength: float = 0.4,
) -> list[float]:
    """Gibt starke Kick+Snare-Onsets für Cut-Refinement zurück (DB-Lookup).

    Convenience-Funktion für pacing_service.py Integration.
    Lädt gecachte Onset-Daten aus der DB ohne Re-Analyse.

    Returns:
        Sortierte Liste von Onset-Zeitpunkten in Sekunden
    """
    svc = OnsetRhythmService()
    analysis = svc.load_from_db(track_id)
    if analysis is None:
        return []

    strong = [
        o.time
        for o in (analysis.onsets_kick + analysis.onsets_snare)
        if o.strength >= min_strength
    ]
    return sorted(strong)
