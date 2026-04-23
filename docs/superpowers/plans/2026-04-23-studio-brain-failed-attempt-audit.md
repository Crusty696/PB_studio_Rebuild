# Studio-Brain-Implementation — Audit gegen Plan

**Datum:** 2026-04-23 (Audit)
**Basis-Commit (Ausführung):** `a3b04da` — "Implement Studio Brain (Phase 6)"
**Plan-Dokument:** `docs/superpowers/plans/2026-04-23-studio-brain-plan.md`
**Verdikt:** **NICHT release-ready.** Kritische Release-Gates fehlen; Pacing-Scorer implementiert eine völlig andere Formel als Spec; Release-Gate-Bug in Wilson-Fallback; Plan-Commit-Disziplin verletzt.

---

## Zusammenfassung auf einen Blick

- **1 einziger Commit** statt ~60 TDD-Commits (Plan-Disziplin verletzt).
- **`TODO_STUDIO_BRAIN.md` markiert alles als erledigt**, obwohl mehrere Release-Gate-Dateien und ganze Konfig-Ordner fehlen.
- **Wilson-Fallback liefert `0/0 → 0.0`** (Release-Gate-Regel R6 und Test aus P2-Plan verletzt — `0/0` muss `0.5` sein, sonst werden alle neuen Clips als „schlecht" behandelt).
- **Mood-Anchor-Release-Gate existiert gar nicht** (keine `mood_anchors.npz`, keine `test_mood_anchor_orthogonality.py`, kein Generationsskript).
- **PacingScorer nutzt völlig andere Term-Namen** als Spec & Plan; Key, Tension, Genre, Mood, Spectral, Groove werden komplett ignoriert → **der Kernnutzen des Studio-Brain wird nicht erreicht**.
- **4-stufige Pacing-Pipeline ist dreistufig** — Kollisions-Check (Stage 3) fehlt ersatzlos.
- **`DecisionRecorder` wird nirgendwo aufgerufen** — kein Pacing-Run schreibt je eine `mem_decision`. Gedächtnis kann dadurch nicht lernen.

---

## 1. Fehlende Dateien (gegen Plan vollständig nicht vorhanden)

### Release-Gate-kritisch

| Plan | Status | Wirkung |
|---|---|---|
| `tests/enrichment/test_mood_anchor_orthogonality.py` | **FEHLT** | **Release-Gate 1** nicht testbar. Feasibility §7 Bedingung 5 verletzt. |
| `config/mood_anchors.npz` | **FEHLT** | Mood-Refinement arbeitet blind, ohne SigLIP-Anchors. |
| `config/mood_anchors_v1.yaml` | **FEHLT** | Prompt-Katalog existiert nur im Design-Doc. |
| `scripts/generate_mood_anchors.py` | **FEHLT** | Anchor-Generierung unmöglich ohne Skript. |

### Module & Pipelines

| Plan | Status | Ersatz / Kommentar |
|---|---|---|
| `services/stats/wilson_lower_bound.py` | **FEHLT** | Nach `services/pacing_utils.py` verschoben (API-inkompatibel, s. u.). |
| `services/brain_service.py` | **FEHLT** | UI-Tabs lesen direkt aus der DB — kein Cache-Layer. |
| `config/pacing_rules.yaml` | **FEHLT** | Section×Role-Matrix existiert überhaupt nicht. |
| `config/pacing_weights/default.yaml` | **FEHLT** | Nur flache `config/pacing_weights.yaml` mit FALSCHEN Term-Namen. |
| `config/pacing_weights/psytrance.yaml` | **FEHLT** | Genre-Profile unmöglich. |
| `config/pacing_weights/house.yaml` | **FEHLT** | Genre-Profile unmöglich. |
| `config/pacing_weights/dj_mix_auto.yaml` | **FEHLT** | Mid-Run-Profilwechsel unmöglich. |
| `scripts/generate_test_dj_mix.py` | **FEHLT** | 3h-Synthese-Audio für `test_dj_mix_3h` nicht generierbar. |
| `ui/studio_brain/structure_tab.py` | **FEHLT** | Kein separates Modul — in Monolith eingebaut. |
| `ui/studio_brain/memory_tab.py` | **FEHLT** | dito. |
| `ui/studio_brain/audit_tab.py` | **FEHLT** | dito. |
| `ui/studio_brain/steer_tab.py` | **FEHLT** | dito. |
| `ui/studio_brain/__init__.py` | **FEHLT** | Package existiert nicht. |

### Tests

| Plan | Status | Kommentar |
|---|---|---|
| `tests/pacing/test_wilson_lower_bound.py` | **FEHLT** | Wilson-Fallback 0/0 nicht getestet. |
| `tests/enrichment/test_mood_anchor_orthogonality.py` | **FEHLT** | **Release-Gate.** |
| `tests/enrichment/test_umap_hdbscan_pipeline.py` | **FEHLT** | Reducer-Pickle-Roundtrip nicht getestet. |
| `tests/ui/test_feedback_shortcuts.py` | **FEHLT** | Feedback-Shortcut-Verhalten ungetestet. |
| `tests/memory/test_pattern_aggregator.py` | **FEHLT** | `test_memory_layer.py` deckt das nicht gleichwertig ab. |
| `tests/memory/test_decision_recorder.py` | **FEHLT** | Snapshot-Integrität nicht validiert. |
| `tests/pacing/test_pacing_stages.py` | **FEHLT** | Fallback-/Forced-Verhalten ungetestet. |
| `tests/integration/test_full_enrichment.py` | **FEHLT** | In `test_enrichment_worker.py` nur teilweise. |
| `tests/integration/test_pacing_with_memory.py` | **FEHLT** | Zwei-Runs-Lernkurve nicht getestet. |

---

## 2. Falsche Benennungen (funktional evtl. ok, aber Plan-inkonform)

Diese Umbenennungen sind bei späteren Agenten-Sessions Fehlerquelle (Agent folgt Plan → findet Datei nicht).

| Plan-Name | Tatsächlich | Ort |
|---|---|---|
| `services/enrichment/mood_anchor_matcher.py` | `mood_refiner.py` | `services/enrichment/` |
| `services/enrichment/style_bucket_clusterer.py` | `style_clusterer.py` | `services/enrichment/` |
| `services/pacing/decision_recorder.py` | — | nach `services/memory/` verschoben |
| `services/pacing/pattern_aggregator.py` | — | nach `services/memory/` verschoben |
| `services/pacing/scorer.py` | `pacing_scorer.py` | `services/pacing/` |
| `workers/structure_enrichment.py` | `enrichment.py` | `workers/` |
| `ui/studio_brain_window.py` | `ui/windows/studio_brain_window.py` | tiefer verschachtelt |
| `ui/story_map_dialog.py` | `ui/dialogs/story_map_dialog.py` | tiefer verschachtelt |
| `tests/enrichment/`, `tests/pacing/`, `tests/memory/` | alles in `tests/test_services/` | flach zusammengeführt |
| `test_onset_chunked_boundary.py` | `test_onset_chunking.py` | Release-Gate-Name verloren |
| `test_dj_mix_3h.py` | `test_dj_mix_stress.py` | |
| `test_golden_run_snapshot.py` | `test_golden_run_regression.py` | |
| `tests/integration/test_pacing_performance.py` | `tests/performance/test_enrichment_throughput.py` | |

---

## 3. Inhaltliche Kritische Bugs in vorhandenem Code

### Bug A — **Wilson `0/0 → 0.0` statt `0.5`** (Release-Gate-Violation)

**Datei:** `services/pacing_utils.py:29-30`

```python
if total == 0:
    return 0.0
```

**Soll (Plan + Spec + Feasibility-R6):** `0/0 → 0.5` (neutral „weiß nichts").

**Wirkung:** `PacingScorer` gewichtet `w_memory_boost = pattern.confidence`. Für jeden Clip ohne History ergibt das 0 → der Agent behandelt **jeden nie gesehenen Clip als 'schlecht, vermeiden'**. Das ist ein Systembias, der den Kernnutzen (Gedächtnis lernt, Agent wird besser) sabotiert.

### Bug B — **PacingScorer benutzt komplett falsche Terme**

**Datei:** `services/pacing/pacing_scorer.py:32-46`

Implementiert sind:
```
w_energy_match, w_role_match, w_novelty, w_rhythm_sync,
w_memory_boost, w_style_continuity, w_color_cohesion,
w_subject_focus, w_clip_stability, w_freshness, w_vibe_match,
w_transition_smoothness, w_human_presence
```

Spec + Plan §6.5 verlangen:
```
w_role, w_style, w_mood_video, w_mood_audio, w_genre, w_key,
w_tension, w_energy, w_spectral, w_groove, w_memory,
w_collision, w_freshness
```

**Wirkung:**
- `w_genre`, `w_key`, `w_tension`, `w_spectral`, `w_groove`, `w_mood_audio`, `w_collision` **existieren nicht**.
- Audio-Kontext (Genre, Musik-Key, Harmonic-Tension, Spektral-Profil, Groove) aus der bestehenden 9-stufigen Audio-Analyse wird **gar nicht** in die Pacing-Entscheidung integriert.
- Sieben der 13 implementierten Terme (`w_novelty`, `w_color_cohesion`, `w_subject_focus`, `w_clip_stability`, `w_vibe_match`, `w_transition_smoothness`, `w_human_presence`) liefern **Placeholder 0.5** oder Mocks → effektiv totes Gewicht.
- **Das Studio-Brain erreicht den im PRD geforderten Zweck nicht.**

### Bug C — **Scoring-Formel normalisiert durch Gewichtssumme**

**Datei:** `services/pacing/pacing_scorer.py:149-156`

```python
for name, weight in self.weights.items():
    val = terms.get(name, 0.5)
    total_score += val * weight
    total_weight += weight
if total_weight > 0:
    total_score /= total_weight
```

Plan-Formel ist **gewichtete Summe ohne Normalisierung durch Gewichtssumme**. Dadurch verlieren höhere Gewichte ihre relative Bedeutung — im gegebenen Defaults mit 13 Termen kippt der Effekt stark: wenn Gewichte nicht exakt auf 1.0 summieren, wird jeder Term praktisch gleichbehandelt. Spec-Intention unterlaufen.

### Bug D — **Stage 3 „Kollisions-Check" fehlt komplett**

**Datei:** `services/pacing/pacing_pipeline.py`

Pipeline hat 3 Stages (Filter, Budget, Score+Select). Plan §6.1 verlangt **4 Stages**: Hard-Rules, Budget, **Kollision**, Score. Der `CompatGraphBuilder` existiert, wird aber nie vom PacingPipeline konsumiert.

### Bug E — **Stage 1 „Hard Rules" existiert nicht**

**Datei:** `services/pacing/pacing_pipeline.py:64`

```python
filtered = [c for c in candidates if c.get("motion_score") is not None]
```

Das ist kein Hard-Rules-Gate. Plan §6.2 verlangt **Section × Role Matrix**: `drop → {hero, action}`, `breakdown → {detail, ambient, establishing}`, etc. Der `struct_clip_tags.role` wird gar nicht ausgewertet.

### Bug F — **`DecisionRecorder` wird nirgendwo aufgerufen**

**Datei:** `services/memory/decision_recorder.py` existiert, aber **kein Produktionspfad** ruft `record()` auf:

```
$ grep -rn "DecisionRecorder" services/ agents/ workers/ ui/
services/memory/decision_recorder.py   (Definition)
```

Kein einziger Import im übrigen Code. Jeder Pacing-Run führt **keine** Decisions in `mem_decision` → der ganze Lern-Loop bricht hier ab. **PRD User-Story 9 nicht erfüllt.**

### Bug G — **PatternAggregator überspringt `at_enricher_version`-Filter**

**Datei:** `services/memory/pattern_aggregator.py:65-101`

Plan P7.2: „aggregator skips stale enricher version". Implementierung iteriert **alle** Decisions ohne Enricher-Version-Check → nach Re-Clustering kippt das Gedächtnis (alte Cluster-IDs existieren in Snapshots, die neuen Buckets überlappen nicht). **Feasibility-R4-Mitigation verletzt.**

### Bug H — **PatternAggregator nutzt BPM als Float-Key**

**Datei:** `services/memory/pattern_aggregator.py:93`

```python
fingerprint_key = (d.at_genre, d.at_section_type, d.at_bpm, d.scene_id)
```

BPM-Werte wie `139.98` und `140.01` erzeugen zwei getrennte Pattern-Zeilen. Plan verlangt Bucketing (z. B. ganzzahlige BPM oder 5er-Schritte).

### Bug I — **PatternAggregator: N+1-Query pro Decision**

**Datei:** `services/memory/pattern_aggregator.py:80`

```python
run = session.get(MemPacingRun, d.run_id)
```

Pro Decision ein Extra-Query. Bei 5000 Decisions = 5000 Extra-Roundtrips. Auch ohne Index-Hit wird das bei wachsendem Gedächtnis spürbar. Plan empfiehlt `JOIN`-basierte Aggregation.

### Bug J — **PatternAggregator: lineare Pattern-Suche in Python**

**Datei:** `services/memory/pattern_aggregator.py:134-143`

Lädt bei jeder Update-Iteration **alle** `MemLearnedPattern`-Zeilen ins RAM und sucht linear → O(N²). Skaliert nicht auf mehr als ~100 Patterns.

### Bug K — **Wilson-API-Divergenz von Plan T2.1**

**Datei:** `services/pacing_utils.py:11`

Plan-Vertrag: `wilson_lower_bound(accepts, total, z=1.96)`. Implementierung: `WilsonLowerBound.calculate(ups, total, confidence=0.95)`. Tests aus Plan (`z=2.576`) würden nie grün werden, weil der Parameter nicht existiert.

### Bug L — **`datetime.utcnow()` deprecated**

**Datei:** `services/memory/pattern_aggregator.py:150, 161`

Python 3.12+ warnt: `datetime.utcnow()` ist deprecated. Soll `datetime.now(timezone.utc)` sein. Nicht funktional kritisch, aber zukunftsbrüchig.

---

## 4. Plan-Disziplin-Verletzungen

- **Ein einziger Commit** (`a3b04da`, +4754/-553 Zeilen): unmöglich einzelne Tasks zu reverten. Plan forderte `feat(x): …`-Commit pro Deep-Module. Bei einem Bug muss nun alles-oder-nichts rückgängig gemacht werden.
- **LLM-Pacing-Refactor (R3) nicht als eigener Sub-PR** (Feasibility §7 Bedingung 8).
- **`TODO_STUDIO_BRAIN.md` lügt** — alle Aufgaben ticked, obwohl Release-Gate-Tests und Kernkonfig-Dateien fehlen.

---

## 5. Was funktionell korrekt ist (nicht alles ist schlecht)

Anerkennend:

- Migrations A/B/C sind da und haben die Schema-Ergänzungen `struct_style_bucket.active` und `mem_decision.at_enricher_version`.
- `RoleClassifier` existiert und wirkt regelbasiert.
- `CompatGraphBuilder`, `StyleClusterer` existieren (Qualität noch nicht geprüft).
- `OnsetRhythmService`-Erweiterung ist vorhanden (Qualität noch nicht geprüft).
- `build_test_fixture.py` (T0.1a) ist gebaut und mit Tests abgedeckt.
- `BackupService` ist implementiert.
- `StudioBrainWindow` ist als Monolith da und lässt sich öffnen (Offscreen-Test vorhanden).

---

## 6. Empfohlene Reparatur-Reihenfolge (Risiko-priorisiert)

### Stufe R1 — Release-Gate & Kern-Bugs (MUSS, bevor irgendwas released wird)

1. **Bug A fixen:** Wilson-Fallback `0/0 → 0.5`. 1-Zeilen-Fix + `tests/pacing/test_wilson_lower_bound.py` nachziehen.
2. **Plan-API wiederherstellen:** `services/stats/wilson_lower_bound.py` mit Plan-Signatur `(accepts, total, z=1.96)` anlegen; alter Pfad als Shim.
3. **Mood-Anker aufbauen:**
   - `config/mood_anchors_v1.yaml` mit den 10 Prompts aus Research §Q4.
   - `scripts/generate_mood_anchors.py`.
   - `config/mood_anchors.npz` generieren.
   - `tests/enrichment/test_mood_anchor_orthogonality.py` (Release-Gate).
4. **Bug B fixen:** `PacingScorer` komplett neu mit den 13 Spec-konformen Termen; alle Audio-Kontext-Felder (`at_genre`, `at_key`, `at_tension`, `at_spectral_hash`, `at_groove_template`, `at_mood_audio`) verdrahten.
5. **Bug D+E fixen:** 4-Stage-Pipeline — Hard-Rules (Section×Role-Matrix aus `config/pacing_rules.yaml`), Budget (bereits da), Kollisions-Check gegen `struct_compat_edge`, Soft-Scoring.
6. **Bug F fixen:** `DecisionRecorder` im `PacingPipeline.select_best_scene` am Ende jeder Entscheidung aufrufen; vollen Kontext-Snapshot schreiben.

### Stufe R2 — Qualitäts-Bugs (SOLL, bevor größere Datenmengen verarbeitet werden)

7. **Bug G fixen:** `at_enricher_version`-Filter im Aggregator.
8. **Bug H fixen:** BPM-Bucketing in Fingerprint.
9. **Bug I+J fixen:** N+1-Query via JOIN, Pattern-Lookup via SQL-Query statt Python-Iteration.
10. **Bug C fixen:** Scoring ohne Gewichtssumme-Normalisierung (oder explizit dokumentieren, wenn gewollt).
11. **Bug L fixen:** `datetime.now(timezone.utc)` überall.

### Stufe R3 — Plan-Konformität (KANN, für Wartbarkeit)

12. `config/pacing_weights/` Ordner mit `default.yaml` + 3 Genre-Profilen anlegen, Pipeline darauf umstellen.
13. `config/pacing_rules.yaml` mit Section×Role-Matrix.
14. Fehlende Tests (Orthogonality + Wilson + UMAP-Pipeline + Feedback + Pattern-Aggregator + DecisionRecorder + Pacing-Stages) ergänzen.
15. `TODO_STUDIO_BRAIN.md` ehrlich machen (nicht alles ticked).
16. Optional: Dateien gemäß Plan umbenennen (oder den Plan an die Realität anpassen — Entscheidung beim User).

---

## 7. Was ich als Nächstes vorschlage

Die Reparatur umfasst mindestens **20-30 Sub-Änderungen** mit teilweise fundamentalem Umfang (PacingScorer neu schreiben, 4. Stage einziehen, DecisionRecorder verdrahten). Das ist nicht in einer Sitzung safe abgearbeitet.

**Dringend entscheiden:**

- **Variante A — Ich repariere autonom Stufe R1 in dieser Sitzung** und committe Task-weise. Stufe R2 + R3 folgen in späteren Sessions. Du reviewst am Ende.
- **Variante B — Ich nehme nur einen Bug pro Antwort**, zeige dir Diff + Test, du gibst OK, nächster. Langsam, maximal sicher.
- **Variante C — Revert `a3b04da`** (zurück auf den reinen Plan-Stand) und Neustart mit `subagent-driven-development`, das pro Task einen frischen Agenten dispatcht und zwischen Tasks reviewen lässt.

Mein Rat: **C**, weil der aktuelle Stand so viele konzeptionelle Fehlentscheidungen hat (falsche Scorer-Terme, fehlende Kollisions-Stage, fehlender DecisionRecorder-Aufruf), dass der Repair-Aufwand in der Summe nahe am Neubau liegt — und bei A/B die Gefahr hoch ist, dass wir am Ende einen Flickenteppich haben, der weder Plan noch Neubau ist.

Wenn du aber Zeit sparen willst: **A**, aber mit klarer Sub-Stufen-Commits, damit wir am Ende der Session ein sauberes Branch-State haben.
