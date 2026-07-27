"""B-734 / B-735 / B-736 — Bildmetriken, Rolle und Musik-Snapshot muessen im
Ranking ANKOMMEN.

User-Vorgabe: "besonders das pacing und die signale, so dass alles wie
besprochen individuell fuer jeden clip verwendet werden kann und dadurch den
genau zur musik passenden clip auswaehlt."

Diese Tests pruefen bewusst VARIANZ statt Existenz. Genau daran sind die drei
Luecken jahrelang unentdeckt geblieben: die Werte waren gesetzt und sahen
plausibel aus — sie waren nur fuer jeden Kandidaten eines Cuts DIESELBEN
(bzw. fuer jeden Cut eines Tracks dieselben). Ein konstanter Summand
verschiebt den Score, aber nie die Reihenfolge. Ein Existenztest haette
keinen der drei Bugs gefangen.

Zwei Varianz-Achsen, die NICHT verwechselt werden duerfen:

  (a) ueber die KANDIDATEN EINES CUTS — das entscheidet, welcher Clip
      gewaehlt wird. Nur Achsen, die den Clip lesen, koennen hier variieren.
  (b) ueber die CUTS eines Tracks — das entscheidet, ob dieselbe
      Kandidatenmenge an einer ruhigen Stelle anders sortiert wird als im
      Drop. Die reinen Audio-Achsen koennen NUR hier variieren; das ist
      keine Luecke, sondern ihre Definition
      (``bridge_dimensions._compute_beat_weight`` liest nur den Kontext).

Der eigentliche Nachweis fuer "waehlt den zur Musik passenden Clip" ist
``test_b736_ranking_differs_between_quiet_passage_and_drop``: dieselben
Kandidaten, zwei verschiedene Musikstellen, andere Rangfolge.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


REAL_DB = Path(
    "C:/Users/David_Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild"
    "/outputs/test-tabelle/pb_studio.db"
)


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    """WeightStore/BrainStore schreiben unter %APPDATA% — pro Test isolieren."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


def _spread(values) -> float:
    """max-min ueber eine Werteliste — 0.0 heisst 'konstant'."""
    vals = [float(v) for v in values]
    return max(vals) - min(vals)


def _distinct(values, ndigits: int = 9) -> int:
    return len({round(float(v), ndigits) for v in values})


# ======================================================================
# Bausteine
# ======================================================================

def _clip(clip_id, *, motion=0.5, mood="dark", role="filler", bucket=3,
          curve_bins=20, seed=1, brightness=None, saturation=None,
          color_temp=None, role_confidence=None, role_source=None):
    from services.pacing.scorer import ClipFeatures

    rng = np.random.default_rng(seed)
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined=mood,
        style_bucket_id=bucket,
        motion_score=motion,
        embedding=rng.standard_normal(32).astype(np.float32),
        motion_curve=np.full(curve_bins, motion, dtype=np.float32),
        brightness=brightness,
        saturation=saturation,
        color_temp=color_temp,
        role_confidence=role_confidence,
        role_source=role_source,
    )


class _Ctx:
    """AudioContext-Stub. Der Reranker liest ausschliesslich per getattr."""

    at_section_type = "drop"
    at_mood_audio = "dramatic"
    at_bpm = 128.0
    at_energy = 0.7
    at_harmonic_tension = 0.4

    def __init__(self, **kw):
        self.at_audio_mood_vec = kw.pop("mood_vec", None)
        # B-736-Felder: default None = "Quelle fehlt"
        for name in ("at_on_beat", "at_beat_strength", "at_onset_strength",
                     "at_onset_density", "at_kick_strength",
                     "at_snare_strength", "at_hihat_strength",
                     "at_spectral_centroid_norm"):
            setattr(self, name, None)
        for k, v in kw.items():
            setattr(self, k, v)


def _reranker(brain_weight=1.0):
    from services.brain.reranker import BrainV3Reranker
    from services.brain.storage.brain_store import BrainStore
    from services.brain.weight_store import WeightStore

    return BrainV3Reranker(WeightStore(BrainStore().weights_path),
                           brain_weight=brain_weight)


# ======================================================================
# B-734 — Bildmetriken erreichen das Ranking
# ======================================================================

