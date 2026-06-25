# 11 — Re-Verifikations-Report Phase 3 (2026-05-05)

**Anlass:** Zweite Re-Verifikations-Welle nach Phase-3-Implementation +
Sub-Task-Atomarität-Klärung + Vault-Spiegelung.

---

## A. Methodik

| Achse | 1. Welle | 2. Welle (jetzt) |
|---|---|---|
| Phasen-Status | Plan-Tabelle in `06_PHASES.md` | **Cross-Check Plan-Tabelle vs. Top-README + Blueprint-README + Test-Output** |
| Vault-Spiegel | `wiki/synthesis/brain-v3-phase3-completion-2026-05-05.md` | **Glob-Audit aller 5 Vault-Synthesen** |
| Test-Count | letzter Lauf | **Grep "112 passed" über alle Repo-Docs + Vault** |
| Banner-State-Markers | nach Phase 3 hinzugefügt | **Grep 🟢/🔴 über alle 4 Blueprints** |
| Konstanten-Konsistenz | nicht geprüft | **Code-Cross-Check: BRIDGE_AXES, MIN_CONFIDENT_SAMPLES, RATING_MAP** |
| **Plan-vs-Code-Drift** | nicht geprüft | **Bucket-Anzahl pro Klick: Plan sagte 85, Code sagt 102 → DRIFT gefunden** |

---

## B. Befunde der 2. Welle

### B.1 Banner-Konsistenz ✓ GRÜN

```text
phase_3_brain_core.md:3        🟢 PHASE 3 IST IMPLEMENTIERT + 112/112 PYTEST GRÜN
phase_4_pacing_integration.md:3 🔴 TODO — BUILD-FROM-SCRATCH-MODE
phase_5_pyside6_ui.md:3          🔴 TODO — BUILD-FROM-SCRATCH-MODE
phase_6_haertung.md:3            🔴 TODO — BUILD-FROM-SCRATCH-MODE
```

Alle 4 Blueprints haben State-Banner GANZ OBEN (Zeile 3). Phantom-Sub-Task-
Frage in nächster Phase wird vermieden.

### B.2 Test-Count "112" Konsistenz ✓ GRÜN

| Quelle | Wert |
|---|---|
| `outputs/pytest_brain_v3_results.txt` | "112 passed in 28.18s" |
| Top-`README.md` | "✓ 112/112 pytest (Lauf 2026-05-05)" |
| `phase_blueprints/README.md` | "🟢 DONE — 112/112 pytest" |
| Repo-Synthesis Phase 3 | "112/112 pytest grün" + "42 NEU, total 112" |
| Vault-Spiegel Phase 3 | "112/112 grün, 28.2 s" |
| Vault `log.md` 2026-05-05 | "112/112 passed in 28.18 s" |

Alle 6 Stellen identisch ✓.

### B.3 Vault-Spiegel komplett ✓ GRÜN

```text
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\
├── brain-v3-plan-audit-2026-05-05.md
├── brain-v3-phase0-gpu-coexistence-2026-05-03.md       (status: fixed)
├── brain-v3-phase1-completion-2026-05-03.md             (status: code-fix-pending-live-verification)
├── brain-v3-phase2-completion-2026-05-03.md             (status: code-fix-pending-live-verification)
└── brain-v3-phase3-completion-2026-05-05.md             (status: code-fix-pending-live-verification)
```

5/5 Synthesen vorhanden + verlinkt in Vault `log.md` 2026-05-05.

### B.4 Code-Konstanten-Konsistenz ✓ GRÜN

| Konstante | Quelle | Wert |
|---|---|---|
| `BRIDGE_AXES` | `cold_start.py:9` | 17 Achsen tuple (Plan-konform) |
| `MIN_CONFIDENT_SAMPLES` | `weight_store.py:27` | 10 (Plan-konform) |
| `RATING_MAP` | `feedback_logger.py:23` | 4 Ratings mit (α, β)-Deltas (Plan-konform) |
| Klassen | brain_v3 | WeightStore, FeedbackLogger, BrainStore, BrainStoreStats — alle vorhanden |

### B.5 Plan-vs-Code-DRIFT GEFUNDEN + KORRIGIERT

**Drift-Befund:** Plan-Doc sagte "5 Backoff-Levels × 17 Achsen = **85** Buckets",
aber Code (context_resolver liefert 6 Keys, feedback_logger updated alle)
nutzt **17 × 6 = 102** Buckets. Phase-3-Blueprint hatte das schon erkannt
("Phase 3 verwendet 6 Levels statt 5"), aber andere Plan-Docs waren
inkonsistent.

**Root-Cause:** Plan-Doc zählt Level 0 (global) + Level 1-5 = 6 Levels,
multipliziert aber fälschlich mit 5 statt 6. Code-Realität ist 6 Levels
(Level 0..5 inklusive), weil Level 0 mit-geschrieben werden muss damit
Backoff-Lookup einen globalen Confidence-Anker hat.

**Korrigiert (alle 8 Stellen):**

