# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-AREA-AUDIT-FIXPLAN-2026-05-25
next_allowed_task: B-393 (Area 8 Export; B-392 fixed)
updated: 2026-05-25

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
- Naechster erlaubter Task: B-393 (Area 8 Export, numerische Reihenfolge).