def test_b734_visual_metrics_reach_the_candidate(isolated_appdata):
    """``struct_clip_tags``-Bildmetriken landen auf dem ClipCandidate.

    Vorher setzte ``_adapt_clip`` sie hart auf 0.5/0.5/0.0, weil die
    ``contribs``-Keys, aus denen sie gelesen wurden, nie existierten.
    """
    rr = _reranker()
    cand, no_signal = rr._adapt_clip(
        _clip(1, brightness=0.1195, saturation=0.2130, color_temp=-0.5718), {})

    assert cand.brightness == pytest.approx(0.1195)
    assert cand.saturation == pytest.approx(0.2130)
    assert cand.color_temp == pytest.approx(-0.5718)
    # Mit Messwert sind die Bildachsen keine "kein Signal"-Achsen mehr.
    assert "color_temp_match_weight" not in no_signal


def test_b734_null_stays_no_signal_not_half(isolated_appdata):
    """NULL (= nie gemessen) darf NICHT als 0.5 durchgehen.

    Die Unterscheidung ist der ganze Punkt: eine nicht gemessene Szene und
    eine Szene, deren Helligkeit zufaellig 0.5 ist, muessen unterscheidbar
    bleiben — sonst gilt eine Nicht-Messung als Bewertung.
    """
    rr = _reranker()
    _cand, no_signal = rr._adapt_clip(_clip(1), {})  # alle Metriken None
    assert "brightness_match_weight" in no_signal
    assert "color_temp_match_weight" in no_signal


def test_b734_visual_axes_vary_across_candidates_of_one_cut(isolated_appdata):
    """KERN: die Bildachsen muessen ueber die Kandidaten EINES Cuts variieren.

    Werte aus der Referenz-Messung an 27 echten Szenen
    (services/enrichment/visual_metrics.py): brightness 0.1195..0.4011,
    color_temp -0.5718..+0.1407.
    """
    rr = _reranker()
    bright = [0.1195, 0.2604, 0.4011]
    temps = [-0.5718, -0.2155, 0.1407]
    scored = [
        (_clip(i + 1, seed=i + 1, brightness=b, saturation=0.21 + 0.1 * i,
               color_temp=t), 0.5, {})
        for i, (b, t) in enumerate(zip(bright, temps))
    ]
    # Audio-Seite von brightness_match_weight mitliefern — ohne spektralen
    # Schwerpunkt hat die Achse keinen Vergleichspunkt.
    out = rr.rerank(scored, _Ctx(at_spectral_centroid_norm=0.42))
    assert len(out) == 3

    for axis in ("brightness_match_weight", "color_temp_match_weight"):
        vals = [c.brain_v3_scores[axis] for c in out]
        assert _spread(vals) > 1e-9, f"{axis} ist ueber die Kandidaten konstant"
        assert _distinct(vals) > 1, f"{axis} hat nur einen distinkten Wert"


def test_b734_metrics_survive_build_clip_features_from_scene_dicts():
    """Die Werte muessen aus den ``scenes``-Dicts kommen, nicht nur vom Stub.

    Der Produktivpfad (services/pacing_service.py) baut das ``scene``-Objekt
    mit einer festen Feldliste OHNE die neuen Spalten; die vollen Dicts gehen
    aber als ``scenes`` mit. Wuerde ``build_clip_features`` nur den Stub
    lesen, kaeme im Produkt nichts an, obwohl jeder Stub-Test gruen bliebe.
    """
    from services.pacing.bridge_mapping import build_clip_features

    scenes = [{
        "id": 7, "start": 0.0, "end": 4.0, "motion_score": 0.6,
        "role": "hero", "role_confidence": 0.87, "role_source": "embedding",
        "avg_brightness": 0.3312, "avg_saturation": 0.7714,
        "color_temp": 0.1407,
    }]
    stub = type("_S", (), {"id": 7, "motion_score": 0.6, "role": "hero"})()

    cf = build_clip_features(video_clip_id=3, scene=stub, scenes=scenes)
    assert cf.brightness == pytest.approx(0.3312)
    assert cf.saturation == pytest.approx(0.7714)
    assert cf.color_temp == pytest.approx(0.1407)
    assert cf.role_confidence == pytest.approx(0.87)
    assert cf.role_source == "embedding"


