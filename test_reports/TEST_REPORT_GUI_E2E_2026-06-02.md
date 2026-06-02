# PB Studio GUI E2E Report - 2026-06-02

## Scope

- Auftrag: GUI-E2E-Test mit Video-Nachweis.
- Skill-Kontext: `pb-functional-tester`, echte Vordergrund-GUI, keine App-Code-Aenderung.
- Projekt: `e2e_20260602_0721`
- Projektpfad: `C:\Users\David Lochmann\Downloads\test\e2e_20260602_0721`
- Videoquelle: `C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur`

## Video Evidence

- Combined recording: `test_reports\gui_e2e_combined_all_20260602.mp4` (segments 1-4, duration 659.93s)
- Segment 1: `test_reports\gui_e2e_20260602_070900.mp4`
- Segment 2: `test_reports\gui_e2e_import_20260602_072405.mp4`
- Segment 3: `test_reports\gui_e2e_import_result_20260602_072835.mp4`
- Segment 4: `test_reports\gui_e2e_late_import_20260602_073845.mp4`

Known recording gap: folder `Choose` click at approximately 07:28:32 happened between segment 2 and segment 3. Log and later UI state prove the folder was selected.

## Steps Executed

1. Started PB Studio in foreground through `tests\gui_harness.py`.
2. Created new project through the real `+ Neues Projekt` dialog.
3. Switched to `Material und Analyse Workflow`.
4. Clicked `Video Modus`.
5. Clicked `Ordner importieren`.
6. Selected `C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur`.
7. Observed video grid and task/log output.

## Observed Results

- Window title changed to `PB_studio v0.5.0 - e2e_20260602_0721`.
- Log line: `Neues Projekt erstellt: e2e_20260602_0721 (1920x1080, 30.0 fps)`.
- Log line: `ImportMedia._import_folder: Ordner gewaehlt: C:/Users/David Lochmann/Documents/Solo_Natur-20260406T220640Z-3-001/Solo_Natur`.
- Log line: `TaskEngine] Gestartet: FolderImport`.
- UI screenshot `tests\qa_artifacts\after_folder_import_wait2_20260602_073224.png` shows grid with imported video clips and status bar text `200 Datei(en) aus Ordner importiert | System bereit`.
- Background logs continued proxy conversion and SigLIP embedding after grid import became visible.

## Performance / Stability Findings

- Project create produced PerfWatchdog slow event: `6084ms | Timer -> QPushButton(btn_accent)`.
- Folder dialog open produced slow events around `774ms`, `900ms`, `957ms`.
- During import/proxy work, repeated UI slow events appeared, including values above 1000ms.
- At 07:41:20, logs still showed active conversion:
  `Konvertiere mit Preset 'edit_proxy': 20250719_0204_Enchanted_Bioluminescent_Jungle_v2_std.mp4`.

## Verdict

Status: FAIL / incomplete for full E2E.

What is verified by live GUI:
- App starts.
- Project creation works through GUI.
- Material workflow opens.
- Folder import can be triggered through GUI.
- Video grid shows imported clips.

What is not verified:
- Full 200-clip background proxy/embedding workload completion.
- Audio import.
- Audio analysis.
- Video analysis completion.
- Timeline/Schnitt result.
- Export.

No `fixed` or `verified` status marker written.
