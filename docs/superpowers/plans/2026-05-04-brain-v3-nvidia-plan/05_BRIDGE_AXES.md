# 05 — Bridge-Achsen, Kontext, Lern-Algorithmus (Brain V3, NVIDIA)

Inhalte sind **GPU-agnostisch** und gegenüber dem frueheren Plan
unverändert — werden hier vollständig übernommen + mit Code-Pfaden
für die V3-Implementation versehen.

## 17 Bridge-Achsen

### 10 Audio-Achsen (aus bestehender `TriggerSettings`-Dataclass)

| Achse | Beschreibung | Wertebereich |
|---|---|---|
| `beat_weight` | Gewichtung von Beat-Triggern | 0.0–2.0 |
| `onset_weight` | Gewichtung von Onset-Triggern | 0.0–2.0 |
| `kick_weight` | Gewichtung von Kick-Drum-Hits | 0.0–2.0 |
| `snare_weight` | Gewichtung von Snare-Hits | 0.0–2.0 |
| `hihat_weight` | Gewichtung von Hi-Hat-Hits | 0.0–2.0 |
| `energy_weight` | Gewichtung von Energy-Peaks | 0.0–2.0 |
| `energy_threshold` | Schwelle für Energie-Peak-Erkennung | 0.0–1.0 |
| `onset_sensitivity` | Sensitivität der Onset-Detection | 0.0–1.0 |
| `min_clip_length` | Minimale Clip-Länge in Sekunden | ≥0.1 |
| `max_clip_length` | Maximale Clip-Länge in Sekunden | ≥0.5 |

### 7 Video-Achsen (NEU für Brain V3)

| Achse | Beschreibung | Berechnung |
|---|---|---|
| `motion_match_weight` | Motion-Kurve ↔ Audio-Energy-Kurve | Pearson-Korrelation |
| `scene_cut_weight` | Scene-Cut ↔ Beat/Drop-Position | Phasen-Distanz |
| `brightness_match_weight` | Helligkeits-Kurve ↔ Spectral-Centroid | Korrelation |
| `color_temp_match_weight` | Farbtemperatur ↔ Audio-Mood | Cosinus-Similarität |
| `pace_match_weight` | Shot-Länge ↔ BPM-Gefühl | Verhältnis-Match |
| `semantic_match_weight` | SigLIP-2 ↔ CLAP via geteilten Raum | Cosine im Brücken-Space |
| `mood_match_weight` | Video-Mood-Tags ↔ Audio-Mood-Tags | Tag-Overlap-Score |

**Code-Vorbereitung Phase 1:** Visual-Kurven (Brightness/Saturation/ColorTemp)
sind bereits in [`services/brain_v3/video/visual_curves.py`](../../../services/brain_v3/video/visual_curves.py) ✓
implementiert. Tempo-Curve in [`services/brain_v3/audio/subtrack_detector.py`](../../../services/brain_v3/audio/subtrack_detector.py) ✓.

**Implementation Phase 3 (TODO):** `services/brain_v3/bridge_dimensions.py` —
nimmt audio/video-Features + Cut-Kontext, gibt 17 normalisierte Werte zurück.

---

## 6 Kontext-Slots

```text
audio_section_type        intro | verse | build | drop | break | outro | transition
audio_subtrack_position   start | middle | end
audio_energy_level        low | medium | high
audio_mood                dark | neutral | uplifting
video_motion_class        low | medium | high | extreme
video_pace_class          slow | medium | fast
```

**Quantisierung (Phase 3 TODO `services/brain_v3/context_resolver.py`):**
- Energy/Motion-Class aus den jeweiligen Kurven via Tertile (33./66.-Perzentil)
- Section-Type aus Sub-Track-Detector + Foote-Boundaries
  ([`SubtrackDetector`](../../../services/brain_v3/audio/subtrack_detector.py) ✓)
- Subtrack-Position: relative Position innerhalb des erkannten Sub-Tracks
  - `start`: erste 25 %
  - `middle`: 25–75 %
  - `end`: letzte 25 %
- Mood-Klassifikation via CLAP-Audio-Embedding gegen vorgegebene Prototypen

---

## 5 Backoff-Levels

Bei Lookup wird vom spezifischsten zum allgemeinsten Kontext zurückgefallen.
Threshold `MIN_CONFIDENT_SAMPLES = 10`.

```text
Level 0: global
         context_key = ""
         Beispiel: kick_weight | "" → α=120, β=80

Level 1: + audio_section_type
         context_key = "section=drop"
         Beispiel: kick_weight | "section=drop" → α=45, β=8

Level 2: + audio_mood
         context_key = "section=drop|mood=dark"

Level 3: + video_motion_class
         context_key = "section=drop|mood=dark|motion=high"

Level 4: + audio_energy_level
         context_key = "section=drop|mood=dark|motion=high|energy=high"

Level 5: + video_pace_class + audio_subtrack_position
         context_key = "section=drop|mood=dark|motion=high|energy=high|pace=fast|subpos=middle"
```