# ======================================================================
# B-735 — Rolle + Konfidenz wirken in der Kandidatenbewertung
# ======================================================================

def test_b735_role_terms_vary_across_candidates_of_one_cut():
    """``role_fit``/``tension_fit`` muessen pro Clip unterschiedlich beitragen.

    Referenz-Messung nach dem Embedding-Klassifikator: establishing/hero
    statt 27x filler, role_confidence mit 25 distinkten Werten.
    """
    from services.pacing.scorer import AudioContext, PacingScorer

    ctx = AudioContext(
        at_timestamp_sec=42.0, at_beat_idx=10, at_section_type="drop",
        at_bpm=130.4, at_energy=0.8, at_key="Am", at_key_confidence=0.8,
        at_harmonic_tension=0.82, at_mood_audio="dramatic",
        at_mood_video="dramatic", at_genre="psytrance", at_sub_genre=None,
        at_spectral_hash=None, at_groove_template=None, at_lufs=-8.0,
    )
    scorer = PacingScorer()
    clips = [
        _clip(1, role="hero", role_confidence=0.91, role_source="embedding"),
        _clip(2, role="establishing", role_confidence=0.64,
              role_source="embedding"),
        _clip(3, role="filler", role_confidence=0.30, role_source="rule"),
    ]
    contribs = [scorer.score(c, ctx)[1] for c in clips]

    for term in ("role", "tension"):
        vals = [c[term] for c in contribs]
        assert _spread(vals) > 1e-9, f"{term}-Beitrag ueber Kandidaten konstant"
        assert _distinct(vals) == 3, f"{term}: nur {_distinct(vals)} Auspraegungen"


def test_b735_confidence_alone_creates_variance():
    """Auch bei IDENTISCHER Rolle muss die Konfidenz differenzieren.

    Das ist der reale Zustand der Referenz-DB vor dem Re-Enrichment:
    27/27 Szenen ``filler``. Ohne Konfidenz-Daempfung waere der Rollen-Term
    dort fuer alle Kandidaten identisch — also im Ranking wirkungslos.
    """
    from services.pacing.scorer import AudioContext, PacingScorer

    ctx = AudioContext(
        at_timestamp_sec=10.0, at_beat_idx=1, at_section_type="drop",
        at_bpm=130.0, at_energy=0.5, at_key=None, at_key_confidence=None,
        at_harmonic_tension=0.9, at_mood_audio="dramatic",
        at_mood_video="dramatic", at_genre=None, at_sub_genre=None,
        at_spectral_hash=None, at_groove_template=None, at_lufs=None,
    )
    scorer = PacingScorer()
    vals = [
        scorer.score(_clip(i, role="filler", role_confidence=conf), ctx)[1]["role"]
        for i, conf in enumerate((0.30, 0.55, 0.88), start=1)
    ]
    assert _spread(vals) > 1e-9
    assert _distinct(vals) == 3


def test_b735_missing_confidence_keeps_legacy_behaviour():
    """``role_confidence=None`` darf das Bestandsverhalten NICHT aendern."""
    from services.pacing.scorer import apply_role_confidence, role_fit

    raw = role_fit("drop", "hero")
    assert apply_role_confidence(raw, None) == raw
    # Konfidenz 1.0 = volle Sicherheit -> ebenfalls unveraendert.
    assert apply_role_confidence(raw, 1.0) == pytest.approx(raw)
    # Konfidenz 0.0 = keine Aussage -> neutral.
    assert apply_role_confidence(raw, 0.0) == pytest.approx(0.5)


# ======================================================================
# B-736 — Musik-Snapshot am Cut-Zeitpunkt
# ======================================================================

_IBI = 0.46        # Beat-Abstand bei 130.4 BPM (Referenz-Track 1)
_BAR = _IBI * 4
_DROP_SEC = 30.0   # ab hier "Drop"
# Abfragepunkte: exakt auf einem Beat, einmal in der ruhigen Haelfte, einmal
# im Drop. Auf dem Beat, damit die Drum-Fenster wirklich etwas finden.
_T_QUIET = _IBI * 32          # 14.72 s
_T_DROP = _IBI * 98           # 45.08 s


