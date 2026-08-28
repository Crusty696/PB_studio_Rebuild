# STAB-5 Controls #126-#140 — Widget-Reihe (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#126** MediaPoolGrid Sort-Combo (Video): Items exakt
  `Name/Aufloesung/FPS ▼`; Auswahlwechsel erreicht `_apply_filter`
  (bound connect, Klassen-Patch).
- **#127** WorkspaceNavBar: `SCHNITT`-Click emittiert `workspace_changed(2)`
  und setzt exklusiven Checked-Zustand.
- **#128** OnboardingBanner `Verstanden`: versteckt Banner, emittiert
  `dismissed`, persistiert Flag in isolierten QSettings.
- **#129** PacingExplorer Run-Combo: Wechsel laedt Decisions exakt fuer den
  gewaehlten Run (`run_id=8`-Query belegt).
- **#130** `Aktualisieren`: laedt Run-Liste genau einmal neu.
- **#131/#132** `👍 Gut`/`👎 Schlecht`: schreiben `user_verdict good/bad`
  fuer aktuelle Decision inkl. Commit; ohne Auswahl kein Write.
- **#133** StemMixer `M`: toggelt Mute, emittiert `("drums", True)`,
  `is_muted`-API korrekt.
- **#134** StemMixer `S`: checkbar, `solo_btn`-Consumer-API zeigt exakt
  diesen Button, toggled-Signal belegt.
- **#135** Transport `■`: emittiert `stop_requested`.
- **#136** Transport `▶`: play_requested; im Playing-Zustand (Text `⏸`)
  pause_requested.
- **#137** StemWorkspace `Reset All`: leert Solo-Set, entmutet, Volume
  zurueck auf 100.
- **#138** TaskDock `Fertige loeschen`: entfernt beendete Rows, ruft
  `clear_finished`, zeigt Leerzustand.
- **#139** TaskDock `Abbrechen`: cancelt laengsten laufenden Task
  (`lang` vor `kurz`), Signal `cancel_requested` korrekt.
- **#140** Zeilen-`✕`: cancelt exakt den Task der Zeile (B-127-Vertrag).

## Verifikation

`tests/ui/test_stab5_widget_row_controls.py` (neu, 14 Tests) ->
`14 passed in 1.19s`. Fakes fuer DB-Session (SQL-Recorder) und
GlobalTaskManager; isolierte QSettings. Kein Produktcodeedit.

## Grenzen

Echte DB-Verdicts, echte Task-Engine-Laeufe und Stem-Audio bleiben
Live-Endgate.
