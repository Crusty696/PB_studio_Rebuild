# 61 — Live-Verify-Walkthrough fuer User

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: planned · 2026-05-19

## Ziel

User-Test-Skript fuer manuelle Live-Verifikation. `status: fixed` setzt User danach.

## Scope

### Kalt-Start (Erst-Install-Simulation)

1. PB Studio neu starten mit leerem `%APPDATA%/PBStudio/llm/`.
2. First-Run-Wizard erscheint.
3. Reasoner-Modell waehlen (z. B. qwen3:8b-q4) + Lizenz akzeptieren.
4. Pull-Progress laeuft, kein Hang.
5. Smoke-Chat-Call "Hallo" → Antwort gruen.

### Backend-Wechsel-Test

1. Settings → LM Studio (extern) Radio anclicken → grau, Tooltip "Folge-Plan".

### Modell-Wechsel-Hot-Reload

1. Settings → Reasoner waehlen llama3.1:8b.
2. Chat-Dock weiter benutzbar, neuer Call nutzt Llama.

### VRAM-Coexistence-Test

1. Audio-V2 starten (Demucs ueber Test-Datei).
2. Parallel Chat-Call → keine OOM-Crash.
3. Status-Dot bleibt gruen.

### Single-Instance-Test

1. PB Studio bereits offen.
2. Zweiter Doppelklick auf App-Verknuepfung.
3. Erste Instanz kommt nach vorne, zweite Instanz beendet sich.

### HF-Direct-Download

1. HF-Token in Settings eingeben.
2. Modell-Browser → HF-Tab → gguf-Modell waehlen.
3. Download + Modelfile-Generation + ollama create.
4. Smoke-Test mit neuem Modell.

### Modell-Lizenz-Dialog

1. Llama 3.x pullen.
2. Lizenz-Dialog erscheint, akzeptieren.
3. Eintrag in `llm_license_accepts`.
4. Re-Pull → kein Dialog.

### Tear-Down

1. App schliessen.
2. Daemon stirbt (Task-Manager pruefen).
3. PID-File entfernt.

## Akzept-Kriterien (User entscheidet)

- [ ] Alle Schritte ohne Stacktrace
- [ ] Keine erwarteten Warnings im Log
- [ ] VRAM-Coexistence-Test ohne Crash
- [ ] Status `code-fix-pending-live-verification` darf zu `fixed` werden
