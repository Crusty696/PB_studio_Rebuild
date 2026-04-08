# Lokale KI-Integration — Architektur-Plan

## Ziel

PB Studio nutzt einen lokalen LLM-Service (Ollama) als unsichtbaren Hintergrund-Prozess.
Der Service ermoeglicht KI-gestuetzte Funktionen (Clip-Beschreibungen, Schnitt-Vorschlaege,
Chat-Assistent) — vollstaendig offline, ohne Cloud-API, ohne Kosten.

## Architektur-Uebersicht

```
App Start
  |
  v
MainWindow.setup_chat_dock()
  |
  +-- LocalLLMService.instance().start()    # Ollama-Prozess starten
  |     |-- Prueft ob Ollama bereits extern laeuft
  |     |-- Sucht Binary: bin/ollama/, System-PATH
  |     |-- subprocess.Popen mit CREATE_NO_WINDOW (kein CMD-Popup)
  |     |-- Wartet auf Server-Bereitschaft (Health-Check)
  |     +-- atexit.register() fuer sauberen Shutdown
  |
  +-- LocalAgentService(ollama_url=...)     # Chat-Agent verbinden
  |
  +-- ChatDock.set_agent(...)               # UI-Anbindung
  |
  v
App laeuft — LLM verfuegbar fuer:
  - ChatDock: Freitext-Anfragen
  - prompt_to_edit(): Strukturierte JSON-Antworten
  - Clip-Analyse, Pacing-Vorschlaege, Schnitt-Entscheidungen

App Exit
  |
  v
atexit -> LocalLLMService._cleanup() -> terminate/kill Ollama-Prozess
```

## Komponenten

### 1. LocalLLMService (`services/llm_service.py`)

- **Rolle:** Singleton-Service fuer Ollama-Prozess-Lifecycle
- **Pattern:** Thread-safe Singleton via `instance()` + `_instance_lock`
- **Prozess-Start:** `subprocess.Popen` mit `creationflags=0x08000000`
- **Cleanup:** `atexit.register(self._cleanup)` — terminate, dann kill nach 5s
- **API:** `prompt_to_edit(user_text)` gibt strukturiertes JSON zurueck
- **Externe Erkennung:** Kein Doppelstart wenn Ollama bereits laeuft

### 2. OllamaClient (`services/ollama_client.py`)

- **Rolle:** HTTP-Client fuer Ollama REST-API (localhost:11434)
- **Abhaengigkeiten:** Nur stdlib (`urllib`) — kein requests/httpx
- **VRAM-Koordination:** Kann pausiert werden wenn GPU-intensive Modelle (Demucs, SigLIP) laden

### 3. UI-Integration (`ui/mixins/panel_setup.py`)

- **Wo:** `setup_chat_dock()` Methode
- **Ablauf:** Settings lesen -> LLM starten -> Agent verbinden -> ChatDock initialisieren
- **Feedback:** Konsolen-Meldungen (`[LLM] Ollama-Server gestartet.`)
- **Fallback:** Wenn Ollama nicht verfuegbar -> HuggingFace-Backend als Alternative

### 4. Settings (`ui/dialogs/settings_dialog.py`)

- **Konfigurierbar:** Ollama URL, Modell, Enabled/Disabled
- **Funktion:** `get_ollama_settings()` gibt `{url, model, enabled}` zurueck

## Empfohlene Modelle (GTX 1060, 6 GB VRAM)

| Modell                          | Groesse  | Eignung                    |
|---------------------------------|----------|----------------------------|
| `phi3:mini`                     | ~2.3 GB  | Schnell, kompakt           |
| `qwen2.5:1.5b-instruct`        | ~1.0 GB  | Sehr klein, schnell        |
| `llama3:8b`                     | ~4.7 GB  | Allrounder                 |
| `gemma3:4b`                     | ~3.0 GB  | Standard-Modell (geplant)  |

## Ollama-Binary

- **Primaer:** `bin/ollama/ollama.exe` (mitgeliefert im Projekt)
- **Sekundaer:** `bin/ollama.exe`
- **Fallback:** System-PATH (z.B. `C:\Users\<user>\AppData\Local\Programs\Ollama\ollama`)
- **Aktuell:** Binary wird ueber System-PATH gefunden. `bin/ollama/` ist fuer zukuenftige portable Distribution reserviert.

## Naechste Schritte

1. ~~LLM-Service implementieren~~ (erledigt)
2. ~~UI-Integration in panel_setup.py~~ (erledigt)
3. Gemma-Modell (`gemma3:4b`) via `ollama pull` installieren (optional)
4. Erweiterte prompt_to_edit()-Nutzung fuer:
   - Automatische Clip-Beschreibungen
   - Pacing-Vorschlaege basierend auf Audio-Analyse
   - Schnitt-Entscheidungen mit KI-Unterstuetzung
5. VRAM-Budget-Management: LLM pausieren wenn Demucs/SigLIP aktiv