| Datei | Zeile | Vorher | Nachher |
|---|---|---|---|
| `services/brain_v3/feedback_logger.py:3` | docstring | "5 Backoff-Levels × 17 Achsen = 85" | "6 Backoff-Levels (0..5) × 17 Achsen = 102" |
| `feedback_logger.py:42, 50, 98` | docstring/log | "85 Buckets" | "102 Buckets" |
| `02_DECISIONS.md:73` | Begründung #11 | "= 85 Bucket-Updates" | "= 102 Bucket-Updates (Plan-Schreibfehler korrigiert)" |
| `01_ARCHITECTURE.md:98` | Datenfluss | "5 Backoff-Levels × 17 Achsen = 85" | "6 Backoff-Levels (0..5) × 17 Achsen = 102" |
| `01_ARCHITECTURE.md:129` | V3-Vergleich | "(85 Buckets/Klick)" | "(102 Buckets/Klick)" |
| `04_DATA_MODEL.md:368` | Datenfluss-Beispiel | "(17 × 5 = 85)" | "(17 × 6 = 102)" |
| `05_BRIDGE_AXES.md:161, 257` | "85 Bucket-Updates" | "102 Bucket-Updates" |
| `06_PHASES.md:162` | feedback_logger-Aufgabe | "5 Levels × 17 Achsen = 85" | "6 Levels (0..5) × 17 Achsen = 102" |
| `06_PHASES.md:177` | DoD | "aller 85 Buckets" | "aller 102 Buckets" |
| `07_RISKS.md:11` | R05 Mitigation | "(85 Buckets/Klick, 1275/Session)" | "(102 Buckets/Klick, 1530/Session)" |
| `07_RISKS.md:49` | R05 Detail | "~85 Buckets pro Klick" | "102 Buckets pro Klick" |
| `phase_3_brain_core.md` | mehrere | "85-Bucket-Update", "85 Bucket-UPSERTs" | "102-Bucket-Update", "102 Bucket-UPSERTs" |
| Vault `brain-v3-phase3-completion-2026-05-05.md:27` | "Atomic-85-Bucket-Update" | "Atomic-102-Bucket-Update (17 Achsen × 6 Levels)" |

**Verifikation:** Grep nach "85 Bucket|85-Bucket|17 × 5|atomic 85|aller 85" über
gesamten Plan-Ordner + Vault → **0 Treffer**. Alle Stellen sind synchron auf 102.

**Test-Auswirkung:** Edits sind **docstring-only** (keine Logik-Änderung).
Test `test_log_feedback_updates_85_buckets` (Test-Funktionsname enthält
historisch "85") prüft `n_buckets_updated == 17 * 6 == 102` und ist seit
Phase-3-Lauf grün. Test-Funktionsname kann später umbenannt werden, aber
nicht Logik-relevant.

### B.6 README.md Top-Level Drift ✓ KORRIGIERT

| Stelle | Vorher | Nachher |
|---|---|---|
| Dokumente-Tabelle | nur 01–08 | 01–10 + `phase_blueprints/`-Verweis ergänzt |
| Aufwand-Schätzung | "Phase 3: 3-5 Tage" | "Phase 3: DONE (Brain-Core, 112/112 pytest, Lauf 2026-05-05)" |

### B.7 Cross-Check `phase_blueprints/README.md` ✓ GRÜN

Status-Tabelle stimmt mit Top-README überein. Status-Schema-Erklärung
(🟢/🟡/🔴) vorhanden.

---

## C. Verdict

**Plan-Set + Code + Vault sind konsistent nach 2. Re-Verify-Welle:**

- **1 echter Drift gefunden + komplett behoben:** Plan-Doc sagte 85 Buckets,
  Code-Realität ist 102. **8 Stellen synchronisiert.**
- **Vault-Spiegelung komplett:** 5/5 Phasen-Synthesen im Vault, alle mit
  Status-Marker
- **Banner-Konsistenz:** alle 4 Blueprints haben State-Banner ganz oben →
  Phantom-Sub-Task-Frage vermieden
- **Test-Count konsistent:** 112/112 in 6 unabhängigen Stellen
- **Code-Konstanten konsistent:** BRIDGE_AXES (17), MIN_CONFIDENT (10),
  RATING_MAP (4) in Code + Tests + Doku übereinstimmend

**Phase 4 darf gestartet werden.** Pre-Check für Claude Code:
1. `services/brain_v3/reranker.py` und `services/brain_v3/brain_v3_service.py`
   dürfen NICHT existieren (sonst Verify-Mode)
2. `phase_blueprints/phase_4_pacing_integration.md` Banner ist 🔴 TODO
3. App-Eingriff in `services/pacing/pipeline.py` (Klasse `PacingPipeline`,
   konkrete Selektor-Funktion vor Edit per Grep verifizieren) ist
   freigegeben (Plan-Doc 02 #24 + User-Direktive 2026-05-05 F1: in-process)

---

## D. Lessons Learned (für Phase 4)

1. **State-Banner JEDER Phase-Doku** — nie wieder "Hinweis am Ende" verstecken
2. **Bucket-Anzahl-Mismatch** war Plan-internes Definitions-Problem, nicht
   Code-Bug — Plan muss Code-Wahrheit folgen wenn Code live verifiziert ist
3. **Skalen-Mismatch Cold-Start vs. Posterior** (TriggerSettings 0–2 vs.
   Bayes 0–1) ist relevante API-Subtilität für Phase-4-Scorer — bereits
   in Phase-3-Synthesis dokumentiert
