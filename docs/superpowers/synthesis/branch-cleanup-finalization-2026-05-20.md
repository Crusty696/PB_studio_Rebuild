# Branch Cleanup Finalization 2026-05-20

Status: `code-complete-live-pending`

## Vault Frontmatter Cleanup

Repariert im Vault:
- `B-315-schnitt-switch-blocks-main-thread-with-real-project.md`
- `B-316-schnitt-audio-subtab-missing-metadata-waveform.md`
- `B-317-schnitt-default-audio-selects-unanalyzed-track.md`
- `B-318-schnitt-timeline-renders-media-duration-instead-entry-duration.md`
- `B-319-schnitt-timeline-data-overlap-audio-duplicates-source-mismatch.md`
- `B-320-schnitt-timeline-video-clips-missing-thumbnails.md`
- `B-322-schnitt-checkbox-marked-video-files-not-used-by-timeline-add.md`

Art der Aenderung:
- `type: bug` ergaenzt.
- `updated: 2026-05-20` gesetzt.
- Bei B-315 fehlendes `id: B-315` ergaenzt.

Nicht geaendert:
- Bug-Status.
- Fachlicher Inhalt.
- Live-/Fixed-Markierungen.

## B-282 Old Branch Closeout

Alter Branch:
- `codex/bug-task-list-2026-05-07`
- HEAD: `0a370ec fix(B-282): select real auto-edit media`

Alte Commit-Pfade:
- `services/task_manager.py`
- `tests/test_services/test_b222_signal_queued_connections.py`
- `tests/ui/test_director_combo_readiness.py`
- `ui/controllers/media_table.py`
- `ui/controllers/workspace_setup.py`

Aktueller Stand:
- `ui/controllers/media_table.py` waehlt echte Director-Combo-Medien und bevorzugt analysierte Audios.
- `ui/controllers/workspace_setup.py` gated Generate/Auto-Edit via `currentData() is not None`.
- `services/task_manager.py` nutzt explizite `Qt.ConnectionType.QueuedConnection` fuer progress/finished/error callbacks.
- `tests/test_services/test_b222_signal_queued_connections.py` enthaelt Regression fuer TaskManager callbacks.
- `tests/ui/test_schnitt_audio_video_combo.py::test_b314_director_combos_select_first_real_project_media` deckt echte Combo-Auswahl ab.

Entscheidung:
- Der alte Branch wird durch aktuellen Code + Commit `b0013cd` inhaltlich ersetzt.
- Kein Merge und kein Cherry-Pick, weil der Branch einen echten Konflikt in `ui/controllers/media_table.py` hatte.
- Worktree und Branch duerfen entfernt werden.

## Auto-Merge Policy

Decision:
- `D-047-block-auto-merge-workflows.md`

Regel:
- `origin/main` und `origin/workflow/auto-merge-cleanup` werden nicht gemerged, solange der neue Inhalt Auto-Merge-/Branch-Cleanup-Automation ist.
- Eine spaetere Uebernahme braucht explizite Governance-Freigabe.

Mindestbedingungen fuer eine spaetere sichere Variante:
- Kein automatischer Merge ohne explizites Label wie `automerge-approved`.
- Kein Merge fuer Draft-PRs.
- Kein Merge ohne gruene Pflichtchecks.
- Kein Branch-Loeschen ohne explizite Schutzliste.
- Keine Wirkung auf `main`/`master`/`develop`/`backup/*`/`sandbox/*`.

## Verification

Bereits ausgefuehrt vor diesem Finalisierungsschritt:
- B-282 targeted pytest: `13 passed in 4.60s`.
- Governance + B-282 targeted pytest: `16 passed in 8.19s`.
- GUI live smoke navigation: App sichtbar gestartet, Projekt/Material/Schnitt/Export/Brain geklickt, graceful Shutdown.

Noch offen:
- Voller Audio-/Video-Import.
- Timeline-Aufbau mit echten Medien.
- Auto-Edit-End-to-End.

Darum bleibt Status nicht `fixed`.
