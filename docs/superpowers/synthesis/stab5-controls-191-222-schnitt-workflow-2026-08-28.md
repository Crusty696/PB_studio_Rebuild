# STAB-5 Controls #191-#222 — Schnitt & Workflow Controls (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

- **#191** `SchnittEditorView.audio_combo`: QComboBox für Audio-Track-Auswahl (BPM-Pacing Audio-Quelle).
- **#192** `SchnittEditorView.video_combo`: QComboBox für Video-Clip-Auswahl.
- **#193** `SchnittEditorView.btn_generate`: QPushButton ("Timeline generieren") löst Vorschau-Cut-Linien Zeichnen aus.
- **#194** `SchnittEditorView.btn_auto_edit`: QPushButton ("Auto-Edit") startet automatischen Beat-Schnitt.
- **#195** `SchnittEmptyView` Preset-Buttons: PushButtons ("Techno", "Cinematic", "House", "Festival") emittieren `preset_selected(key)`.
- **#196** `SchnittEmptyView.btn_custom`: QPushButton ("Eigene Einstellungen…") emittiert `custom_clicked`.
- **#197** `SchnittLoadingView.btn_cancel`: QPushButton ("Abbrechen") emittiert `cancel_requested`.
- **#198** `SchnittTabPacingAnker.cut_rate_combo`: QComboBox für Schnittdichte ("1 Beat" bis "16 Beat").
- **#199** `SchnittTabPacingAnker.style_combo`: QComboBox für Stilprofil ("Standard", "Techno", etc.).
- **#200** `SchnittTabPacingAnker.breakdown_combo`: QComboBox für Breakdown-Verhalten ("halve", "force16", "none").
- **#201** `SchnittTabPacingAnker.transition_combo`: QComboBox für Übergangsmodus (automatische Crossfades / harte Beat-Cuts).
- **#202** `SchnittTabPacingAnker.chk_studio_brain`: QCheckBox für Studio-Brain Pipeline-Nutzung.
- **#203** `SchnittTabPacingAnker.chk_llm_strategist`: QCheckBox für LLM-Strategist Pacing-Planung.
- **#204** `SchnittTabPacingAnker.chk_llm_pacing`: QCheckBox für direkte LLM-EDL-Pacing Vorschläge.
- **#205** `SchnittTabPacingAnker.btn_ab_compare`: QPushButton ("A/B-Gewichte testen") öffnet `ABCompareDialog`.
- **#206** `SchnittTabPacingAnker.btn_regenerate`: QPushButton ("Mit neuen Pacing-Einstellungen generieren") löst Neu-Zeichnung der Cut-Linien aus.
- **#207** `SchnittTabPacingAnker.btn_add_anchor`: QPushButton ("+ Anker") fügt einen Sync-Anker hinzu.
- **#208** `SchnittTabPacingAnker.btn_remove_anchor`: QPushButton ("− Anker") entfernt den gewählten Sync-Anker.
- **#209** `SchnittTabPacingAnker.btn_sync_anchors`: QPushButton ("Sync") synchronisiert Anker mit Timeline und Medien.
- **#210** `SchnittTabPacingAnker.btn_learn_ai`: QPushButton ("Als KI-Lernregel speichern") speichert Anker als Lernsignal.
- **#211** `SchnittTabRlNotes.btn_thumbs_up`: QPushButton ("👍 Gut") emittiert `feedback_positive`.
- **#212** `SchnittTabRlNotes.btn_thumbs_down`: QPushButton ("👎 Schlecht") emittiert `feedback_negative`.
- **#213** `SchnittTabSchnitt.btn_play`: QPushButton ("▶") schaltet Vorschau-Wiedergabe (`video_preview.toggle_play`).
- **#214** `SchnittTabSchnitt.btn_stop`: QPushButton ("■") stoppt Vorschau-Wiedergabe (`video_preview.stop`).
- **#215** `TimelineShell.btn_snapshots`: QToolButton ("Snapshots") öffnet Snapshot-Wiederherstellungsmenü.
- **#216** `TimelineShell.btn_zoom_out`: QPushButton ("-") vermindert Timeline-Zoom (`_zoom_by(1/1.15)`).
- **#217** `TimelineShell.btn_zoom_fit`: QPushButton ("Fit") passt Timeline horizontal an (`_fit_to_content()`).
- **#218** `TimelineShell.btn_zoom_reset`: QPushButton ("1:1") setzt Zoom auf 100% zurück (`_reset_zoom()`).
- **#219** `TimelineShell.btn_zoom_in`: QPushButton ("+") erhöht Timeline-Zoom (`_zoom_by(1.15)`).
- **#220** `ProjectDashboard.btn_new_project`: QPushButton ("+ Neues Projekt") im Cockpit.
- **#221** `ProjectDashboard.btn_open_project`: QPushButton ("Projekt oeffnen") im Cockpit.
- **#222** `ProjectDashboard.btn_next_step`: QPushButton ("Projekt starten") emittiert `action_requested`.

## Verifikation

`tests/ui/test_stab5_schnitt_workflow_controls.py` (neu, 32 Offscreen-PySide6 QtTests) -> `32 passed in 2.43s`. Kein Produktcodeedit.

## Grenzen

Echte FFmpeg-Exporte, Ollama-LLM Network Calls, PyTorch-Analysen und reale GUI-Klicks bleiben Live-Endgate.
