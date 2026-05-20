# GUI Automation Helpers

Diese Skripte sind manuelle Diagnose- und Live-Verifikationshelfer fuer eine bereits laufende PB-Studio-App.

## Regeln

- Nicht automatisch in normalen Testlaeufen starten.
- Nur mit sichtbarer App und bewusstem User-Kontext nutzen.
- Keine generierten Dateien im Repo committen. Outputs gehoeren nach `outputs/`, `test_reports/` nur wenn ein Plan das explizit verlangt.
- Pfade in den Skripten vor Nutzung pruefen; einige Helfer enthalten lokale Testdatenpfade.

## Inhalt

- `debug_gui.py`, `map_gui.py`, `scan_ids.py`, `list_all_buttons.py`: UIA-Struktur/Controls inspizieren.
- `gui_nav_*.py`, `gui_switch_material.py`: Navigation pruefen.
- `gui_audio_import*.py`, `gui_video_import*.py`: Import-Flows manuell triggern.
- `wait_for_gui.py`, `find_material_tabs.py`, `gui_trigger_analysis.py`: fokussierte Workflow-Helfer.
