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


# B-736: Fenster fuer die Drum-Onset-Abfrage am Cut-Punkt. 120 ms entspricht
# etwa einer Sechzehntel bei 125 BPM — eng genug, dass ein Kick zwei Beats
# spaeter nicht mehr durchschlaegt, weit genug, dass ein leicht vor dem Grid
# gespielter Kick noch zaehlt.
_ONSET_WINDOW_SEC: float = 0.12
# Fenster fuer die lokale Onset-Dichte: ~1 Takt bei 120 BPM (2 s), also die
# Zeitspanne, die ein Zuschauer als "gerade jetzt" wahrnimmt.
_DENSITY_WINDOW_SEC: float = 1.0


def _nearest_distance(sorted_times: np.ndarray, t: float) -> float:
    """Abstand von ``t`` zum naechstgelegenen Wert in ``sorted_times`` (s)."""
    idx = int(np.searchsorted(sorted_times, t))
    best = float("inf")
    if idx < sorted_times.size:
        best = abs(float(sorted_times[idx]) - t)
    if idx > 0:
        best = min(best, abs(float(sorted_times[idx - 1]) - t))
    return best


def _onset_energy_at(arr: np.ndarray, t: float, window: float) -> float:
    """Staerkster Onset im Fenster ``t +/- window`` aus einem (N,2)-Array.

    ``arr`` ist ``[[time_s, strength], ...]``, nach Zeit sortiert; die
    Strengths sind beim Laden auf 0..1 normiert. Rueckgabe 0.0 heisst
    "gemessen, aber hier passiert nichts" — das ist eine Aussage, kein
    fehlendes Signal.
    """
    lo = int(np.searchsorted(arr[:, 0], t - window, side="left"))
    hi = int(np.searchsorted(arr[:, 0], t + window, side="right"))
    if hi <= lo:
        return 0.0
    return _clamp01(float(arr[lo:hi, 1].max()))


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
    # ── B-736: Rhythmus-Quellen aus ``beatgrids`` ────────────────────────────
    # Alle EINMAL pro Track geparst und hier als np.ndarray gehalten, damit
    # ``rhythm_at`` pro Cut nur noch searchsorted macht (O(log n), kein
    # json.loads, keine Query). Das Latenzbudget aus
    # tests/integration/test_pacing_performance.py laesst kein Parsen pro Cut
    # und erst recht keines pro Kandidat zu.
    #
    # spectral_centroid stammt aus ``av_pacing_data`` (gleiches 0.4s-Raster
    # wie spectral_flux) und ist beim Laden auf 0..1 normiert.
    beats: np.ndarray | None = None            # Beat-Zeitpunkte (s)
    downbeats: np.ndarray | None = None        # Downbeat-Zeitpunkte (s)
    onset_kick: np.ndarray | None = None       # (N,2) [time_s, strength]
    onset_snare: np.ndarray | None = None
    onset_hihat: np.ndarray | None = None
    onset_strength: tuple[float, ...] = ()     # 0..1 normiert
    onset_strength_hop_sec: float = 0.0
    spectral_centroid: tuple[float, ...] = ()  # 0..1 normiert
    # Medianwerte, einmal vorberechnet — Nenner der Naeherungs-Normierung.
    median_beat_interval: float = 0.0
    median_bar_interval: float = 0.0
    # Onsets/s im Track (Kick+Snare+Hihat) — Bezugsgroesse fuer die lokale
    # Onset-Dichte, damit ein ruhiger Track nicht automatisch "dicht" wirkt.
    onset_rate_ref: float = 0.0

    def has_rhythm(self) -> bool:
        """True, wenn mindestens eine der B-736-Quellen vorliegt."""
        return (
            (self.beats is not None and self.beats.size > 0)
            or bool(self.onset_strength)
            or bool(self.spectral_centroid)
            or self.onset_kick is not None
            or self.onset_snare is not None
            or self.onset_hihat is not None
        )

    def rhythm_at(self, t_sec: float) -> dict[str, float]:
        """Rhythmus-/Klangfarben-Snapshot am Cut-Zeitpunkt ``t_sec``.

        Liefert NUR Keys, fuer die es eine echte Quelle gibt. Ein fehlender
        Key heisst "kein Signal" — der Aufrufer darf daraus KEINE 0.5 machen,
        sonst waere eine Nicht-Messung von einer Messung ununterscheidbar.

        Alle Werte in 0..1. Kosten pro Aufruf: einige ``searchsorted`` auf
        vorgeparsten Arrays — wird einmal pro Cut aufgerufen, nie pro Kandidat.
        """
        out: dict[str, float] = {}
        t = float(t_sec)

        # on_beat: 1.0 direkt auf dem Beat, 0.0 maximal weit daneben
        # (= eine halbe Beat-Periode). Genau das, was scene_cut_weight meint.
        if (self.beats is not None and self.beats.size > 0
                and self.median_beat_interval > 1e-6):
            dist = _nearest_distance(self.beats, t)
            out["on_beat"] = 1.0 - _clamp01(
                dist / (0.5 * self.median_beat_interval))

        # beat_strength: Naehe zum Downbeat (Takt-1). Ein Schnitt auf der
        # Takt-Eins wirkt anders als einer auf Zaehlzeit 3 — deshalb eine
        # eigene Achse neben on_beat.
        if (self.downbeats is not None and self.downbeats.size > 0
                and self.median_bar_interval > 1e-6):
            dist = _nearest_distance(self.downbeats, t)
            out["beat_strength"] = 1.0 - _clamp01(
                dist / (0.5 * self.median_bar_interval))

        if self.onset_strength and self.onset_strength_hop_sec > 1e-9:
            idx = int(t / self.onset_strength_hop_sec)
            idx = min(max(idx, 0), len(self.onset_strength) - 1)
            out["onset_strength"] = _clamp01(float(self.onset_strength[idx]))

        if self.spectral_centroid and self.hop_sec > 1e-9:
            idx = int(t / self.hop_sec)
            idx = min(max(idx, 0), len(self.spectral_centroid) - 1)
            out["spectral_centroid_norm"] = _clamp01(
                float(self.spectral_centroid[idx]))

        for key, arr in (("kick_present", self.onset_kick),
                         ("snare_present", self.onset_snare),
                         ("hihat_present", self.onset_hihat)):
            if arr is None or arr.size == 0:
                continue
            out[key] = _onset_energy_at(arr, t, _ONSET_WINDOW_SEC)

        # onset_sensitivity: lokale Onset-DICHTE (Onsets/s im Fenster um den
        # Cut), auf die Track-Rate bezogen. Bei dichtem Material muesste ein
        # Cutter unempfindlicher triggern, bei duennem empfindlicher — genau
        # die Groesse, die die gleichnamige Achse ausdruecken soll.
        if self.onset_rate_ref > 1e-9:
            n = 0
            for arr in (self.onset_kick, self.onset_snare, self.onset_hihat):
                if arr is None or arr.size == 0:
                    continue
                lo = np.searchsorted(arr[:, 0], t - _DENSITY_WINDOW_SEC, "left")
                hi = np.searchsorted(arr[:, 0], t + _DENSITY_WINDOW_SEC, "right")
                n += int(hi - lo)
            local_rate = n / (2.0 * _DENSITY_WINDOW_SEC)
            # Track-Rate = 1.0; doppelt so dicht wie der Track-Schnitt = 1.0
            # nach Clamp. Bewusst linear, keine erfundene Kennlinie.
            out["onset_sensitivity"] = _clamp01(
                local_rate / (2.0 * self.onset_rate_ref))

        return out

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


