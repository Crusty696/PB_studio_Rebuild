# Full-Stack-Audit — heute implementierter Code (2026-07-08/09)

> Read-only-Audit. KEINE Code-Aenderungen vorgenommen. 100% ehrlich,
> inkl. was NICHT verifiziert werden konnte.

## Umfang

~34 Produktiv-Code-Dateien in ~25 Code-Commits (Branch
`claude/NEUBAU-VOLLINTEGRATION-2026-07-07`, gemergt nach `codex/OTK-021`).
Schwerpunkte: 3 Crash-Fixes (B-611/B-612/B-613), M2 (T1.2–T1.6, Studio-Brain),
M3 (DAG-Video-Engine), B-359-RAM-Fix, UI-Async-Fixes, Timeline-Instrumentierung.

## Verifikations-Status (ehrlich)

| Bereich | Status | Beleg |
|---|---|---|
| B-611 Export-Rundung | **live-verifiziert** | GUI-Render Projekt 21, 0 Crashes an 1352 Einträgen |
| B-612 Model-Manager-Freeze | **live-verifiziert** | 52515ms → 54ms im echten Lauf |
| B-613 Export-Lücke | **live-verifiziert** (Symptom) | GUI-Render, WARNING statt Crash, ffmpeg lief bis 40% |
| M3 DbPersistStage / Motion-Paritaet | **live-verifiziert** (2 Clips) | Energy-Diff 0.0000, Szenen/VectorDB exakt |
| M2 T1.2–T1.6 (Studio-Brain) | **code-complete-live-pending** | nur Unit-Tests; Setting default AUS → im echten App-Flow NICHT ausgeführt |
| M3 Video-Engine (übrige) | **code-complete-live-pending** | Setting default AUS |
| B-359 Chunked-Onset | code-complete | Unit-Tests; nicht live auf 92-min-Mix gemessen |
| UI-Async (Settings/Cleanup) | Unit-getestet | nicht live geklickt |

## Befunde nach Schweregrad

### 🔴 KRITISCH
Keine im **heute geänderten Code** gefunden. Die 3 gemeldeten Crashes sind
gefixt und live verifiziert.

### 🟠 HOCH — GELÖST (2026-07-09, live verifiziert)
- **Timeline-Hang 62s** war bei sehr grossen Timelines (92-min-Mix, 1352
  Clips). **BEHOBEN** in zwei Schritten (Commits 83bfa3f + 7868107):
  (1) Batch-Groesse 25→2000 (weniger Inter-Batch-Paints, wall −56%);
  (2) Text-Items (Label/Status pro Clip) LAZY erst bei Sichtbarkeit
  (`_ensure_content`) — der echte CPU-Treiber waren ~4000 QGraphicsTextItem
  (Windows-Font-Layout). **Live-GPU-verifiziert:** batched-build cpu
  29266ms→**1623ms** (~18-20×), SCHNITT-Wechsel 62000ms→**302ms**,
  Projekt-Open ~17s aber durchgehend responsiv (kein "Keine Rueckmeldung").
  Cutliste/Labels korrekt, Labels bleiben beim Scrollen (Lazy ohne
  Regression). 89 Timeline + 582 UI-Tests gruen.
  Rest: Projekt-Open ~17s (DB/Audio-Load, responsiv) — akzeptabel, kein Freeze.

### 🟡 MITTEL
- **B-613 Cut-Dedup ändert Auto-Edit-Ausgabe.** `services/pacing_service.py`
  führt nach Drop-Burst/Onset-Snap Cuts < 0.2s zusammen. Das ist die
  korrekte Ursachen-Behebung, ABER: es verändert die Schnitt-Ausgabe in
  dichten Sektionen (dort können 1–N Cuts entfallen). Verifiziert NUR gegen
  die Golden-Fixture (unverändert) — **NICHT** gegen einen frischen
  Auto-Edit auf echtem Material. Effekt auf reale DJ-Mixe unbelegt.
- **M2 (T1.2–T1.6) + M3-Engine sind Setting-gated, default AUS** → im
  normalen App-Betrieb NICHT aktiv. Ihre reale Korrektheit (Brain-V3-Reranker,
  Steer-Overrides, Lernschleife, RL-v2, Engine-Persistenz) ist nur durch
  Unit-Tests belegt, NICHT durch einen echten App-Durchlauf mit aktiviertem
  Setting. „Funktioniert" ist hier NICHT bewiesen.
- **B-359 Chunked-Analyse: globale Rhythmus-Metriken approximiert.**
  `_analyze_long_chunked` übernimmt Syncopation/Groove/Swing vom
  onset-reichsten Chunk (Heuristik), nicht als echten globalen Aggregat.
  Für lange Mixe mit wechselnden Sektionen leicht ungenau. Onset-Listen
  selbst sind vollständig+korrekt gemergt.