### Backoff-Lookup-Logik (Phase 3 TODO `weight_store.py`)

```python
# Datei: services/brain_v3/weight_store.py (Phase 3)

MIN_CONFIDENT_SAMPLES = 10

def get_posterior_mean(self, axis: str, context_keys: list[str]) -> float:
    """Findet das spezifischste konfidente Bucket fuer (axis, context).

    context_keys ist absteigend sortiert: [Level 5, Level 4, ..., Level 0]
    """
    for level, key in enumerate(reversed(context_keys)):
        row = self.conn.execute(
            "SELECT positive_count, negative_count FROM axis_weights "
            "WHERE axis = ? AND context_level = ? AND context_key = ?",
            (axis, len(context_keys) - 1 - level, key),
        ).fetchone()

        if row is None:
            continue

        alpha, beta = row
        n_samples = alpha + beta
        if n_samples >= MIN_CONFIDENT_SAMPLES:
            return (alpha + 1.0) / (alpha + beta + 2.0)

    # Fallback: Cold-Start-Default aus TriggerSettings
    return self.cold_start_defaults[axis]
```

---

## Lern-Algorithmus

### Beta-Bernoulli mit Laplace-Smoothing

```python
# Posterior Mean: geglaettete Wahrscheinlichkeit zwischen 0 und 1
posterior_mean = (alpha + 1) / (alpha + beta + 2)

# Varianz: fuer Smart-Sampling (hoehere Varianz = unsicher = priorisieren)
variance = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1))
```

**Eigenschaften:**
- Bei `α=β=0` (cold start): `posterior_mean = 0.5` (neutrale Annahme)
- Konvergiert mit zunehmender Datenmenge zur tatsächlichen Erfolgsrate
- Robust gegen einzelne Ausreißer (Laplace-Smoothing)

