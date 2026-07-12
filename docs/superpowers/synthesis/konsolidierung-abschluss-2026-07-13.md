# Synthese: Konsolidierungs-Plan K1-K9 — code-complete (2026-07-13)

plan_id: PB-STUDIO-KONSOLIDIERUNG-2026-07-12 (D-068)
ausfuehrung: 5 parallele Worktree-Agenten (User-Auftrag: autonom + maximal
parallel), sequentielle Merges nach main durch Hauptagent, je Task
Paritaets-Verify. Main-Endstand: 277d2b9, Worktree clean, Agent-Branches
gemergt + geloescht.

## Ergebnis pro Task

| Task | Commit(s) | Ergebnis | Verify |
|---|---|---|---|
| K9 | 618a5ca | toter VectorDB-Konstanten-Patch raus, F-030-Reset bleibt | 27/27 Tests + Live-Skript (close()+Reset+APP_ROOT-Getter) |
| K4 | c23677a (merge 277d2b9) | subprocess_kwargs() in ffmpeg_utils, 13 Dateien / ~30 Inline-Stellen umgestellt | ruff, ffprobe rc=0 ohne Konsolenfenster |
| K7 | 6dee49f (merge 277d2b9) | probe_duration + parse_frame_rate Helper, 8 Dateien, Fallbacks exakt erhalten (60.0/30.0/0.0-Divergenzen dokumentiert bewahrt); video_service-fps + proxy_generator-JSON-Probe bewusst NICHT umgestellt (nicht abbildbare Semantik) | 14 Tests + Funktionstest (Sine-WAV=2.0s, Fallback-Pfade, strict-Raise) |
| K5 | fa1431e (merge 49d8b96) | Enqueue-Factory audio_actions, -75 Zeilen; video_actions NICHT refactored — Finding-Praemisse dort falsch (kein identisches Muster) | Registry-Dump SHA256-identisch vorher/nachher + Runtime-Paritaet |
| K2 | aa41aeb (merge 4bd198d) | 7 Stellen auf audio_constants.STEM_NAMES; 4 ausgelassen (abweichende load-bearing Reihenfolge: pacing_beat_grid 477/927, pacing_service 685 dominant_stem-Tie-Break, stages 186 Fallback-Reihenfolge) | 51 stem- + 249 pacing-Tests gruen |
| K3 | 3d86dc1 | 6 Stellen auf SIGLIP_DEFAULT_MODEL/EMBEDDING_DIM | GPU-Smoke cuda:0 GTX 1060, shape (1,1152), HF_HUB_OFFLINE |
| K6a | 7023d51 | make_nullpool_engine-Fabrik in database/session.py; auto-edit-Engine FK=0 (wie vorher), jetzt mit WAL+busy_timeout 120s | PRAGMA-Beweis: fabrik(False)=0, fabrik(True)=1, nullpool=1, auto-edit=0; 268 Tests |
| K1 | 9177d2f (merge 8c80d7d) | 7 Undo-Write-Stellen durch _run_timeline_write (B-512-Retry ueberall) | Zyklus-Skript DB+UI-Callbacks byte-identisch; 20/20 auf main |
| K8 | 91b71a9/3dae929/5a9f7a8 (merge 3395029) | 4 QThread-Stellen auf run_worker (settings_dialog 2x, export-Controller, workspace_setup); 11 begruendet ausgelassen (Contract-Tests, Cancel-Protokolle, B-605-Design, Multi-Arg-Signale) | 22+14+67 Agent-Tests, 22/22 main-Nachlauf |

## Offen (User)

1. K6 TEIL B: foreign_keys=ON im Auto-Edit-Pfad — Verhaltensaenderung,
   braucht expliziten User-Entscheid (STOP+ASK dokumentiert).
2. Live-Sichtung K8-Flows (4 dokumentierte manuelle Flows: Settings-Test +
   Dialog-Close waehrend Lauf, async Validate-Save, Export-Produktions-Info
   + Doppelklick, Schnitt-Gates-Refresh bei Workspace-Wechsel).
3. `fixed`-Marker auf dem Plan setzt nur der User.

## Bekannte Nicht-K1-K9-Befunde aus der Ausfuehrung (pre-existing, unveraendert)

- pytest-Teardown PermissionError auf kaputtem Junction
  `%TEMP%\pytest-of-David_Lochmann\pytest-current` (jeder Lauf Exit 1 trotz
  gruener Tests).
- Test-Order-Pollution: 16 chat_actions-Fails nur im Gesamtlauf, standalone
  gruen (auf Baseline reproduziert).
- `test_interactive_timeline_applies_brain_v3_state_metadata` failt auf main
  (IndexError clip_items[0], auf 4bd198d ohne Aenderungen reproduziert).
- `test_clip_lock_click` Ordering-Fail im Verbund (standalone gruen).
