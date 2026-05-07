# Synthesis — Pre-Phase-4-Spike (Pacing-Config + Kontext-Mapping)

**Datum:** 2026-05-05
**Anlass:** L3 + O2 aus Plan-Patch — Pacing-Config-Eingriffspunkt waehlen
und 6-Kontext-Slot-Mapping festschreiben, bevor Phase-4-Code beginnt.
**Status:** **code-fix-pending-live-verification** (Spike ist Plan-
Recherche, kein Code-Edit; Decision in `D-035` proposed).

---

## 1. Ziel des Spikes

1. **L3:** Wo wird das Flag `use_brain_v3: bool` in der Pacing-API
   platziert? Drei Optionen (a/b/c) gegen die echte Code-Realitaet
   pruefen, eine Empfehlung geben, mit Code-Beleg.
2. **O2:** Wie werden die 6 Brain-V3-Backoff-Slots aus dem
   Pacing-State befuellt? Pro Slot: Quelle, Mapping, Quantisierung.

---

## 2. Befunde — Pacing-API-Realitaet

### 2.1 `PacingPipeline.__init__` Signatur (Stand 2026-05-05)

`services/pacing/pipeline.py` Z. 81–99:

```python
def __init__(
    self,
    scorer: PacingScorer | None = None,
    rules_path: str | Path = "config/pacing_rules.yaml",
    budgets: Mapping[str, BudgetRule] | None = None,
    dj_mix: bool = False,
    collision_min_similarity: float = 0.55,
    collision_strict: bool = False,
    decision_recorder: "DecisionRecorder | None" = None,
    run_id: int | None = None,
) -> None:
```

**Fakt:** es gibt **kein** zentrales `PacingConfig`-Objekt. Pacing-
Settings werden direkt als 8 Konstruktor-Parameter uebergeben.

### 2.2 Konsumenten von `PacingPipeline(...)` im Repo

| Datei | Zeile | Kontext |
|---|---|---|
| `services/pacing_service.py` | 722 | **Production-Pfad** (StudioBrain-Pacing-Pipeline) |
| `scripts/generate_golden_decisions.py` | 106 | Skript |
| `tests/pacing/test_pacing_stages.py` | 6× (54, 71, 88, 113, 135, 162) | Stage-Unit-Tests |
| `tests/integration/test_pacing_with_memory.py` | 4× (373, 457, 511, 544) | Integration-Tests |
| `tests/memory/test_decision_recorder.py` | 216 | Memory-Tests |
| `tests/functional_steer_tab_memory_loop.py` | 192 | Functional-Test |
| `tests/test_services/test_brain_wiring_b197.py` | 145 | Source-Inspection-Test (`assert "PacingPipeline(" in src`) |

**Total:** 2 Production-Stellen + 13 Test-Stellen = 15 Konsumenten.
Alle nutzen ausschliesslich **bestehende** Konstruktor-Parameter mit
Defaults — kein Code-Pfad waere durch ein zusaetzliches Default-
Parameter-Paar gebrochen.

### 2.3 `select_best()`-Hook-Punkt — bestaetigt

`services/pacing/pipeline.py` Z. 145, Signatur:
```python
def select_best(
    self,
    candidates: Sequence[ClipFeatures],
    ctx: AudioContext,
    predecessor: ClipFeatures | None = None,
    recent_clip_ids: Sequence[int] | None = None,
) -> PipelineResult:
```

`select_best()` hat **keinen `config`-Parameter**. Das Flag muss als
Instanz-Attribut auf `PacingPipeline` lesbar sein
(`self.use_brain_v3`, `self.brain_v3_min_confidence`).

---

## 3. Empfehlung L3 — Pacing-Config-Eingriffspunkt

### Option (a) — gewaehlt: 2 neue Konstruktor-Parameter

