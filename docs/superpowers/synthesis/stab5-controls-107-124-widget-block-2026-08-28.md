# STAB-5 Controls #107-#124 — Widget-Block (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#107** `AnalysisStatusPanel.filter_combo`: Index-Wechsel setzt `_filter_mode` (0: all, 1: pending, 2: error) und lädt Ansicht neu.
- **#108** `AnalysisStatusPanel.btn_refresh`: Klick ruft `refresh()` auf und aktualisiert Status.
- **#109** `AnalysisStatusPanel.btn_retry_errors`: Button im Error-Zustand aktiv; Klick ruft `_on_retry_all_errors()` auf.
- **#110** `AnalysisStatusPanel` Zeilen-Button ("Starten"/"Wiederholen"): Klick emittiert `analysis_requested` für den jeweiligen Schritt (z. B. `metadata_extract`).
- **#111/#112** `AnalysisStatusPanel` Shortcuts: `F5` und `Ctrl+R` lösen `refresh()` aus.
- **#113** `BrainV3FeedbackPopup` Rating-Buttons: Klick löst `_submit(rating)` für den gewählten Rating-Key aus.
- **#114** `BrainV3FeedbackPopup` `Abbrechen`-Button: Klick emittiert `rejected` und schließt den Dialog.
- **#115** `BrainV3FeedbackPopup` Hotkeys (`1`-`4`): Auslösen triggert `_submit(rating)` entsprechend der Tasten 1–4.
- **#116** `BrainV3LearningSessionDialog._btn_preview_play`: Klick triggert `_toggle_preview()`.
- **#117** `BrainV3LearningSessionDialog._btn_preview_stop`: Klick triggert `_stop_preview()`.
- **#118** `BrainV3LearningSessionDialog._btn_open`: Klick triggert `_on_open_clicked()` (öffnet Feedback-Popup).
- **#119** `BrainV3LearningSessionDialog._btn_close`: Klick triggert `_on_close_clicked()`.
- **#120** `BrainV3StatsPanel._btn_refresh`: Klick ruft `refresh()` auf.
- **#121** `BrainV3StatsPanel._btn_learning`: Klick ruft `_on_learning_clicked()` auf.
- **#122** `BrainV3StatsPanel._btn_reset`: Klick ruft `_on_reset_clicked()` auf.
- **#123** `show_cross_project_reuse_toast` Checkbox ("Nicht mehr fragen"): Klick speichert `mute_key=True` in QSettings.
- **#124** `CutListPanel.btn_refresh`: Klick ruft `refresh()` auf.

## Verifikation

`tests/ui/test_stab5_widget_block_controls.py` (neu, 12 Tests) -> `12 passed in 2.40s`. Kein Produktcodeedit.

## Grenzen

Echte DB-Writes, Async-Workers und Audio-/Video-Wiedergabe bleiben Live-Endgate.
