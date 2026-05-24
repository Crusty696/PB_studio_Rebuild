---
title: ComfyUI Audit - 30_Workflows/Migration_Setup.md
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\Migration_Setup.md
status: live-verified
next_reference_file: 30_Workflows\Music_Video_Pipeline.canvas
---

# Audit: `30_Workflows\Migration_Setup.md`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\Migration_Setup.md
```

- Groesse: 10.372 Bytes.
- SHA256: `A03CB7B5DBDAB3D555C61936E0078A031482693D82D40F52160C9F91752E1F65`.
- Markdown-Dokument mit Frontmatter:
  - `type: reference`
  - `project: ComfyUI-Studio`
  - `created: 2026-05-22`
  - `updated: 2026-05-22`
  - Tags: `migration`, `setup`, `install`, `environment`, `portability`

## Belegter Inhalt

Die Datei dokumentiert Portabilitaet fuer einen ComfyUI-Studio-Vault:

- Skripte nutzen `COMFY_STUDIO_VAULT` oder leiten die Vault-Wurzel aus der Skriptposition ab.
- `COMFY_OUTPUT_DIR` und `COMFY_INPUT_DIR` haben hartkodierte Fallbacks auf den Original-ComfyUI-Pfad und muessen auf anderen Layouts gesetzt werden.
- `_meta\install.ps1 -Persist` prueft ComfyUI-Installation, `ffmpeg`, `ffprobe`, Python-venv, Obsidian-Konfig, Env-Variablen und Cache-Konsistenz.
- Migration schliesst temporaere Renderdaten und finale Videos bewusst aus.
- Cache-Artefakte `_*.json` und `*.npz` sollen mitgenommen werden, weil sie wenige MB belegen und laut Datei Minuten bis Stunden Re-Inferenz sparen.
- Der Modell-Stack ist vom Vault getrennt. Die Datei empfiehlt `HF_HOME`, damit Hugging-Face-Cache portabel wird.
- Sanity-Check nach Migration prueft `ffprobe`, `ffmpeg`, Python-venv, CUDA/HIP, ComfyUI-Port 8000, Env-Variablen und idempotenten Testlauf.

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `services\startup_checks.py`: prueft FFmpeg/ffprobe, CUDA/GPU, Disk, Ollama, ML-Pakete und liefert `SystemStatus`.
- `ui\dialogs\startup_check_dialog.py`: zeigt Startup-Fehler/Warnungen an.
- `ui\dialogs\setup_wizard.py`: First-Run Hardware-/Modell-Wizard; referenziert aktuell `run_startup_checks`, waehrend `services\startup_checks.py` belegbar `check_system` enthaelt.
- `services\model_lifecycle_service.py`: liest `HF_HOME` oder `HUGGINGFACE_HUB_CACHE` fuer Modell-Cache-Status.
- `docs\PRODUCTION_CONFIG.md` und `docs\DEPLOYMENT.md`: dokumentieren `HF_HOME`.
- `services\startup_checks.py:get_ffmpeg_bin()` und `get_ffprobe_bin()` loesen lokale `bin\`-Tools oder `FFMPEG_PATH`/`FFPROBE_PATH` auf.

Nicht gefunden:

- Kein PB-eigenes ComfyUI-Vault.
- Kein produktiver ComfyUI-Output-/Input-Ordner in PB.
- Kein PB-Startup-Status fuer `HF_HOME`/`HUGGINGFACE_HUB_CACHE`.
- Kein Startup-Status, der die konkret aufgeloesten FFmpeg-/ffprobe-Pfade sichtbar macht.

## Vergleich

Referenz:

- Macht Portabilitaet zur expliziten Betriebsregel.
- Validiert Tools, Env-Variablen und Cache-Erhalt vor Migration.
- Trennt Vault-Daten, temporaere Renderdaten und grosse Modell-Caches.
- Nutzt hartkodierte ComfyUI-spezifische Fallbacks fuer Output/Input, dokumentiert deren Risiko.

PB Studio:

- Hat bereits Startup-Checks und UI-Darstellung.
- Hat bessere App-spezifische GPU-/CUDA-Pruefung fuer GTX-1060-Kontext.
- Hat `HF_HOME` nur in Doku und Modell-Lifecycle, nicht im allgemeinen Systemstatus.
- Hat eine konkrete Inkonsistenz im SetupWizard-Importpfad (`run_startup_checks` vs. `check_system`).

## Integrationsentscheidung

Gezielte App-Code-Aenderung sinnvoll, aber eng begrenzt.

Grund:

- Die Referenz liefert keinen direkt kopierbaren Python-Code, aber belegte bessere Betriebslogik: Portabilitaetsstatus sichtbar machen, bevor teure Modell-/Video-Pipeline-Pfade fehlschlagen.
- PB Studio besitzt bereits den passenden Integrationspunkt (`SystemStatus`, StartupCheckDialog, SetupWizard). Das ist additiv und aendert PB Studios Grundkonzept nicht.
- `HF_HOME` ist auch PB-relevant, weil PB Studio Hugging-Face-Modelle nutzt und bereits `HF_HOME`/`HUGGINGFACE_HUB_CACHE` in `model_lifecycle_service.py` liest.
- `COMFY_STUDIO_VAULT`, `COMFY_OUTPUT_DIR` und `COMFY_INPUT_DIR` sind ComfyUI-spezifisch und werden nicht als PB-Pflichtstatus integriert.

## Zielpfade und Ersetzungsblock

Zielpfade:

- `services\startup_checks.py`
- `ui\dialogs\startup_check_dialog.py`
- `ui\dialogs\setup_wizard.py`
- `tests\test_services\test_startup_checks_environment.py` (neu)

Geplanter Code-Block:

- `SystemStatus` additiv erweitern um Tool-Pfade und Modell-Cache-Felder.
- Helper fuer Hugging-Face-Cache-Status hinzufuegen.
- `check_system()` fuehrt Cache-Check parallel aus und schreibt Warnungen nur nicht-blockierend.
- `run_startup_checks()` als Alias auf `check_system()` ergaenzen, damit SetupWizard-Pfad nicht mehr fehlschlaegt.
- StartupCheckDialog und SetupWizard zeigen FFmpeg-/ffprobe-Pfad und Hugging-Face-Cache-Status.

Nicht integrieren:

- Kein ComfyUI-Server-Check.
- Kein `COMFY_*`-Env-Pflichtcheck.
- Kein neuer Download- oder Installationsprozess.
- Kein GPU-/CUDA-Backend-Wechsel.

## Testplan

- Unit-Test: `HF_HOME` gesetzt, existiert und ist schreibbar -> Cache-Status ok.
- Unit-Test: `HF_HOME` fehlt und `HUGGINGFACE_HUB_CACHE` fehlt -> nicht-blockierende Warnung.
- Unit-Test: `HUGGINGFACE_HUB_CACHE` gesetzt -> Status zeigt granularen Cache-Pfad.
- Unit-Test: `run_startup_checks()` existiert und ruft `check_system()`.
- Import-/Syntaxcheck fuer `services.startup_checks`, `ui.dialogs.startup_check_dialog`, `ui.dialogs.setup_wizard`.
- UI-Live-Verifikation bleibt offen: App starten, Startup-/Setup-Anzeige ansehen, Log pruefen.

## Risiko

- Niedrig fuer Backend: additive Felder im Dataclass-Status.
- Mittel fuer UI: Dialog-Layout kann bei langen Pfaden unuebersichtlich werden.
- Niedrig fuer Runtime: keine neuen Abhaengigkeiten und keine externen Calls.

## Verifikation

- Referenzdatei voll gelesen.
- Dateigroesse und SHA256 geprueft.
- PB-Gegenstuecke per `rg` und Dateiinspektion geprueft.
- Externe Hugging-Face-Doku geprueft: `HF_HOME` ist Basis fuer Hub-Daten; `HF_HUB_CACHE` defaultet unter `HF_HOME\hub`.
- Code umgesetzt in `services\startup_checks.py`, `ui\dialogs\startup_check_dialog.py`, `ui\dialogs\setup_wizard.py` und `tests\test_services\test_startup_checks_environment.py`.
- Syntaxcheck: `python -m py_compile services\startup_checks.py ui\dialogs\startup_check_dialog.py ui\dialogs\setup_wizard.py` gruen.
- Unit-Tests: `python -m pytest tests\test_services\test_startup_checks_environment.py tests\test_services\test_startup_checks_gpu.py -q` im Conda-Env `pb-studio` gruen: 11 passed.
- Import-Smoke: `services.startup_checks`, `ui.dialogs.startup_check_dialog`, `ui.dialogs.setup_wizard` geladen.
- Qt-Offscreen-Smoke: `StartupCheckDialog(SystemStatus(...))` und `SetupWizard()` instanziiert.
- Live-App-Start ausgefuehrt: `main.py` im Conda-Env `pb-studio` gestartet, Fenster `PB_studio v0.5.0 - Director's Cockpit` erschien, Prozess war responsive.
- Realer UI-Klickpfad ausgefuehrt: Workflow-Navigation `Projekt -> Material und Analyse -> Schnitt -> Export` per UIA/pywinauto geklickt.
- Log-Auswertung fuer aktuellen Lauf `2026-05-24 20:27..20:30`: keine `Traceback`, keine `UNHANDLED`, keine `CRITICAL`, kein `Systemcheck abgestuerzt`, kein `Fehler bei finaler Initialisierung`, kein `AttributeError`, kein `TypeError`.
- App sauber geschlossen; Log zeigt Shutdown/CUDA-Cleanup.

## Naechste Datei

`30_Workflows\Music_Video_Pipeline.canvas`
