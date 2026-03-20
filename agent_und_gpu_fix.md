# Agent & GPU Fix — Dokumentation

## Datum: 2026-03-20

---

## SEKTOR 1: Hardcore GPU-Enforcement

### Problem
Die App konnte stillschweigend auf CPU zurückfallen, selbst wenn eine NVIDIA GPU (GTX 1060) verfügbar war. Es gab keine prominente Anzeige der aktiven Hardware.

### Lösung

#### 1. ModelManager (`services/model_manager.py`)
- **GPU-ZWANG**: Wenn `torch.cuda.is_available()` True ist, wird `device="cuda"` erzwungen — egal was übergeben wird
- **Hardware-Banner**: Beim ersten Init wird ein prominenter Banner auf stdout UND ins Logging geschrieben:
  ```
  ============================================================
    HARDWARE AKTIV: NVIDIA GeForce GTX 1060 6GB
    VRAM: 6144 MB | CUDA: 12.x
    GPU-ZWANG: Alle KI-Modelle laufen auf CUDA
  ============================================================
  ```
- **`gpu_info` Property**: Gibt Hardware-Info als Dict zurück (für UI-Anzeige)
- Warnung wenn jemand versucht, `device="cpu"` zu übergeben obwohl CUDA da ist

#### 2. Video Analysis Service (`services/video_analysis_service.py`)
- **RAFT Optical Flow**: Explizites GPU-ZWANG-Logging beim Laden
- SigLIP nutzt automatisch den ModelManager (GPU-Zwang dort bereits aktiv)

#### 3. Beat Analysis Service (`services/beat_analysis_service.py`)
- **beat_this**: Explizites GPU-ZWANG-Logging beim Modell-Laden
- Device-Property erzwingt CUDA wenn verfügbar

#### 4. LocalAgentService (`services/local_agent_service.py`)
- GPU-ZWANG auch hier: CUDA wird erzwungen, CPU-Override wird gewarnt

---

## SEKTOR 2: KI-Agent Wiring (Chat Dock)

### Problem
Der Chat-Agent war ein Dummy — Texteingaben führten zu keinen echten UI-Aktionen. Der "KI verarbeitet..." Status blieb endlos stehen.

### Lösung

#### 1. ChatDock (`ui/chat_dock.py`)
- **`set_main_window()`**: Neue Methode — verbindet Chat mit dem Hauptfenster
- **Quick-Command-Detection**: Bekannte Befehle werden DIREKT erkannt (ohne LLM):
  - `"analysiere"` → Markiert ALLE Videos im Pool, startet `_start_video_pipeline()`
  - `"schneide"` / `"auto-edit"` → Startet `_auto_edit_to_beat()`
  - `"gpu status"` / `"hardware"` → Zeigt GPU-Info im Chat
- **Agent-Antworten**: Der Chat schreibt echte Antworten:
  - "Ich habe alle X Videos markiert und starte die Analyse auf der GPU!"
  - "Auto-Edit wird gestartet! Schneide Videos zum Beat..."
- **Dummy-Status entfernt**: "KI verarbeitet..." → "Agent arbeitet..." (nur bei LLM-Fallback)
- Unbekannte Befehle gehen weiterhin an den Orchestrator/LLM

#### 2. MainWindow (`main.py`)
- `setup_chat_dock()` erweitert:
  - `chat_dock.set_main_window(self)` — MainWindow-Referenz gesetzt
  - GPU-Status wird beim Start in Konsole UND Chat angezeigt
  - Verfügbare Befehle werden im Chat-Willkommensnachricht gelistet

---

## Befehlsübersicht (Chat-Agent)

| Befehl | Aktion | Antwort |
|--------|--------|---------|
| `analysiere` | Alle Videos markieren + Pipeline starten | "Ich habe alle X Videos markiert..." |
| `schneide` / `auto-edit` | Auto-Edit mit DJ-Pacing starten | "Auto-Edit wird gestartet..." |
| `gpu status` / `hardware` | GPU-Info anzeigen | "HARDWARE AKTIV: GTX 1060..." |
| Alles andere | → Orchestrator → LLM | Dynamische Antwort |

---

## Geänderte Dateien

1. `services/model_manager.py` — GPU-Zwang, Hardware-Banner, gpu_info Property
2. `services/video_analysis_service.py` — RAFT GPU-Zwang-Logging
3. `services/beat_analysis_service.py` — beat_this GPU-Zwang-Logging
4. `services/local_agent_service.py` — GPU-Zwang bei Device-Auswahl
5. `ui/chat_dock.py` — Quick-Commands, MainWindow-Anbindung, Agent-Antworten
6. `main.py` — Chat-Setup mit GPU-Status und MainWindow-Referenz