def _as_list(raw) -> list:
    """JSON-Spalte -> Liste. Die Spalten sind ``Column(JSON)``, kommen je nach
    Treiber aber auch mal als str zurueck (B-235 im onset_rhythm_service)."""
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)):
        import json
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    try:
        return list(raw)
    except TypeError:
        return []


def _load_onset_pairs(raw) -> "np.ndarray | None":
    """``[[time, strength], ...]`` -> sortiertes (N,2)-Array, Strength 0..1.

    Die Strengths sind Roh-Onset-Energien (unbeschraenkt, im Referenz-Track
    meist << 1). Ohne Normierung auf den Track-Peak lieferte
    ``_onset_energy_at`` fast ueberall ~0.0 und die Kick-/Snare-/Hihat-Achsen
    waeren zwar "befuellt", aber praktisch konstant.
    """
    pairs = _as_list(raw)
    if not pairs:
        return None
    try:
        arr = np.asarray(pairs, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if arr.ndim != 2 or arr.shape[1] < 2 or arr.shape[0] == 0:
        return None
    arr = arr[:, :2]
    arr = arr[np.argsort(arr[:, 0], kind="stable")]
    peak = float(arr[:, 1].max())
    if peak > 1e-9:
        arr[:, 1] = arr[:, 1] / peak
    return arr


def _load_beat_rhythm(session, audio_track_id: int) -> dict:
    """B-736: Rhythmus-Rohdaten aus ``beatgrids`` — EINMAL pro Track.

    Bewusst hier und nicht ueber ``audio_track.beatgrid``: ``pacing_service``
    laedt den Track mit ``.defer()`` auf genau diesen Blob-Spalten
    (services/pacing_service.py:1328-1336), ein Attribut-Zugriff wuerde dort
    entweder eine versteckte Query pro Cut ausloesen oder nach dem
    ``with``-Block auf dem detachten Objekt scheitern.

    Fehlende Tabelle/Zeile ist ein regulaerer Zustand -> leeres dict, und die
    betroffenen Achsen bleiben ohne Signal.
    """
    try:
        from sqlalchemy import select

        from database import Beatgrid
    except ImportError:
        return {}
    try:
        row = session.execute(
            select(
                Beatgrid.beat_positions,
                Beatgrid.downbeat_positions,
                Beatgrid.onset_kick_data,
                Beatgrid.onset_snare_data,
                Beatgrid.onset_hihat_data,
                Beatgrid.onset_strength_curve,
            ).where(Beatgrid.audio_track_id == audio_track_id)
        ).first()
    except Exception as e:  # noqa: BLE001
        logger.debug("_load_beat_rhythm(track=%s) fehlgeschlagen: %s",
                     audio_track_id, e)
        return {}
    if row is None:
        return {}

    beats_raw, downbeats_raw, kick_raw, snare_raw, hihat_raw, strength_raw = row

    def _times(raw) -> "np.ndarray | None":
        vals = _as_list(raw)
        if not vals:
            return None
        try:
            arr = np.asarray(vals, dtype=np.float64).ravel()
        except (TypeError, ValueError):
            return None
        return np.sort(arr) if arr.size else None

    beats = _times(beats_raw)
    downbeats = _times(downbeats_raw)
    out: dict = {
        "beats": beats,
        "downbeats": downbeats,
        "onset_kick": _load_onset_pairs(kick_raw),
        "onset_snare": _load_onset_pairs(snare_raw),
        "onset_hihat": _load_onset_pairs(hihat_raw),
    }
    if beats is not None and beats.size >= 2:
        out["median_beat_interval"] = float(np.median(np.diff(beats)))
    if downbeats is not None and downbeats.size >= 2:
        out["median_bar_interval"] = float(np.median(np.diff(downbeats)))

    # onset_strength_curve ist bereits auf den Track-Peak normiert
    # (onset_rhythm_service: ``onset_env[::4] / max_env``). Ihr Hop wird NICHT
    # persistiert (beatgrids hat keine solche Spalte), deshalb aus der
    # Track-Laenge zurueckgerechnet statt HOP_LENGTH/DEFAULT_SR zu raten —
    # ein falsch geratener Hop wuerde den Index systematisch verschieben und
    # jedem Cut die Onset-Staerke einer anderen Stelle zuordnen.
    strength = [float(v) for v in _as_list(strength_raw)]
    if strength:
        span = _track_duration(session, audio_track_id)
        if span is None and beats is not None and beats.size:
            span = float(beats[-1])
        if span and span > 0:
            out["onset_strength"] = tuple(strength)
            out["onset_strength_hop_sec"] = float(span) / float(len(strength))
        else:
            logger.debug(
                "onset_strength_curve fuer track=%s ohne Zeitbezug "
                "(keine Dauer, keine Beats) — Achse bleibt ohne Signal.",
                audio_track_id,
            )

    # Referenz-Onset-Rate ueber den ganzen Track (Onsets/s).
    total = 0
    span_end = 0.0
    for key in ("onset_kick", "onset_snare", "onset_hihat"):
        arr = out.get(key)
        if arr is None or arr.size == 0:
            continue
        total += int(arr.shape[0])
        span_end = max(span_end, float(arr[-1, 0]))
    if total and span_end > 1e-6:
        out["onset_rate_ref"] = total / span_end
    return out


def _track_duration(session, audio_track_id: int) -> "float | None":
    try:
        from sqlalchemy import select

        from database import AudioTrack
        row = session.execute(
            select(AudioTrack.duration).where(AudioTrack.id == audio_track_id)
        ).first()
    except Exception:  # noqa: BLE001
        return None
    if row is None or row[0] is None:
        return None
    try:
        return float(row[0])
    except (TypeError, ValueError):
        return None


def load_av_pacing_curves(session, audio_track_id: int) -> "AVPacingCurves | None":
    """Laedt die AV-Pacing- UND Rhythmus-Kurven eines Tracks — EINMAL, vor dem
    Cut-Loop.

    Bewusst als column-select (kein ORM-Voll-Laden): die Zeitreihen sind gross,
    und ``AudioTrack.av_pacing_data`` ist ``lazy='select'``, damit sie nicht bei
    jedem Track-Laden mitkommen (B-090). Hier werden sie gezielt geholt.

    B-736: zusaetzlich zu ``av_pacing_data`` wird jetzt ``beatgrids``
    mitgeladen (Beats, Downbeats, Kick-/Snare-/Hihat-Onsets,
    Onset-Huellkurve) und ``av_pacing_data.spectral_centroid``. Aus diesen
    Quellen baut ``AVPacingCurves.rhythm_at`` den Snapshot am Cut-Punkt, der
    die neun bis dahin auf 0.5 laufenden Bridge-Achsen speist.

    Returns:
        ``AVPacingCurves`` oder None wenn der Track WEDER ``av_pacing_data``
        NOCH verwertbare ``beatgrids``-Rhythmusdaten hat. Vorher gab es None
        schon bei fehlendem ``av_pacing_data`` — ein Track mit Beatgrid, aber
        ohne AV-Pacing-Stage haette damit auch seine Rhythmusdaten verloren.
        None bleibt ein regulaerer Zustand; der Scorer nutzt dann seine
        Bestands-Terme.
    """
    try:
        from sqlalchemy import select

        from database import AVPacingData
    except ImportError:
        return None
    row = None
    try:
        row = session.execute(
            select(
                AVPacingData.hop_sec,
                AVPacingData.spectral_flux,
                AVPacingData.stereo_width,
                AVPacingData.percussive_ratio,
                AVPacingData.rms_hop_sec,
                AVPacingData.rms_curve,
                AVPacingData.spectral_centroid,
            ).where(AVPacingData.audio_track_id == audio_track_id)
        ).first()
    except Exception as e:  # noqa: BLE001
        logger.debug("load_av_pacing_curves(track=%s) fehlgeschlagen: %s",
                     audio_track_id, e)

    rhythm = _load_beat_rhythm(session, audio_track_id)

    if row is None:
        if not rhythm or not any(
            v is not None and (not hasattr(v, "size") or v.size)
            for v in (rhythm.get("beats"), rhythm.get("onset_kick"),
                      rhythm.get("onset_snare"), rhythm.get("onset_hihat"))
        ) and not rhythm.get("onset_strength"):
            return None
        # Kein av_pacing_data, aber Beatgrid-Rhythmus vorhanden: Container nur
        # mit den Rhythmus-Feldern. hop_sec=0 -> at() liefert (None,None,None),
        # exakt wie bisher bei fehlendem Datensatz.
        return AVPacingCurves(
            hop_sec=0.0, spectral_flux=[], stereo_width=[],
            percussive_ratio=[], **rhythm,
        )

    (hop_sec, flux, width, perc, rms_hop_sec, rms_curve,
     centroid) = row
    flux = list(flux or [])
    # spectral_flux ist unbeschraenkt (Norm der Magnitude-Differenzen) —
    # auf 0..1 normieren, sonst clampt at() alles > 1.0 auf 1.0 platt.
    if flux:
        peak = max(flux)
        if peak > 1e-9:
            flux = [v / peak for v in flux]
    # spectral_centroid steht in Hz (librosa) und wird hier auf den
    # Track-Peak normiert. Damit ist er direkt mit ClipCandidate.brightness
    # (0..1) vergleichbar — genau das rechnet
    # BridgeDimensions._compute_brightness_match_weight.
    centroid_list = [float(v) for v in _as_list(centroid)]
    if centroid_list:
        cpeak = max(centroid_list)
        if cpeak > 1e-9:
            centroid_list = [v / cpeak for v in centroid_list]
        else:
            centroid_list = []
    return AVPacingCurves(
        hop_sec=float(hop_sec or 0.0),
        spectral_flux=flux,
        stereo_width=list(width or []),
        percussive_ratio=list(perc or []),
        spectral_centroid=tuple(centroid_list),
        **rhythm,
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
        # B-736: Rhythmus-/Klangfarben-Snapshot GENAU an dieser Stelle im
        # Track. Ein Aufruf pro Cut (nicht pro Kandidat) — die Werte gelten
        # fuer den Cut und werden vom Reranker ueber alle Kandidaten
        # wiederverwendet.
        rhythm = av_pacing.rhythm_at(float(seg_start_sec))
    else:
        at_flux = at_width = at_perc = None
        at_rms = None
        rhythm = {}

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
        # B-736: fehlender Key -> Feld bleibt None -> Reranker markiert die
        # Achse als "kein Signal". Kein 0.5-Default an dieser Stelle.
        at_on_beat=rhythm.get("on_beat"),
        at_beat_strength=rhythm.get("beat_strength"),
        at_onset_strength=rhythm.get("onset_strength"),
        at_onset_density=rhythm.get("onset_sensitivity"),
        at_kick_strength=rhythm.get("kick_present"),
        at_snare_strength=rhythm.get("snare_present"),
        at_hihat_strength=rhythm.get("hihat_present"),
        at_spectral_centroid_norm=rhythm.get("spectral_centroid_norm"),
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


_TAG_KEYS: tuple[str, ...] = (
    "avg_brightness", "avg_saturation", "color_temp",
    "role_confidence", "role_source",
)


def _opt_float(raw, lo: float, hi: float) -> "float | None":
    """Wert -> float in [lo, hi], oder None wenn nicht gemessen.

    ``None`` bleibt ``None`` — die Unterscheidung "nie gemessen" vs.
    "gemessen und zufaellig 0.5" ist der ganze Punkt von B-734. Ein
    Nicht-Float (kaputte Zeile) wird ebenfalls zu None statt zu einer
    erfundenen Zahl.
    """
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val:  # NaN
        return None
    return max(lo, min(hi, val))


def _scene_tag_lookup(scene, scenes, scene_id: int) -> dict:
    """Sammelt die ``struct_clip_tags``-Zusatzspalten fuer EINE Szene.

    Reihenfolge: Attribut am ``scene``-Objekt gewinnt (direkte Aufrufer und
    Tests), sonst der Eintrag mit passender ``id`` aus ``scenes``.
    """
    out: dict = {}
    for key in _TAG_KEYS:
        val = getattr(scene, key, None)
        if val is not None:
            out[key] = val
    if len(out) == len(_TAG_KEYS) or not scenes:
        return out
    for s in scenes:
        try:
            if int(s.get("id", -1)) != scene_id:
                continue
        except (AttributeError, TypeError, ValueError):
            continue
        for key in _TAG_KEYS:
            if key not in out and s.get(key) is not None:
                out[key] = s[key]
        break
    return out


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

    # B-734/B-735: Bildmetriken + Rollen-Konfidenz aus ``struct_clip_tags``.
    #
    # Warum aus ``scenes`` und nicht nur aus ``scene``: der Aufrufer im
    # Produktivpfad (services/pacing_service.py, ausserhalb des fuer diese
    # Aufgabe freigegebenen Datei-Sets) baut das ``scene``-Stub-Objekt mit
    # einer festen Feldliste, die diese Spalten nicht enthaelt. Die vollen
    # Szenen-Dicts kommen aber ohnehin als ``scenes`` herein und tragen die
    # Spalten seit ``services/pacing_beat_grid.py`` sie nachlaedt. Deshalb
    # erst am Stub lesen (Tests/direkte Aufrufer), dann per scene_id im
    # ``scenes``-Dict nachschlagen.
    _tags = _scene_tag_lookup(scene, scenes, scene_id)

    return ClipFeatures(
        clip_id=int(video_clip_id),
        scene_id=scene_id,
        role=str(role),
        mood_refined=str(mood),
        style_bucket_id=int(bucket),
        motion_score=motion,
        embedding=embedding,
        shot_confidences=shot_conf,
        brightness=_opt_float(_tags.get("avg_brightness"), lo=0.0, hi=1.0),
        saturation=_opt_float(_tags.get("avg_saturation"), lo=0.0, hi=1.0),
        color_temp=_opt_float(_tags.get("color_temp"), lo=-1.0, hi=1.0),
        role_confidence=_opt_float(_tags.get("role_confidence"), lo=0.0, hi=1.0),
        role_source=(str(_tags["role_source"])
                     if _tags.get("role_source") else None),
        # Aktiviert zusammen mit AudioContext.at_rms_curve den kurvenbasierten
        # Energy-Match (scorer.score) statt des skalaren energy_match.
        motion_curve=build_motion_curve(scenes, offset_sec),
    )
