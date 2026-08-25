# STAB-3 LLM-Pfade — 2026-08-25

status: agent-complete-await-user-marker

## Auftrag

`STAB-3 / Tool- und Non-Tool-LLM-Pfade muessen Recall/Stats/Explain/Learn erhalten`.

## Modell und Runtime

- Ollama 0.21.2, gepinnt.
- `qwen2.5:3b`, Runtime-Digest
  `357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b`.
- GTX 1060 / CUDA0; qwen-Runner vollstaendig auf CUDA0.
- Isolierte Stability-Settings waehlen `qwen2.5:3b`; Host-Settings unangetastet.

## Produktfixes

- B-896, Commit `90e1472`: Settings-Modell wird bis in Orchestrator,
  Toolloop, Classifier und Non-Tool-Fallback gebunden.
- B-897, Commit `50ce61d`: `brain_learn_note` normalisiert fehlenden Titel
  und entfernt optionale JSON-null-Werte vor Registry-Ausfuehrung; native und
  Non-Tool-Gatewaypfade teilen denselben Normalizer.
- Fokus nach Fix: 7 bestanden, 29 abgewaehlt; PyCompile, Ruff und Diffcheck
  gruen.

## Current-Live: ChatDock

| Aktion | Ergebnis |
|---|---|
| Learn | qwen nativer Toolcall; Note #2 mit exaktem Marker persistiert |
| Recall | 1 Treffer, Note #2, score 1.0, exakter Chorus→Clip-32-Inhalt |
| Stats | 11 Runs, 1092 Decisions, 2 Feedback-Events, 2 Patterns, 2 Notes, 16/18 Achsen mit Signal |
| Explain | Decision 821, Run 9/Sequenz 31, Score 0.7119 und 17 Scorebeitraege |

Projekt-DB `PRAGMA quick_check=ok`. App PID 8660 blieb responsiv.

## Non-Tool-Grenze

- B-738 steht durch Usermarker `fixed`.
- Echter headless Non-Tool-Learn→Recall-/Promptbeleg vom 2026-08-11 liegt in
  B-738 vor.
- Aktueller Fokus umfasst den realen Orchestrator-Non-Tool-Fallback und ist
  gruen.
- Aktueller Gemma-ChatDock-Learn war rot: Modell forderte keine
  Gateway-Aktion an.
- User erlaubte danach: besseres LLM verwenden oder ueberspringen. qwen wurde
  als besseres Toolmodell verwendet; erneuter Non-Tool-ChatDock-Lauf wurde
  uebersprungen. Das ist **kein aktueller Non-Tool-Live-PASS**.

## DoD

- [x] Konfiguriertes Modell erreicht echten Orchestratorpfad.
- [x] Current ChatDock Learn/Recall/Stats/Explain.
- [x] Learn persistent und per Recall wieder auffindbar.
- [x] Aktueller fokussierter Tool-/Non-Tool-Regressionssatz.
- [ ] Erneuter Current-ChatDock-Beleg mit Non-Tool-Modell — userautorisiert
  uebersprungen.
- [ ] User-`fixed`-/STAB-3-Phasenmarker.

## Naechste Task

`STAB-4 / B-723 echten GPU-/Cancel-/Projektwechsel-Pfad live verifizieren`.
