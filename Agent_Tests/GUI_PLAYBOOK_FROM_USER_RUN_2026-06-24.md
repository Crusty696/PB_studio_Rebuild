# GUI-Playbook — aus echtem User-Lauf 2026-06-24 (app_run_075538, 516 Klicks)

Verifizierte Aktionsabfolge + Selektoren (Targeting: objectName > Buttontext > Koordinate).
Klick-Targets sind QPushButton sofern nicht anders genannt.

## 0. Start
- StartupCheckDialog → "Weiter"  (auch wenn SystemCheck eine "FAIL"-Zeile zeigt)

## 1. PROJEKT
- Nav `workspace_btn` text="PROJEKT"
- `btn_accent` "+ Neues Projekt" → NewProjectDialog
- "..." (Pfad-Picker), ComboBox, `btn_ok` "Erstellen"
- danach `workflow_card`

## 2. MATERIAL & ANALYSE — Audio
- Nav `workspace_btn` "MATERIAL & ANALYSE"
- Mode "AUDIO"
- `btn_secondary` "+ Audio" → QFileDialog → "&Open"
- Analyse-Einzelschritte (`btn_secondary`): "Stems"→"Starten", "BPM / Beatgrid",
  "Wellenform", "Tonart", "LUFS", "Mood / Genre", "Spektral(analyse)", "Songstruktur"
- Status/Reste: "Fertige loeschen", "Aktualisieren", ProgressBar "x% (n/8 Schritte)"
- Nebenpfade benutzt: "Einstellungen"→SettingsDialog, Modell-Manager, "Storage-Browser"

## 3. MATERIAL & ANALYSE — Video
- Mode "VIDEO"
- `btn_secondary` "+ Ordner" / "+ Video" → QFileDialog → "&Open"
- `btn_select_toggle` "Alle"
- `btn_secondary` "Szenen"
- `btn_accent` "Video komplett analysieren"
- `btn_ai` "Keyframe-String"

## 4. SCHNITT  ← CRASH-STELLE (B-575)
- Nav `workspace_btn` "SCHNITT"
- `btn_accent` "Zur Timeline hinzufuegen"
- `btn_accent` "Auto-Edit"   →  HIER kam der Crash (WaveformGraphicsItem already deleted)
- später `btn_accent` "Timeline generieren" (mehrfach) → 2. Crash
- Crash zeigte `CrashDialogClassWindow` → "Schliessen"

## B-575 Retest-Fokus (nach Fix 618d8db)
Im analysierten Projekt: SCHNITT → "Auto-Edit" bzw. "Timeline generieren"
**mehrfach hintereinander** klicken. Erwartung: KEIN CrashDialog, kein
`Internal C++ object (WaveformGraphicsItem) already deleted` im Log.