def _curves(**kw):
    """AVPacingCurves mit synthetischem, aber realistisch geformtem Rhythmus."""
    from services.pacing.bridge_mapping import AVPacingCurves

    beats = np.arange(0.0, 60.0, _IBI)          # 130.4 BPM wie Referenz-Track
    downbeats = np.arange(0.0, 60.0, _BAR)
    # Drum-Onsets liegen AUF dem Beatgrid. Laegen sie dazwischen, faende die
    # Fensterabfrage an BEIDEN Stellen nichts (0.0 == 0.0) und der Test waere
    # zwar gruen, wuerde aber nichts belegen.
    #
    # Ruhige Haelfte (< 30 s): leise Kicks/Snares, Hihat nur auf jedem 4.
    #                          Beat -> geringe Onset-Dichte.
    # Drop (>= 30 s):          laute Kicks/Snares, Hihat auf jedem Beat.
    quiet = beats[beats < _DROP_SEC]
    drop = beats[beats >= _DROP_SEC]

    def _band(quiet_amp: float, drop_amp: float):
        amps = np.where(beats < _DROP_SEC, quiet_amp, drop_amp)
        return np.column_stack([beats, amps])

    hihat_t = np.concatenate([quiet[::4], drop])
    hihat = np.column_stack([
        hihat_t, np.where(hihat_t < _DROP_SEC, 0.15, 0.75)])

    hop = 0.1
    n = int(60.0 / hop)
    onset = tuple(0.1 if i * hop < _DROP_SEC else 0.9 for i in range(n))
    centroid = tuple(0.2 if i * hop < _DROP_SEC else 0.8 for i in range(n))
    base = dict(
        hop_sec=hop, spectral_flux=[0.5] * n, stereo_width=[0.5] * n,
        percussive_ratio=[0.5] * n,
        beats=beats, downbeats=downbeats,
        onset_kick=_band(0.25, 1.0), onset_snare=_band(0.20, 0.9),
        onset_hihat=hihat,
        onset_strength=onset, onset_strength_hop_sec=hop,
        spectral_centroid=centroid,
        median_beat_interval=_IBI, median_bar_interval=_BAR,
        onset_rate_ref=float(2 * len(beats) + len(hihat_t)) / 60.0,
    )
    base.update(kw)
    return AVPacingCurves(**base)


def test_b736_rhythm_snapshot_varies_across_cuts():
    """Der Snapshot muss die STELLE im Track beschreiben, nicht den Track.

    Vorher standen in ``raw_audio_features`` nur energy/bpm/section/mood/
    tension — neun Achsen liefen auf dem konstanten 0.5-Fallback aus
    ``BridgeDimensions.compute``.
    """
    av = _curves()
    quiet = av.rhythm_at(_T_QUIET)
    drop = av.rhythm_at(_T_DROP)

    for key in ("onset_strength", "spectral_centroid_norm", "kick_present",
                "snare_present", "onset_sensitivity"):
        assert key in quiet and key in drop, f"{key} fehlt im Snapshot"
        assert abs(drop[key] - quiet[key]) > 1e-6, (
            f"{key} ist zwischen ruhiger Stelle und Drop identisch")
        # Drop ist lauter/dichter als die ruhige Passage.
        assert drop[key] > quiet[key], f"{key}: Drop nicht groesser als Ruhe"


def test_b736_on_beat_is_maximal_on_the_beat():
    """``on_beat`` muss auf dem Beat 1.0 und dazwischen deutlich kleiner sein."""
    av = _curves()
    on = av.rhythm_at(_IBI * 20)          # exakt auf einem Beat
    off = av.rhythm_at(_IBI * 20 + _IBI / 2)  # exakt dazwischen
    assert on["on_beat"] == pytest.approx(1.0, abs=1e-6)
    assert off["on_beat"] < 0.05


def test_b736_missing_source_stays_no_signal(isolated_appdata):
    """Fehlt eine Quelle, muss die Achse als "kein Signal" gemeldet werden.

    Kein stiller 0.5-Ersatz: sonst waere "nie gemessen" von "gemessen und
    zufaellig 0.5" nicht unterscheidbar.
    """
    rr = _reranker()
    out = rr.rerank([(_clip(1), 0.5, {})], _Ctx())  # alle B-736-Felder None
    ns = out[0].no_signal_axes
    for axis in ("beat_weight", "onset_weight", "kick_weight", "snare_weight",
                 "hihat_weight", "onset_sensitivity", "scene_cut_weight"):
        assert axis in ns, f"{axis} muesste ohne Quelle 'kein Signal' sein"