**External-Verify:** Standard-Bayesian-Bandit-Literatur (z.B.
[Thompson-Sampling-Survey von Russo et al. 2018](https://arxiv.org/abs/1707.02038)) —
Beta-Posterior für Bernoulli-Likelihood ist Lehrbuch-Standard.

### 4-Klick-Mapping

| Klick | α-Inkrement | β-Inkrement | Bedeutung |
|---|---|---|---|
| Passt perfekt | +2.0 | 0 | starkes positives Signal |
| Passt | +1.0 | 0 | schwaches positives Signal |
| Passt nicht ganz | 0 | +1.0 | schwaches negatives Signal |
| Passt gar nicht | 0 | +2.0 | starkes negatives Signal |

### Atomic Update auf 5 Levels

Pro Klick werden **alle 5 Backoff-Buckets** in einer Transaktion aktualisiert,
für **alle 17 Achsen** = 102 Bucket-Updates (17 Achsen × 6 Levels — Level 0 wird mit-geschrieben damit Backoff-Lookup einen globalen Confidence-Anker hat).

```python
# Datei: services/brain_v3/feedback_logger.py (Phase 3 TODO)

def log_feedback(self, cut_id: int, rating: str, context_keys: list[str]):
    alpha_delta, beta_delta = RATING_MAP[rating]

    with self.weights_conn:  # auto-commit on success, rollback on exc
        for axis in BRIDGE_AXES:                 # 17 Achsen
            for level, key in enumerate(context_keys):  # 5 Levels
                self.weights_conn.execute(
                    """
                    INSERT INTO axis_weights
                        (axis, context_level, context_key,
                         positive_count, negative_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(axis, context_level, context_key) DO UPDATE SET
                        positive_count = positive_count + ?,
                        negative_count = negative_count + ?,
                        last_updated   = excluded.last_updated
                    """,
                    (axis, level, key,
                     alpha_delta, beta_delta, datetime.utcnow().isoformat(),
                     alpha_delta, beta_delta),
                )
```

---

## Cold-Start-Verhalten

Bei einer brandneuen Installation gibt es null Klick-Daten. Der Cold-Start
liefert sinnvolle Defaults aus der bestehenden `TriggerSettings`-Dataclass:

```python
# Datei: services/brain_v3/cold_start.py (Phase 3 TODO)

COLD_START_DEFAULTS = {
    # Audio-Achsen aus TriggerSettings-Defaults
    "beat_weight": 1.0,
    "onset_weight": 0.5,
    "kick_weight": 1.2,
    "snare_weight": 1.0,
    "hihat_weight": 0.3,
    "energy_weight": 0.8,
    "energy_threshold": 0.6,
    "onset_sensitivity": 0.5,
    "min_clip_length": 1.0,
    "max_clip_length": 8.0,
    # Video-Achsen — neutrale Mitte
    "motion_match_weight": 0.5,
    "scene_cut_weight": 0.5,
    "brightness_match_weight": 0.5,
    "color_temp_match_weight": 0.5,
    "pace_match_weight": 0.5,
    "semantic_match_weight": 0.5,
    "mood_match_weight": 0.5,
}
```

Sobald für eine Achse + Kontext mindestens 10 Samples vorliegen, wird der
Default durch den gelernten Posterior Mean ersetzt.

---

## Smart-Sampling

Für den Lern-Session-Dialog werden die **15 unsichersten Cuts** ausgewählt:

```python
# Datei: services/brain_v3/smart_sampler.py (Phase 4 TODO)

def select_uncertain_cuts(self, timeline: list[Cut], n: int = 15) -> list[Cut]:
    """Sortiert Cuts nach Gesamt-Varianz absteigend, gibt Top-N zurueck."""

    scored = []
    for cut in timeline:
        total_variance = 0.0
        for axis in BRIDGE_AXES:
            ctx = cut.metadata.context_keys
            alpha, beta = self._get_alpha_beta(axis, ctx)
            variance = (alpha * beta) / (
                (alpha + beta) ** 2 * (alpha + beta + 1) + 1e-9
            )
            total_variance += variance
        scored.append((total_variance, cut))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [cut for _, cut in scored[:n]]
```

**Begründung:** Cuts mit hoher Varianz sind die, bei denen das Hirn unsicher
ist. Klicks darauf liefern den größten Lerneffekt pro Aufwand.

**Effizienz-Berechnung:**
15 Klicks × 102 Bucket-Updates (17 Achsen × 6 Levels — Level 0 wird mit-geschrieben damit Backoff-Lookup einen globalen Confidence-Anker hat) = 1275 Bucket-Updates pro Lern-Session.
Bei 3 Sessions pro Projekt = 3825 Bucket-Updates → typische Cold-Start-
Phasen für die häufigsten Kontexte verlassen.

---

## Reranker-Eingriffspunkt

```python
# Datei: services/brain_v3/reranker.py (Phase 4 TODO)
# Zweck: Eingriff in services/pacing/pipeline.py PacingPipeline.select_best()
#        (Zeile 145 Stand 2026-05-05, festgelegt User-Direktive 2026-05-05 F5).
#        Reranker uebernimmt die Stage-4-Sortierung: arbeitet auf der
#        scored-Liste (passed_stage2 == True + Stage-4-Soft-Scores),
#        nicht auf rohen Kandidaten. Stages 1-3 bleiben unangetastet.

class BrainV3Reranker:
    def __init__(self, brain_service: BrainV3Service):
        self.brain = brain_service

    def rerank(
        self,
        candidates: list[ClipCandidate],
        cut_context: CutContext,
    ) -> list[ScoredCandidate]:
        """Bewertet jeden Kandidaten via 17 Achsen + Kontext.

        Returns:
            Liste von ScoredCandidate, sortiert nach final_score absteigend.
            Jeder Kandidat enthaelt brain_v3_scores: dict[axis -> score].
        """
        scored = []
        for candidate in candidates:
            sub_scores = {}
            for axis in BRIDGE_AXES:
                bridge_value = self.brain.bridge.compute(
                    axis, candidate, cut_context
                )
                weight = self.brain.weights.get_posterior_mean(
                    axis, cut_context.context_keys
                )
                sub_scores[axis] = bridge_value * weight

            final_score = sum(sub_scores.values()) / len(sub_scores)
            scored.append(ScoredCandidate(
                candidate=candidate,
                final_score=final_score,
                brain_v3_scores=sub_scores,
            ))

        scored.sort(key=lambda x: x.final_score, reverse=True)
        return scored
```

**Eingriff in App-Bestand:** Hook in `services/pacing/pipeline.py`
`PacingPipeline.select_best()` (Zeile 145, Stand 2026-05-05). Nur
aktiv wenn `use_brain_v3 = True` (Eingriffspunkt fuer das Flag wird
in Phase-4-Blueprint Sektion 2.1 festgelegt — Default-Empfehlung:
Konstruktor-Parameter auf `PacingPipeline.__init__`). App-Eingriffspunkt
durch User-Direktive 2026-05-04 + 2026-05-05 (F5) freigegeben.
Reranker operiert auf der `scored`-Liste (Stage-4-Soft-Scoring-
Kandidaten, nicht auf rohen Kandidaten). Stages 1-3 (Hard-Rules,
Variations-Budget, Collision-Check) bleiben verbindlich.

---

## Reset-Verhalten

`BrainV3Service.reset()` mit Confirmation löscht **nur** den Hirn-Store
(`weights.db` + `patterns.db`), **nicht** den Embedding-Cache. Nach Reset:

- Cold-Start-Defaults aktiv für alle Achsen
- Alle Embeddings bleiben verfügbar
- Erneutes Klicken trainiert Hirn von vorne

Der Embedding-Cache bleibt absichtlich erhalten, weil die Embeddings selbst
keine User-Bewertung enthalten — nur die Modell-Outputs der ML-Modelle.

**API-Pattern (Phase 4, in-process — kein REST):**
```python
token_resp = service.reset()  # ohne Argument → BrainV3ResetTokenResponse(confirmation_token="abc123")
reset_resp = service.reset(BrainV3ResetConfirmRequest(confirmation_token="abc123"))
# → BrainV3ResetResponse(status="reset_complete")
```

Two-Step-Confirmation gegen versehentliches Reset.