```python
def __init__(
    self,
    # ... bestehende 8 Parameter, UNVERAENDERT ...
    use_brain_v3: bool = False,                     # NEU
    brain_v3_min_confidence: float = 0.0,           # NEU
) -> None:
    # ... bestehender Body, plus:
    self.use_brain_v3 = use_brain_v3
    self.brain_v3_min_confidence = brain_v3_min_confidence
```

### Begruendung

| Aspekt | Bewertung |
|---|---|
| Konsistenz | passt zum bestehenden Pattern (bool/float-Defaults wie `dj_mix`, `collision_min_similarity`) |
| Risiko fuer Konsumenten | **Null** — alle 15 Konsumenten haben Defaults, additiv |
| Auffindbarkeit | Konstruktor-Signatur ist die kanonische API — erste Stelle wo ein neuer Entwickler Pacing-Konfig erwartet |
| Refactor-Schuld | minimal — falls spaeter ein zentrales `PacingConfig`-Dataclass kommt (Option c), kann `**kwargs`/Mapping-Migration in einem Schritt durchgefuehrt werden |
| Test-Aufwand | 1 zusaetzlicher Default-Test (`assert pipeline.use_brain_v3 is False` ohne Argument) |

**Verworfen:**
- Option (b) `AudioContext`-Feld: vermischt Audio-Daten mit App-Konfig,
  semantisch unsauber. AudioContext ist `frozen=True` per Cut, das Flag
  ist aber per Pipeline-Instanz konstant.
- Option (c) neues `PacingConfig`-Modul: zu grosser Refactor fuer ein
  einzelnes Flag-Paar; rechtfertigt sich erst bei 5+ Settings.

**Pflicht-Konsumenten-Update:** **keiner.** Alle 15 Konsumenten bleiben
funktional unveraendert. Nur wer Brain V3 aktivieren will, uebergibt
`use_brain_v3=True` — das geschieht in Phase 4 ueber den
`BrainV3Service`-Wrapper oder einen UI-Toggle.

---

## 4. Befunde — AudioContext (Pacing-State)

`services/pacing/scorer.py` Z. 32–57, `@dataclass(frozen=True) class AudioContext`:

| Feld | Typ | Wertebereich |
|---|---|---|
| `at_timestamp_sec` | float | Cut-Position |
| `at_beat_idx` | int \| None | Beat-Index oder None |
| `at_section_type` | str \| None | `intro\|buildup\|drop\|breakdown\|outro\|verse\|chorus\|bridge\|transition` (**9 Werte**) |
| `at_bpm` | float \| None | BPM |
| `at_energy` | float \| None | 0..1 |
| `at_key` | str \| None | musikalischer Key |
| `at_key_confidence` | float \| None | 0..1 |
| `at_harmonic_tension` | float \| None | 0..1 |
| `at_mood_audio` | str \| None | `energetic\|calm\|dramatic\|ambient` (**4 Werte**) |
| `at_mood_video` | str \| None | analog (audio-derived visual hint) |
| `at_genre` | str \| None | — |
| `at_sub_genre` | str \| None | — |
| `at_spectral_hash` | str \| None | 8-band signature |
| `at_groove_template` | str \| None | — |
| `at_lufs` | float \| None | Loudness |

`predecessor: ClipFeatures` enthaelt zusaetzlich `motion_score: float`
(0..1) und `embedding: np.ndarray | None`.

---

## 5. 6-Kontext-Slot-Mapping (O2)

Brain-V3-Ziel-Schema aus `services/brain_v3/context_resolver.py:36`:

| Slot | Ziel-Werte (CutContext) |
|---|---|
| `audio_section_type` | `intro\|verse\|build\|drop\|break\|outro\|transition` (**7 Werte**) |
| `audio_subtrack_position` | `start\|middle\|end` |
| `audio_energy_level` | `low\|medium\|high` |
| `audio_mood` | `dark\|neutral\|uplifting` |
| `video_motion_class` | `low\|medium\|high\|extreme` |
| `video_pace_class` | `slow\|medium\|fast` |

### 5.1 Mapping-Tabelle pro Slot

