# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25
next_allowed_task: none (all B-348..B-430 code-complete)
updated: 2026-05-27

## Meaning

Der User hat am 2026-05-25 bestaetigt, dass der Fixplan nach der Bereichspruefung frei gegeben ist.

Aktiver Plan:

```text
PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25
```

Der Audit-Plan `PB-STUDIO-AREA-AUDIT-2026-05-24` ist abgeschlossen und bleibt als Quelle erhalten.

## Agent Behavior

- Nur `PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25` ausfuehren.
- Fixes sind nur fuer dokumentierte Bugs B-348 bis B-430 autorisiert.
- Reihenfolge: B-348 zuerst, dann High, Medium, Low in Bug-ID-Reihenfolge.
- Audio-V2-Portierung bleibt ausserhalb dieses Plans.
- Bestehende Dirty-Worktree-Aenderungen bleiben erhalten und werden nicht revertet.
- `verified` / `fixed` nur nach realem App-Workflow plus Log-/UI-Beleg.

## Current Status

- Audit-Plan abgeschlossen; Fixplan aktiv.
- Belegter neuer Bug: `B-348` blockiert globales `pytest --collect-only`.
- Area 2 ist audit-complete-live-open.
- Area 3 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 3: `B-349`, `B-350`, `B-351`, `B-352`.
- Area 4 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 4: `B-353`, `B-354`, `B-355`, `B-356`, `B-357`, `B-358`, `B-359`.
- Area 5 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 5: `B-360`, `B-361`, `B-362`, `B-363`, `B-364`, `B-365`, `B-366`, `B-367`, `B-368`, `B-369`.
- Area 6 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 6: `B-370`, `B-371`, `B-372`, `B-373`, `B-374`, `B-375`, `B-376`, `B-377`, `B-378`.
- Area 7 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 7: `B-379`, `B-380`, `B-381`, `B-382`, `B-383`, `B-384`, `B-385`, `B-386`, `B-387`, `B-388`, `B-389`, `B-390`, `B-391`.
- Area 8 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 8: `B-392`, `B-393`, `B-394`, `B-395`, `B-396`, `B-397`, `B-398`, `B-399`, `B-400`, `B-401`, `B-402`, `B-403`, `B-404`, `B-405`, `B-406`, `B-407`, `B-408`.
- Area 9 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 9: `B-409`, `B-410`, `B-411`, `B-412`, `B-413`, `B-414`, `B-415`, `B-416`, `B-417`.
- Area 10 ist audit-complete-live-open.
- Belegte neue Bugs aus Area 10: `B-418`, `B-419`, `B-420`, `B-421`, `B-422`, `B-423`, `B-424`, `B-425`, `B-426`, `B-427`, `B-428`, `B-429`, `B-430`.
- Final-Synthesis erstellt.
- B-348 ist fixed im Vault am 2026-05-25: collect Exit 0, Standalone-Runner Exit 0, nahe DB-Tests Exit 0.
- B-349 ist fixed im Vault am 2026-05-25: Service-Workflow mit eigenem laufendem Task Exit 0, Projektmanager-nahe Tests Exit 0.
- B-350 ist fixed im Vault am 2026-05-25: VectorDB-Fehlerpfad rollback+raise, Erfolgspfad commit nach VectorDB-Delete.
- B-351 ist code-fix-pending-live-verification im Vault am 2026-05-25; statisch gruen, live pywinauto-Smoke offen. Wurde vor restlichen High-Bugs begonnen; Reihenfolge jetzt korrigiert.
- B-353 ist fixed im Vault am 2026-05-25: Qt-Offscreen error-ohne-finished QThread-Lifecycle Exit 0.
- B-354 ist fixed im Vault am 2026-05-25: MediaWorkspace stem dispatch Constructor-Mismatch Exit 0.
- B-357 ist fixed im Vault am 2026-05-25: BaseAnalysisWorker-Cancel nach `_analyze()` persistiert nicht, Audio-nahe Tests Exit 0, collect Exit 0.
- B-362 ist fixed im Vault am 2026-05-25: ProxyCreationWorker-Cancel emittiert Terminal-Signal; Controller ueberschreibt cancelled nicht auf error.
- B-363 ist fixed im Vault am 2026-05-25: Video-Pipeline-Cancel wird nicht mehr als done checkpointed.
- B-364 ist fixed im Vault am 2026-05-25: Orchestrator ruft Stage-unload auch bei Listener-/Checkpoint-Exception.
- B-368 ist fixed im Vault am 2026-05-25: VectorDB-Delete-Fehler bricht Writes ab; VectorDB-Write laeuft erst nach SQLite-Szenencommit.
- B-369 ist fixed im Vault am 2026-05-25: Soft-deleted VideoClips werden in Pipeline, Actions, Worker-Lookups und Search gefiltert.
- B-372 ist fixed im Vault am 2026-05-25: Embedding-Cache speichert Modellvarianten mit Composite-Key; Scheduler skippt nicht mehr hash-only.
- B-375 ist fixed im Vault am 2026-05-25: Legacy pacing memory ignoriert soft-deleted AudioTracks und Szenen aus soft-deleted VideoClips.
- B-376 ist fixed im Vault am 2026-05-25: PatternAggregator normiert `good/bad` auf `accept/reject`.
- B-378 ist fixed im Vault am 2026-05-25: Feedback-Batch-Flush laeuft im Hintergrund und startet nicht doppelt parallel.
- B-379 ist fixed im Vault am 2026-05-25: Debounced ClipInspector writes behalten die Entry-ID des geaenderten Clips.
- B-380 ist fixed im Vault am 2026-05-25: ClipInspector ignoriert stale async load results fuer alte Entry-IDs.
- B-381 ist fixed im Vault am 2026-05-25: Timeline `_anchor_map` wird bei Anchor add/remove ohne Reload aktualisiert.
- B-382 ist fixed im Vault am 2026-05-25: Anchor-Sync clamp't DB `start_time` konsistent zur UI auf 0.
- B-383 ist user-gated: Code-Fix committed (925a5fc), wartet auf User-Live-Verify. Vom User uebersprungen am 2026-05-25.
- B-384 ist code-fix-pending-live-verification im Vault am 2026-05-25: Kontextmenue "Alle Anker entfernen" auch fuer unsichtbare Anker (`_all_anchor_offsets`); Repro pre-fix FAIL, post-fix direkt 1 passed, collect-only 2232.
- B-385 ist code-fix-pending-live-verification im Vault am 2026-05-25: `render_grid_lines` leert die Scene nicht mehr; Waveform bleibt erhalten; Grid-Lines getrackt. Repro pre-fix FAIL, post-fix 2 passed, collect-only 2234.
- B-386 ist code-fix-pending-live-verification im Vault am 2026-05-25: Waveform-Baender werden auf gleiche Laenge normalisiert (kein IndexError beim Paint). Repro pre-fix FFF, post-fix 3 passed, collect-only 2237.
- B-387 ist code-fix-pending-live-verification im Vault am 2026-05-25: VideoPreview verwirft spaete Frames fremder Pfade (`_active_request_path`). Repro pre-fix FAIL, post-fix 2 passed, collect-only 2239.
- B-388 ist code-fix-pending-live-verification im Vault am 2026-05-26: Thumbnail-Worker liefert QImage statt QPixmap; GUI-Slot wandelt um. Repro pre-fix FAIL, post-fix 2 passed, collect-only 2241.
- B-389 ist code-fix-pending-live-verification im Vault am 2026-05-26: Thumbnail-done-Slot via `_apply_thumbnail` gegen geloeschte Cards geschuetzt. Repro pre-fix FAIL, post-fix 2 passed, collect-only 2243.
- B-390 ist code-fix-pending-live-verification im Vault am 2026-05-26: Convert-Effekt-Preview verwirft veraltete Worker via Request-Sequenz. Repro pre-fix FAIL, post-fix 2 passed, collect-only 2245.
- B-391 ist code-fix-pending-live-verification im Vault am 2026-05-26: FrameExtract `-v error` + Exitcode-Fallback statt `-v quiet`. Repro pre-fix FAIL, post-fix 2 passed, collect-only 2247.
- Area 7 (B-379..B-391) damit code-fertig ausser B-383 (user-gated).
- B-392 ist fixed im Vault am 2026-05-26: ConvertWorkspace-Smoke-Testvertrag auf zwei dokumentierte Tabs aktualisiert; direct `1 passed`, Workspace-Smoke `7 passed`, nahe Tests `3 passed`, collect `2247`.
- B-393 ist code-fix-pending-live-verification im Vault am 2026-05-26: Export `output_name` wird filename-only validiert; path traversal RED, post-fix direct `1 passed`, Export-near `5 passed`, Core ExportService `1 passed`, collect `2248`; Live-Export offen.
- B-394 ist code-fix-pending-live-verification im Vault am 2026-05-26: Agent export action lehnt absolute `output_path` ab und emittiert keinen Task; direct `2 passed`, Agent/Wiring-nahe `53 passed`, collect `2250`; Live-Action offen.
- B-395 ist code-fix-pending-live-verification im Vault am 2026-05-26: `source_duration <= 0` wird vor FFmpeg abgelehnt; direct `1 passed`, Export-near `6 passed`, Core ExportService `1 passed`, collect `2251`; Live-Export offen.
- B-396 ist code-fix-pending-live-verification im Vault am 2026-05-26: Source-Range wird gegen `clip.duration` begrenzt; direct `2 passed`, Export-near `7 passed`, Core ExportService `1 passed`, collect `2252`; Live-Export offen.
- B-397 ist code-fix-pending-live-verification im Vault am 2026-05-26: Video-Timeline-Gaps werden vor Renderer abgelehnt statt still verkuerzt; direct `1 passed`, Export-near `8 passed`, Core ExportService `1 passed`, collect `2253`; Live-Export offen.
- B-398 ist code-fix-pending-live-verification im Vault am 2026-05-26: Summary zaehlt nur exportierbare aktive Medien; direct `1 passed`, Summary-near `3 passed`, Export-near `12 passed`, collect `2254`; Live-GUI offen.
- B-399 ist code-fix-pending-live-verification im Vault am 2026-05-26: AudioEntry `start_time`/`source_start`/`source_end` wird vor Export als Temp-WAV geschnitten und per `adelay` auf Timeline-Start versetzt; direct `1 passed`, Export-near `13 passed`, collect `2255`; Live-Export offen.
- B-400 ist code-fix-pending-live-verification im Vault am 2026-05-26: Orphan-Cleanup entfernt jetzt auch `pb_concat_*` und `pb_fcs_*`; direct `1 passed`, Export-near `14 passed`, collect `2256`; Live-Export-Start offen.
- B-401 ist code-fix-pending-live-verification im Vault am 2026-05-26: BatchConvertWorker nutzt Popen+Cancel-Watchdog statt blockierendem `subprocess.run`; direct `1 passed`, Convert-nahe `17 passed`, collect `2257`; Live-Batch-Convert offen.
- B-402 ist code-fix-pending-live-verification im Vault am 2026-05-26: Convert-Progressbar nutzt Range `0..100`, passend zu Worker-Prozentwerten; direct `1 passed`, UI/Convert-nahe `7 passed`, collect `2258`; Live-GUI offen.
- B-403 ist code-fix-pending-live-verification im Vault am 2026-05-26: BatchConvertWorker nutzt `get_ffmpeg_bin()` statt PATH-Literal `ffmpeg`; direct `1 passed`, Batch/Convert-nahe `16 passed`, collect `2259`; Live-Batch-Convert offen.
- B-404 ist code-fix-pending-live-verification im Vault am 2026-05-26: HEVC-UI-Auswahl mappt auf `hevc_nvenc` statt `libx265`; pre-fix RED sah `libx265`; direct `1 passed`, UI/Convert-nahe `16 passed`, collect `2260`; Live-HEVC-Batch-Convert offen.
- B-405 ist code-fix-pending-live-verification im Vault am 2026-05-26: BatchConvertWorker lehnt `libaom-av1` fuer GTX-1060-Ziel ab und startet kein FFmpeg; pre-fix RED startete FFmpeg mit `libaom-av1`; direct `1 passed`, Batch/Convert-nahe `19 passed`, collect `2261`; Live-Batch-Convert offen.
- B-406 ist code-fix-pending-live-verification im Vault am 2026-05-26: `VideoAnalyzer.create_proxy()` nutzt `h264_nvenc`-Edit-Proxy-Parameter statt `libx264`; pre-fix RED sah `libx264`; direct `1 passed`, Video/Proxy-nahe `32 passed`, collect `2262`; Live-Proxy-Workflow offen.
- B-407 ist code-fix-pending-live-verification im Vault am 2026-05-26: LUFS-Subprocess-Timeout wird nach Kill wieder als Timeout raised; `_normalize_audio_lufs()` macht daraus harten RuntimeError statt `False`; pre-fix RED zeigte Soft-Fallback; direct `2 passed`, Export/LUFS-nahe `18 passed`, collect `2264`; Live-Export offen.
- B-408 ist code-fix-pending-live-verification im Vault am 2026-05-26: LUFSAnalysisWorker schreibt nicht mehr auf soft-deleted AudioTracks; pre-fix RED schrieb `lufs=-9.25`; direct `1 passed`, Audio-Worker-nahe `14 passed`, collect `2265`; Live-GUI-LUFS offen.
- B-409 ist code-fix-pending-live-verification im Vault am 2026-05-26: Chat-Watchdog setzt Agent-Worker-Cancel-Flag, trennt UI-Slots und fordert Thread-Abbruch an; direct `1 passed`, Chat/Agent-nahe `63 passed`, collect `2266`; Live-Chat-Workflow offen.
- B-410 ist code-fix-pending-live-verification im Vault am 2026-05-26: `AIAgentWorker` haelt den gemeinsamen Registry-Lock jetzt ueber Registry-Swap, `agent.process()` und Restore; pre-fix RED belegte Registry-Wechsel zwischen parallelen Workern; direct `1 passed`, Chat/Agent-nahe `64 passed`, collect `2267`; Live-Chat-Workflow offen.
- B-411 ist code-fix-pending-live-verification im Vault am 2026-05-26: `LocalAgentService._execute_single_action()` hebt Handler-Rueckgaben `{"error": ...}` auf Top-Level `error` und laesst `result` leer; pre-fix RED zeigte Fehler-Dict als Action-Erfolg; direct `1 passed`, Agent/Chat-nahe `32 passed`, collect `2268`; Live-Chat-Workflow offen.
- B-412 ist code-fix-pending-live-verification im Vault am 2026-05-26: GUI-affine Chat-Actions `create_project`, `open_project`, `undo_timeline`, `redo_timeline`, `sync_anchors` laufen via BlockingQueuedConnection im Qt-Main-Thread; pre-fix RED zeigte `undo()` im Worker-Thread; direct/near `66 passed`, collect `2270`; Live-Chat-Workflow offen.
- B-413 ist code-fix-pending-live-verification im Vault am 2026-05-26: `DESTRUCTIVE_ACTIONS` deckt jetzt `delete_media`, `clear_timeline`, `remove_clip`, `remove_anchor`; pre-fix RED erlaubte `clear time line` -> `clear_timeline`; ActionRegistry `29 passed`, Agent/UI-nahe `39 passed`, collect `2274`; Live-Chat-Workflow offen.
- B-414 ist code-fix-pending-live-verification im Vault am 2026-05-26: destruktive Actions lehnen unbekannte Parameter vor Handler-Ausfuehrung ab; pre-fix RED fuehrte `clear_timeline` trotz `project_id`/`confirm` aus; ActionRegistry `30 passed`, Agent-nahe `37 passed`, collect `2275`; Live-Chat-Workflow offen.
- B-415 ist code-fix-pending-live-verification im Vault am 2026-05-26: `add_to_timeline` filtert Media-Lookups auf aktives `project_id` und `deleted_at is None`; pre-fix RED commitete fremde/soft-deleted Clips; direct `2 passed`, nahe `69 passed`, collect `2277`; Live-Chat-Workflow offen.
- B-416 ist code-fix-pending-live-verification im Vault am 2026-05-26: Quick-Commands matchen keine normalen Erklaer-Saetze mehr via Substring; pre-fix RED matchte `erklaere pacing` und `analysiere bitte den begriff`; direct `3 passed`, Chat/Agent-nahe `7 passed`, collect `2280`; Live-Chat-Workflow offen.
- B-417 ist code-fix-pending-live-verification im Vault am 2026-05-26: Request-ID- und Projektkontext-Validierung in ChatDock gegen stale Worker-Ergebnisse; direct `2 passed`, collect `2282`; Live-Chat-Workflow offen.
- Area 9 (B-409..B-417) damit code-fertig.
- B-418 ist fixed im Vault am 2026-05-27: Ueberarbeitung der Installationsdokumentation auf Conda/Python 3.10/CUDA 11.3 (requirements-py310-cu113.txt).
- B-419 ist fixed im Vault am 2026-05-27: Ueberarbeitung der Deploymentdokumentation auf Conda/Python 3.10/CUDA 11.3 (requirements-py310-cu113.txt) und Richtigstellung der requirements.txt.
- B-420 ist fixed im Vault am 2026-05-27: build_installer.bat dynamisiert, erkennt Conda-Umgebung.
- B-421 ist code-fix-pending-live-verification im Vault am 2026-05-27: pb_studio.spec um config, translations und migrations erweitert.
- B-422 ist code-fix-pending-live-verification im Vault am 2026-05-27: pb_studio.spec um ffmpeg und ffprobe im bin-Ordner erweitert.
- B-423 ist code-fix-pending-live-verification im Vault am 2026-05-27: pb_studio.spec um packaging hiddenimports und datas erweitert.
- B-424 ist fixed im Vault am 2026-05-27: Race-Condition im --pre-cache CLI-Handler behoben und blockierende Wartezeit durch done_event garantiert.
- B-425 ist fixed im Vault am 2026-05-27: NSIS Installer-Bitmaps AI-generiert und in resources abgelegt.
- B-426 ist fixed im Vault am 2026-05-27: start_pb_studio.py wählt Python-Pfade nach Auto-Setup dynamisch neu aus.
- B-427 ist code-fix-pending-live-verification im Vault am 2026-05-27: check_ffmpeg akzeptiert System-PATH; README FFmpeg korrigiert; 3/3 Unit-Tests.
- B-428 ist code-fix-pending-live-verification im Vault am 2026-05-27: NSIS GPU-Meldung korrigiert (CUDA 11.3, kein CPU-Mode).
- B-429 ist code-fix-pending-live-verification im Vault am 2026-05-27: README PySide6 Qt 6.6-6.7 statt Qt 6.8+.
- B-430 ist code-fix-pending-live-verification im Vault am 2026-05-27: Smoke-Test um CUDA/Torch-DLLs, FFmpeg, config, translations erweitert.
- Area 10 (B-418..B-430) damit code-fertig.
- **Gesamter Fixplan PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25 (B-348..B-430) code-complete.**
- Live-Verify Runde 1 (2026-05-29, pb-gui-tester, outputs/GUI_Verify_2026_05_29): Packaging 7/7 PASS, GUI Media PASS/partial, Export 10/10 PASS, Convert 7/7 PASS.
- GUI Schnitt Lauf 1 (2026-05-29): B-385 PASS live, B-386 PASS live, B-387 INCONCLUSIVE, B-384 nicht verifiziert (Tester-Limit Lauf 1), B-390 nicht erreicht. Beat→Timeline (56 Cuts) live OK.
- GUI Schnitt Lauf 2 (2026-05-29, bestehendes Projekt): B-384 PASS live (DB-belegt, Screenshot), B-387 INCONCLUSIVE (Race nicht erzwingbar, Code-Guard ok), B-390 INCONCLUSIVE-GUI + Service-Test 2 passed (EFFEKTE-Tab nicht erreichbar = separate UX-Luecke). Report: outputs/GUI_Verify_2026_05_29/verify_report_b384_387_390.md.
- GUI-Schnitt Gesamtstand: B-384/385/386 PASS (Agent-Verify), B-387 INCONCLUSIVE, B-390 INCONCLUSIVE-GUI+Service-PASS. Alle = Agent-Verify, `status:fixed` weiterhin nur User.
- Offen: B-387/B-390 echte Race- bzw. EFFEKTE-Tab-GUI-Verifikation (separate UI-Erreichbarkeit). Chat-Bereich B-409..B-417 noch ungetestet.
- Offen Chat-Bereich: B-409..B-417 Live-Chat-Workflow noch ungetestet.
- Naechster Schritt: User-Live-Verification der offenen code-fix-pending-live-verification Bugs.