def test_b736_real_source_clears_no_signal(isolated_appdata):
    """Mit echten Werten duerfen dieselben Achsen NICHT mehr als tot gelten."""
    rr = _reranker()
    ctx = _Ctx(at_beat_strength=0.8, at_onset_strength=0.6,
               at_kick_strength=0.9, at_snare_strength=0.3,
               at_hihat_strength=0.1, at_onset_density=0.55,
               at_on_beat=0.95, at_spectral_centroid_norm=0.42)
    out = rr.rerank([(_clip(1, brightness=0.3), 0.5, {})], ctx)
    ns = out[0].no_signal_axes
    for axis in ("beat_weight", "onset_weight", "kick_weight", "snare_weight",
                 "hihat_weight", "onset_sensitivity", "scene_cut_weight",
                 "brightness_match_weight"):
        assert axis not in ns, f"{axis} gilt trotz Messwert als 'kein Signal'"


def test_b736_audio_axis_values_differ_between_music_positions(isolated_appdata):
    """Die Bridge-Achsen-Werte selbst muessen sich pro Musikstelle aendern."""
    rr = _reranker()
    clip = _clip(1, brightness=0.3)
    av = _curves()
    q, d = av.rhythm_at(_T_QUIET), av.rhythm_at(_T_DROP)

    def _axes(snap):
        ctx = _Ctx(
            at_kick_strength=snap.get("kick_present"),
            at_snare_strength=snap.get("snare_present"),
            at_onset_strength=snap.get("onset_strength"),
            at_onset_density=snap.get("onset_sensitivity"),
            at_beat_strength=snap.get("beat_strength"),
            at_on_beat=snap.get("on_beat"),
            at_spectral_centroid_norm=snap.get("spectral_centroid_norm"),
        )
        return rr.rerank([(clip, 0.5, {})], ctx)[0].brain_v3_scores

    a, b = _axes(q), _axes(d)
    changed = {ax for ax in a if abs(a[ax] - b[ax]) > 1e-9}
    assert {"kick_weight", "snare_weight", "onset_weight", "onset_sensitivity",
            "brightness_match_weight"} <= changed, (
        f"unveraendert geblieben: {changed}")


# ======================================================================
# Integrationsbeleg — der eigentliche Nachweis
# ======================================================================

def test_b736_ranking_differs_between_quiet_passage_and_drop(isolated_appdata):
    """DIESELBEN Kandidaten muessen an zwei Musikstellen anders sortiert werden.

    Das ist der Nachweis fuer "waehlt den zur Musik passenden Clip". Wuerden
    nur die reinen Audio-Achsen befuellt, bliebe die Reihenfolge gleich —
    ein konstanter Summand verschiebt jeden Kandidaten identisch. Die
    Rangfolge kann sich nur aendern, wenn eine Achse Clip UND Musikstelle
    gegeneinander bewertet:
      brightness_match_weight = 1 - |clip.brightness - spectral_centroid|
      motion_match_weight     = 1 - |clip.motion - energy|
    """
    rr = _reranker()
    # Dunkler, ruhiger Clip vs. heller, bewegter Clip.
    dark = _clip(1, motion=0.15, brightness=0.12, color_temp=-0.55,
                 curve_bins=40, seed=11)
    bright = _clip(2, motion=0.85, brightness=0.40, color_temp=0.14,
                   curve_bins=40, seed=12)
    scored = [(dark, 0.5, {}), (bright, 0.5, {})]

    av = _curves()
    quiet_snap, drop_snap = av.rhythm_at(_T_QUIET), av.rhythm_at(_T_DROP)

    def _order(snap, energy):
        ctx = _Ctx(
            at_kick_strength=snap.get("kick_present"),
            at_snare_strength=snap.get("snare_present"),
            at_onset_strength=snap.get("onset_strength"),
            at_onset_density=snap.get("onset_sensitivity"),
            at_beat_strength=snap.get("beat_strength"),
            at_on_beat=snap.get("on_beat"),
            at_spectral_centroid_norm=snap.get("spectral_centroid_norm"),
        )
        ctx.at_energy = energy
        return [c.clip_id for c in rr.rerank(scored, ctx)]

    quiet_order = _order(quiet_snap, energy=0.15)   # leise Passage
    drop_order = _order(drop_snap, energy=0.85)     # Drop

    assert quiet_order != drop_order, (
        "Rangfolge ist an beiden Musikstellen identisch — der Reranker "
        "bewertet Clip und Musikstelle nicht gegeneinander."
    )
    # Richtungspruefung: der dunkle/ruhige Clip gehoert in die ruhige
    # Passage, der helle/bewegte in den Drop.
    assert quiet_order[0] == 1, f"ruhige Stelle waehlt {quiet_order[0]}"
    assert drop_order[0] == 2, f"Drop waehlt {drop_order[0]}"