| # | Slot | Quelle | Mapping/Quantisierung | Status |
|---|---|---|---|---|
| 1 | `audio_section_type` | `ctx.at_section_type` | **9 → 7 Werte-Mapping noetig** (siehe 5.2) | **TBD — User-Klaerung** |
| 2 | `audio_subtrack_position` | `ctx.at_timestamp_sec` + Sub-Track-Boundaries | Helper `quantize_subtrack_position()` existiert in `context_resolver.py:99` | OK |
| 3 | `audio_energy_level` | `ctx.at_energy` | `quantize_tertile(at_energy, p33=0.33, p66=0.66)` | OK (Default-Schwellen, kann spaeter pro Mix kalibriert werden) |
| 4 | `audio_mood` | `ctx.at_mood_audio` | **4 → 3 Werte-Mapping noetig** (siehe 5.3) | **TBD — User-Klaerung** |
| 5 | `video_motion_class` | `predecessor.motion_score` (`ClipFeatures`) | `quantize_tertile()` mit 4 Klassen — **Helper unterstuetzt nur 3 Klassen, neuer 4-Klassen-Quantisierer noetig** | TBD — Code-Aufgabe |
| 6 | `video_pace_class` | **TBD — keine offensichtliche Quelle in AudioContext** | Optionen: (i) aus Cut-Density-Modulator (`services/pacing/cut_density_modulator.py`), (ii) aus Recent-Cut-Frequenz (Cuts pro 10 s), (iii) ableiten aus BPM | **TBD — User-Klaerung** |

### 5.2 Section-Type-Mapping (9 → 7)

`AudioContext` Werte → `CutContext` Werte. 4 Werte brauchen Mapping-
Entscheidung:

| AudioContext | CutContext (Default-Empfehlung) | Alternative | Begruendung |
|---|---|---|---|
| `intro` | `intro` | — | direkt |
| `verse` | `verse` | — | direkt |
| `chorus` | `drop` | `verse` | semantisch ist Chorus ein Energy-Peak, naeher an Drop |
| `bridge` | `transition` | `verse` | strukturell ein Uebergang |
| `buildup` | `build` | — | string-Trim |
| `drop` | `drop` | — | direkt |
| `breakdown` | `break` | — | string-Trim |
| `outro` | `outro` | — | direkt |
| `transition` | `transition` | — | direkt |

**User-Klaerung pflicht** fuer `chorus` und `bridge` (zwei semantisch
unscharfe Faelle).

### 5.3 Mood-Mapping (4 → 3)

| AudioContext | CutContext (Default-Empfehlung) | Alternative | Begruendung |
|---|---|---|---|
| `energetic` | `uplifting` | — | direkt |
| `calm` | `neutral` | `uplifting` | calm ist nicht uplifting, neutral ist passender |
| `dramatic` | `dark` | `neutral` | dramatic ist tendentiell schwer, dark passt |
| `ambient` | `neutral` | `dark` | ambient ist tonal-offen, neutral passender |

**User-Klaerung empfohlen** — die Default-Empfehlungen sind plausibel,
aber Stilfrage.

### 5.4 `video_pace_class`-Quelle (offen)

Drei Optionen:

| # | Option | Pro | Contra |
|---|---|---|---|
| (i) | aus `cut_density_modulator.py` | semantisch sauber, schon im Pacing-Code | erfordert Zugriff auf Pacing-internal-State |
| (ii) | aus Recent-Cut-Frequenz (cuts/10s aus `recent_clip_ids`) | nur Daten die im Pipeline-Hook eh verfuegbar sind | Approximation, nicht echtes Pace-Mass |
| (iii) | ableiten aus `at_bpm` (slow <100 / medium 100-130 / fast >130) | trivial verfuegbar, kein neuer State | nicht "Video-Pace" sondern "Audio-BPM" — Plan-Doc 05 nennt es `video_pace_class` |