### 🟢 NIEDRIG
- **B-611 Rest-Edge-Cases** (theoretisch, unbeobachtet) — **BEWUSST AKZEPTIERT,
  nicht geändert:** (a) `source_start` separat gerundet ohne Co-Clamp;
  (b) Export-Clamp kann 0 ergeben. Beide sind durch B-613-Min-0.2s-Dedup +
  Intelligent-Looping-Reset in der Praxis ausgeschlossen. Eine spekulative
  Härtung (skip/return 0.0) würde ein 0-Längen-Segment an ffmpeg reichen
  (Concat-Caller-Verhalten unklar) → NEUES Risiko für unbeobachteten Fall.
  Ingenieur-Entscheidung: funktionierenden Export-Code nicht spekulativ
  ändern (Honesty/Don't-break-working-things).
- **Timeline-[PERF]-Instrumentierung** — **GEFIXT** (Commit fd3c213): jetzt
  hinter Env-Flag `PB_TIMELINE_PERF=1` (default AUS), kein Rauschen im
  Normalbetrieb.

### ⚪ UNBEKANNT / offen
- **Projekt-Datenverlust** (`outputs/6262626`, `outputs/final-check`) während
  der Session — Ursache NICHT bestimmbar. NICHT durch heutigen Code oder
  meine Befehle belegt (keine App-Lösch-Op im Log, kein rm auf outputs/).
  Echtes Datenverlust-Risiko, ungeklärt. `outputs/` ist gitignored (keine
  Git-Recovery). Muss der User klären.
- **Off-by-one** im Timeline-Log: `clips=1353` (Timeline) vs `1352 Cuts`
  (Cutliste) — im Log sichtbar, nicht untersucht (ausserhalb heutigem Scope,
  evtl. Audio-Track mitgezählt).

## Verdrahtungs-Analyse (Phase 5)

- **B-613-Dedup → Segment-Loop:** verifiziert, dass `cut_beats` nach dem
  Dedup (Z.824) NICHT mehr mutiert wird (nur `len()`-Read Z.1063) → Dedup
  hält bis zum Loop. ✓
- **T1.4 Feedback → RL-v2/WeightStore:** beide Propagationen in getrennten
  try/except, best-effort, nie geraised → können Feedback-Commit/UI nicht
  crashen. Kein Doppel-Write (RL-v2 ohne db_session_factory). ✓
- **B-612 Delete-Worker:** Re-Entrancy-Guard + closeEvent-Cleanup +
  QueuedConnection vorhanden. ✓
- **DbPersistStage → Monolith-Writer:** nutzt store_scenes_in_db/
  store_embeddings (inkl. Projekt-Token/FK-Guards) → keine neue DB-Logik. ✓

## Selbst-Kritik / Limitierungen (PFLICHT)

**Was NICHT geprüft/verifiziert werden konnte:**
1. Die Setting-gated Features (M2 Studio-Brain, M3 Engine) im **echten
   App-Betrieb mit aktiviertem Setting** — Defaults sind AUS, ich habe sie
   nicht live durchlaufen. Ihre Praxis-Korrektheit ist unbewiesen.
2. ~~B-613-Cut-Dedup real~~ — **NACHTRAEGLICH VERIFIZIERT** (frischer
   Auto-Edit Projekt 21): Dedup merged 55/1365 Cuts (~4%), ausschliesslich
   Paare <0.2s (imperceptibel schnell); Drop-Burst-Kadenz bleibt. User-
   Entscheidung: beide Fixes behalten.
3. Ein **vollständiger 92-min-Export bis 100%** (nur bis 40% live gesehen).
4. Interna von `rl_memory_v2.py` (SectionPolicy/VarietyMemory-Korrektheit)
   nur oberflächlich.
5. Der Paritäts-Nachweis basiert auf **2 Clips** (1 langsam, 1 bewegt) —
   nicht auf allen 57 Clips des Projekts.

**Getroffene Annahmen:**
- Golden-Fixture ist repräsentativ für normale Auto-Edit-Ausgabe.
- Die 2 Paritäts-Clips sind repräsentativ.
- Unit-Test-Grün ≈ Logik-korrekt (aber: Smoke ≠ Live-verifiziert).

**Methode:** Kritische Diff-/Code-Review + gezielte Daten-Verifikation +
Wiederverwendung der Live-GUI-Test-Ergebnisse. KEIN vollständiger dynamischer
E2E-Durchlauf jeder einzelnen Funktion.

## Status nach Nachbearbeitung (Normalmodus, 2026-07-09)

1. 🟠→✅ **Timeline-62s-Hang GELÖST** + live verifiziert (cpu 29s→1.6s,
   Wechsel 62s→302ms). Commits 83bfa3f + 7868107.
2. 🟡→✅ **B-613-Dedup real gemessen** (55/1365 Cuts, nur <0.2s-Flicker) —
   User behaelt beide Fixes.
3. 🟡 **M2/M3-Features default AUS** → reale Korrektheit weiterhin nur
   Unit-belegt (nicht live mit aktivem Setting). Bewusst experimentell/OFF
   bis User-Abnahme. (Offen, aber by-design kein Normalbetrieb-Risiko.)
4. ⚪ **Projekt-Datenverlust** (6262626/final-check): forensisch als
   gezielt/extern eingegrenzt, NICHT durch heutigen Code/App. Ursache
   (User vs. anderer Chat) offen.
5. 🟢→✅ **[PERF]-Instrumentierung** hinter Env-Flag (fd3c213); B-611-Edge-
   Cases bewusst akzeptiert (guarded, spekulative Aenderung waere neues Risiko).

**Fazit:** Alle findbaren REALEN Bugs (3 Crashes + Timeline-Hang) gefixt +
live verifiziert. Rest = experimentelle Setting-gated-Features (OFF),
dokumentierte Limitierungen, oder externer Datenverlust — keine offenen
Crashes/Fehlfunktionen im Normalbetrieb.
