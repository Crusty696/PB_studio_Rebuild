# Timeline-Virtualisierung (D-066) — M4-Harness-Abnahme BESTANDEN

datum: 2026-07-10 (nacht)
plan: PB-STUDIO-TIMELINE-VIRTUALISIERUNG-2026-07-10
status: harness-pass — User-Sichtung + `fixed` offen (setzt nur der User)
head: 67af4f9 (+ dieser Synthese-Commit)

## Abnahme-Ergebnis (Lauf 7, echte App, test33: 1428 Cuts / 375 Videos)

- `scripts/diag/verify_workspace_switch_perf.py --cycles 3` → **status=pass, EXIT=0**
- worst_click_s = **0.89** (alle 12 Klicks 0.38–0.89 s; Kriterium ≤ 2.0)
- Watchdog-Dumps im Messfenster = **0**, max_block = **0.0 s** (Kriterium ≤ 2.0)
- `setCurrentIndex`-Show: max **72 ms** (vor dem Plan: 20–34 s)
- Testsuite: **654 passed / 0 failed** (inkl. neuer Virtualisierungs-Guards)
- 7 pb-gui-tester-Laeufe insgesamt, **0 Crashes**, saubere Shutdowns
- JSON: `tests/qa_artifacts/workspace_switch_perf.json`, Screenshots `m4verify7_*`

## Was den Freeze wirklich ausmachte (profil-bewiesene Fix-Kette)

| Commit | Befund (Watchdog-/PERF-Beweis) | Fix |
|---|---|---|
| 1f36a08/2aea13e/da29a88/d67ab97 | 1428 Clip-Items + 12k+ Marker-Items voll materialisiert | M1–M3: Records + Viewport-Fenster, Single-Items mit Culling, Show-Entkopplung, Grid-Virtualisierung |
| 2763832 | refresh_audio lud pro Workspace-Klick Scene + 165k Waveform-Floats neu; CutList get_cut_list synchron im Klick | No-op-Guard (audio unveraendert), CutList-Refresh nach Paint |
| 477ed9f | ORM-Kaskaden: `query(TimelineEntry).all()` zog via lazy='selectin' ALLE ClipAnchors, VideoClips alle Scenes, AudioTracks die Waveform-Blobs → DB minutenlang busy, Main-Queries im busy_timeout | Export-/Convert-Pfad auf Spalten-Queries; Doppel-Scan pro EXPORT-Klick entfernt |
| 1788a42 | 150er-Materialisierungs-Block = 17.3 s unter Last (115 ms/Item) | Zeitbudget 40 ms/Tick (Lauf 7: saubere 40-ms-Ticks) |
| 7a65fef (B-614) | Stem-Peaks: 8000 seek+read-Zyklen pro Stem × 4 parallel = HDD-Seek-Sturm + GIL-Druck → Cold-Start-Freezes | sequentielles Block-Lesen (1 Seek), numpy-vektorisiert, serielle Job-Queue |
| dca67e9/67af4f9 | Harness-Messfehler: 2-s-Poll-Quantisierung; UIA-Polling = Observer-Last im Ziel-Main-Thread | Poll 0.25 s via SendMessageTimeout(WM_NULL) |

Messverlauf worst_click: 28.9 → 32.6 → 42.3 → 22.75 → 2.52 → (6: Messstoerung) → **0.89 s**.

## Ehrliche Grenzen

1. **Pass gilt fuer den eingeschwungenen Zustand:** Nach Projekt-Open laeuft
   ~2 Min Hintergrundarbeit (Storage-Migration, get_all_audio, Stem-Peaks
   seriell). Waehrend dieser Phase koennen Wechsel noch traege sein
   (Lauf 6 mit nur 60 s Ruhe: worst 7.66 s).
2. **Projekt-LOAD selbst** hat weiterhin Watchdog-Dumps bis 6.7 s
   (u.a. `media_workspace._build_video_page`, `nativeEventFilter`;
   17.7-s-SLOW-EVENT beim Recent-Menue-Klick). Ausserhalb der
   Plan-Abnahme — Kandidat fuer einen Folge-Task.
3. Harness-Klicks ersetzen keine User-Sichtung: Drag&Drop, Rubberband,
   Lock/Undo, Zoom wurden durch die Testsuite (Guards) abgedeckt, aber
   nicht manuell im Live-Lauf geprueft.

## Offen (User)

- Live-Sichtung: test33 oeffnen, Workspace-Wechsel, Timeline scrollen/
  zoomen/draggen, Grid scrollen, Cutliste klicken.
- `fixed`-Marker auf Plan + B-614 (setzt nur der User).