**Empfehlung:** Option (ii) — Recent-Cut-Frequenz: Cuts pro 10 s aus
`len(recent_clip_ids)`-aequivalentem Zaehler. Slow <2 cuts/10s,
medium 2-5, fast >5. Begruendung: das ist tatsaechlich Cut-Pace, nicht
Audio-BPM. Aber: **User-Klaerung pflicht**, weil semantischer Slot.

---

## 6. Konsequenzen / Aufwand

### Vor Phase-4-Code-Start zu klaeren (User)

1. Section-Mapping `chorus` und `bridge` — Empfehlung Default akzeptieren? (~2 Min)
2. Mood-Mapping (4 Optionen) — Default akzeptieren? (~3 Min)
3. `video_pace_class`-Quelle — Option (i)/(ii)/(iii)? (~5 Min)
4. `D-035` Vault-Decision von `proposed` auf `adopted` setzen

### Code-Arbeit (Phase 4, in `services/brain_v3/`)

- `build_cut_context(ctx, predecessor, recent_clip_ids) -> CutContext`
  Helper schreiben (~30 Min)
- 4-Klassen-Quantisierer `quantize_quartile()` fuer
  `video_motion_class` ergaenzen — kann in `context_resolver.py`
  hinzukommen (~15 Min)
- Pacing-Pipeline-Konstruktor erweitern (~5 Min)

### Test-Aufwand

- 1 Default-Test fuer `PacingPipeline.use_brain_v3 is False` (~5 Min)
- Mapping-Tests pro Slot (~30 Min)
- Regression-Test fuer alle 13 bestehenden Pacing-Tests (kein Edit
  noetig, Defaults greifen)

---

## 7. Verweise

- Plan: `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/phase_blueprints/phase_4_pacing_integration.md` Sektion 2.1 + 4.7
- Code: `services/pacing/pipeline.py:81` (Konstruktor),
  `services/pacing/pipeline.py:145` (`select_best`),
  `services/pacing/scorer.py:32` (`AudioContext`),
  `services/brain_v3/context_resolver.py:36` (`CutContext`)
- Decision (proposed): `wiki/decisions/D-035-brain-v3-pacing-config-eingriffspunkt.md`
- Vault-Spiegel dieser Synthesis: `wiki/synthesis/2026-05-05-pre-phase4-spike.md`

---

## 8. Status-Marker

- **Spike ausgefuehrt:** ✓ 2026-05-05 (Code-Grep + Plan-Cross-Check)
- **Empfehlungen formuliert:** ✓
- **User-Bestaetigung erledigt:** ✓ 2026-05-05 — User-Direktive
  „kann mich nicht entscheiden ma beste variabel umschaltbar".
  Konsequenz: M1 + M2 + M3 werden **nicht hardcoded**, sondern als
  konfigurierbare Defaults mit YAML-Override implementiert.
  Vault-Decision: **D-036 adopted** (siehe
  `wiki/decisions/D-036-brain-v3-context-mapping-konfigurierbar.md`).
- **Phase-4-Code-Start (Pacing-Hook):** technisch **freigegeben** —
  Konstruktor-Eingriff (D-035 adopted) + Mapping-Strategie
  (D-036 adopted) sind beide entschieden.

## 9. Resolution-Stand der drei Mapping-Konflikte

| # | Konflikt | Loesung | Status |
|---|---|---|---|
| **M1** | Section-Mapping `chorus`/`bridge` | `cfg.section_mapping[...]` mit Default `chorus→drop`, `bridge→transition`. Override via YAML moeglich. | resolved-via-config (D-036) |
| **M2** | Mood-Mapping `calm`/`dramatic`/`ambient` | `cfg.mood_mapping[...]` mit Default `calm→neutral`, `dramatic→dark`, `ambient→neutral`. Override via YAML moeglich. | resolved-via-config (D-036) |
| **M3** | `video_pace_class`-Quelle | `cfg.pace_source` mit Default `"recent_cuts"`. Alternativen `"cut_density"` und `"bpm"` per YAML waehlbar. | resolved-via-config (D-036) |