# ======================================================================
# Echte DB — read-only Gegenprobe
# ======================================================================

@pytest.mark.skipif(not REAL_DB.exists(), reason="Referenz-DB nicht vorhanden")
def test_b736_real_db_rhythm_varies_across_cut_points():
    """Gegenprobe an der echten DB: der Snapshot variiert ueber die Cuts.

    Read-only (``mode=ro``) — der Testschutz blockiert schreibende
    Verbindungen auf die Produktiv-DB, und das ist Absicht.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from services.pacing.bridge_mapping import load_av_pacing_curves

    eng = create_engine(f"sqlite:///file:{REAL_DB.as_posix()}?mode=ro&uri=true")
    cut_points = [10.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0]
    tracks_with_rhythm = 0
    with Session(eng) as s:
        for track_id in (1, 2):
            av = load_av_pacing_curves(s, track_id)
            if av is None or not av.has_rhythm():
                continue
            tracks_with_rhythm += 1
            snaps = [av.rhythm_at(t) for t in cut_points]
            # Mindestens eine Achse muss ueber die Cut-Punkte variieren —
            # sonst beschreibt der Snapshot den Track, nicht die Stelle.
            varying = {
                k for k in ("on_beat", "beat_strength", "onset_strength",
                            "kick_present", "snare_present",
                            "onset_sensitivity", "spectral_centroid_norm")
                if all(k in sn for sn in snaps)
                and _spread([sn[k] for sn in snaps]) > 1e-6
            }
            assert len(varying) >= 4, (
                f"track {track_id}: nur {sorted(varying)} variieren ueber "
                f"die Cut-Punkte")
    assert tracks_with_rhythm > 0, "kein Track mit Rhythmus-Daten in der DB"


@pytest.mark.skipif(not REAL_DB.exists(), reason="Referenz-DB nicht vorhanden")
def test_b736_real_db_onset_hop_matches_analyzer_constant():
    """Der aus der Track-Laenge zurueckgerechnete Hop muss zum Analyzer passen.

    ``beatgrids`` persistiert den Hop der ``onset_strength_curve`` nicht.
    Waere die Rueckrechnung falsch, bekaeme jeder Cut die Onset-Staerke einer
    ANDEREN Stelle zugeordnet — ein Fehler, den kein Existenztest sieht.
    Gegenprobe gegen die Konstanten des Erzeugers
    (services/onset_rhythm_service.py: ``onset_env[::4]``).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from services.audio_constants import DEFAULT_SR, HOP_LENGTH
    from services.pacing.bridge_mapping import load_av_pacing_curves

    expected = HOP_LENGTH / DEFAULT_SR * 4
    eng = create_engine(f"sqlite:///file:{REAL_DB.as_posix()}?mode=ro&uri=true")
    checked = 0
    with Session(eng) as s:
        for track_id in (1, 2):
            av = load_av_pacing_curves(s, track_id)
            if av is None or not av.onset_strength:
                continue
            checked += 1
            assert av.onset_strength_hop_sec == pytest.approx(expected, rel=0.02), (
                f"track {track_id}: hop={av.onset_strength_hop_sec} "
                f"statt {expected}")
    assert checked > 0, "kein Track mit onset_strength_curve"
