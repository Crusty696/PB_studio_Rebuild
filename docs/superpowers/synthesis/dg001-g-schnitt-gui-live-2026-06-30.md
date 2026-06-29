# DG-001 G.* SCHNITT GUI Live Verification — 2026-06-30

Status: **AGENT-LIVE-PASS fuer G.2/G.3-Ersatzbeleg**

Wichtig: Das ist kein `fixed`/Release-Entscheid. DG-001 bleibt offen, weil der
User-Entscheid zum H1-Ersatzmedium weiter fehlt.

## Runner

`scripts/diag/verify_dg001_g_schnitt_gui.py`

Finaler Lauf:

```powershell
$env:CUDA_MODULE_LOADING='LAZY'
$env:PB_REQUIRE_NVENC='1'
$env:KMP_DUPLICATE_LIB_OK='TRUE'
$env:OMP_NUM_THREADS='4'
$env:MKL_NUM_THREADS='4'
& 'C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe' -u scripts\diag\verify_dg001_g_schnitt_gui.py --timeout-s 15
```

Exit-Code: `0`

## Belegte Resultate

Aus `test-report/dg001-g-schnitt-gui-20260630/result.json`:

```json
{
  "workspace_visible": true,
  "workspace_state": 2,
  "workspace_state_expected_editor": 2,
  "tab_labels": ["Schnitt", "Pacing & Anker", "Audio", "RL & Notes"],
  "clip_count": 2,
  "audio_clip_count": 1,
  "locked_video_clip_count": 1,
  "waveform_item_count": 1,
  "notes_saved": true,
  "regenerate_modal": {
    "seen": true,
    "window_title": "Pacing neu anwenden?",
    "text": "Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?"
  },
  "regenerate_signal_after_no": 0,
  "screenshot_saved": true,
  "passed": true
}
```

## Was real geprüft wurde

- Echter `QApplication`-Lauf, sichtbarer `SchnittWorkspace`.
- Echte Projekt-SQLite-DB pro Lauf unter `test-report/dg001-g-schnitt-gui-20260630/project_<timestamp>_<uuid>/pb_studio.db`.
- Echte SCHNITT-Widgets: `Schnitt`, `Pacing & Anker`, `Audio`, `RL & Notes`.
- Timeline lädt asynchron aus DB und rendert zwei Clips.
- Gelockter Video-Clip wird aus `timeline_entries.locked=True` als locked Item sichtbar.
- Audio-Waveform wird aus `waveform_data` sichtbar.
- RL Notes schreiben in `project_notes` und werden über Service-Roundtrip gelesen.
- Re-Generate-Warnung erscheint als echte `QMessageBox`; Klick auf `No` emittiert kein Regenerate-Signal.
- Screenshot gespeichert: `test-report/dg001-g-schnitt-gui-20260630/schnitt_workspace.png`.

## Grenzen

- Synthetisches Minimalprojekt, nicht verlorenes historisches `test55655`.
- Kein kompletter Original-Produktionslauf mit allen Workspaces.
- Kein User-`fixed`: dieser Beleg deckt G.2/G.3 neu ab, hebt DG-001 aber nicht auf.

