# AUD-48: E2E Test — Ollama Chat Dock UI

**Datum:** 2026-04-02 13:12:42
**Ergebnis:** BESTANDEN

## Test-Schritte

| Step | Name | Status | Detail |
|------|------|--------|--------|
| 1 | Ollama erreichbar (Port 11434) | ✅ | localhost:11434 offen |
| 2 | llama3:8b verfuegbar (llama3:8b) | ✅ | Modelle: ['llama3:8b'] |
| 3 | startup_checks.ollama_ok == True | ✅ | ollama_ok=True |
| 4 | status_bar_text() zeigt 'Ollama' (nicht 'KI: Fallback') | ✅ | Status Bar: 'GPU: n/a  \|  Ollama  \|  FFmpeg 6.1.1' |
| 5 | LocalAgentService erstellt | ✅ | Backend: Ollama, Modell: llama3:8b, URL: http://localhost:11434 |
| 6 | Backend ist Ollama (use_ollama=True) | ✅ | ollama_enabled=True |
| 7 | Modell ist llama3:8b | ✅ | model='llama3:8b' |
| 8 | Erwartete Init-Meldung: 'Agent bereit. Backend: Ollama' | ✅ | Backend-String: 'Ollama' |
| 9 | QSettings: ollama/enabled == True | ✅ | enabled=True |
| 10 | QSettings: ollama/url korrekt | ✅ | url=http://localhost:11434 |
| 11 | QSettings: ollama/model gesetzt | ✅ | model='llama3:8b' |
| 12 | Ollama Version erreichbar (0.18.3) | ✅ | version='0.18.3' |
| 13 | Modell-Liste enthaelt llama3:8b | ✅ | modelle=['llama3:8b'] |
| 14 | Chat-Antwort von llama3:8b erhalten | ✅ | Antwort: 'OK' |