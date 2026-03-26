# Test-Report: PB_studio v0.4.0 — Vollständiger GUI-Test

**Datum:** 2026-03-24 12:07–12:35 Uhr  
**Projekt:** PB_studio_Rebuild  
**App:** `C:\Users\david\documents\app_projekte\PB_studio_Rebuild\main.py`  
**Dauer:** ~28 Minuten  
**Tester:** Claude GUI-Test-Agent (automatisiert)

---

## Zusammenfassung

| Status | Anzahl |
|--------|--------|
| ✅ Bestanden | 6 |
| ⚠️ Teilweise bestanden | 2 |
| ❌ Fehlgeschlagen | 0 |
| ⏭️ Übersprungen | 0 |

## Ergebnis: ⚠️ BEDINGT BESTANDEN

Alle Kernfunktionen sind grundsätzlich funktionsfähig. Es wurden 3 Bugs identifiziert, davon 1 kritischer (PyTorch fehlt → KI-Beat-Analyse nicht verfügbar) und 2 mittlere Bugs (pytest-Reste in Produktions-DB, Inspector-Buttons reagieren nicht ohne Chat-Dock).

---

## Test-Umgebung

| Parameter | Wert |
|-----------|------|
| App-Version | v0.4.0 — Director's Cockpit |
| Python | 3.11.x (Poetry venv `pb-studio-rebuild-340yKtNV-py3.11`) |
| GPU | NVIDIA GeForce GTX 1060 (6144 MB VRAM) — HARDWARE AKTIV |
| Betriebssystem | Windows 11 (Dual-Monitor, 3240×2020 Gesamtdesktop) |
| UI-Framework | PySide6 (DaVinci Resolve-Style) |
| Datenbank | SQLite (`pb_studio.db`) via SQLAlchemy ORM |
| Test-Daten Audio | `storage/stems/htdemucs/Crusty_Progressive Psy Set2/bass.wav` |
| Test-Daten Video | `C:\Users\david\Videos\PB_Studio_Export\proxies\proxy_20260201_1910_New_Video_gen_01kgd9sqc9ek492ht4pr0jm2pg.mp4` |

---

## Testschritte

### 1. App starten & Hauptfenster prüfen
- **Aktion:** App via Poetry-venv gestartet: `python main.py` im Verzeichnis `PB_studio_Rebuild`
- **Erwartet:** App öffnet, DaVinci-Style UI lädt, alle 5 Workspaces sichtbar
- **Ergebnis:** ✅ Bestanden
- **Details:**
  - App startet in < 5 Sekunden
  - Konsole zeigt: `[System] DaVinci-Style UI geladen`, `[System] Version 0.4.0`, `[GPU] HARDWARE AKTIV: NVIDIA GeForce GTX 1060 (6144 MB VRAM)`
  - Alle 5 Workspaces vorhanden: **MEDIA** | **EDIT** | **STEMS** | **CONVERT** | **DELIVER**
  - MEDIA Workspace als Standard aktiv
  - Video Pool und Audio Pool sichtbar
  - ⚠️ Beobachtung: DB enthält pytest-Reste aus vorherigen Tests (siehe BUG #1)

---

### 2. Audio importieren
- **Aktion:** MEDIA Workspace → "Audio importieren" → `bass.wav` ausgewählt
- **Erwartet:** Datei-Dialog öffnet, Datei wird importiert, Konsole zeigt Bestätigung
- **Ergebnis:** ✅ Bestanden
- **Details:**
  - Button "Audio importieren" (linke Sidebar) erfolgreich angeklickt
  - Datei-Browser-Dialog öffnet korrekt
  - `bass.wav` aus `storage/stems/htdemucs/Crusty_Progressive Psy Set2/` ausgewählt
  - Konsole: `[Ingest] Audio importiert: bass.wav`
  - Analyse-Pipeline startet sofort

---

### 3. Beat-Detection prüfen
- **Aktion:** Librosa-Grundanalyse + beat_this KI-Analyse werden nach Import automatisch gestartet
- **Erwartet:** BPM erkannt, Beat-Punkte berechnet
- **Ergebnis:** ⚠️ Teilweise bestanden
- **Details (Bestanden):**
  - Librosa-Analyse erfolgreich: `[Audio] Analyse fertig: 143.6 BPM | Dauer: 3745.54s | Beats: 8428 | Energie-Punkte: 3746`
  - Audio-Track erscheint in EDIT Workspace Inspector-Dropdown als `[1] Crusty_Progressive Psy Set2 (143.6 BPM)`
- **Details (Fehlgeschlagen):**
  - beat_this KI-Analyse schlägt fehl: `[Audio] Beat-Analyse übersprungen: name 'torch' is not defined`
  - **BUG #2**: PyTorch nicht importiert in `beat_analysis_service.py` → KI-Präzisionsanalyse nicht verfügbar
  - App fällt graceful auf Librosa zurück ✅

---

### 4. Video importieren
- **Aktion:** MEDIA Workspace → "Video importieren" → Proxy-MP4 Datei ausgewählt
- **Erwartet:** Video importiert, Edit-Proxy automatisch erstellt
- **Ergebnis:** ✅ Bestanden
- **Details:**
  - Button "Video importieren" erfolgreich angeklickt
  - `proxy_20260201_1910_New_Video_gen_01kgd9sqc9ek492ht4pr0jm2pg.mp4` importiert
  - Konsole: `[Proxy] Erstelle Edit-Proxy fuer '...'...`
  - Konsole: `[Proxy] Fertig: '...' → storage\proxies\..._edit_proxy.mp4`
  - Automatische Proxy-Erstellung via FFmpeg funktioniert korrekt

---

### 5. Video-Quelle im EDIT Inspector auswählen
- **Aktion:** EDIT Workspace wechseln → Inspector → Video-Dropdown öffnen → `[9] proxy_...` auswählen
- **Erwartet:** Video-Quelle setzt sich, Vorschau erscheint
- **Ergebnis:** ✅ Bestanden
- **Details:**
  - EDIT Workspace Tab erfolgreich aktiviert
  - Inspector zeigt QUELLEN-Bereich mit Audio-Combo und Video-Combo
  - Video-Dropdown expandiert und zeigt alle 9 verfügbaren Clips (inkl. pytest-Reste aus BUG #1)
  - `[9] proxy_20260201_1910_New_Video_gen_01kgd9sqc9ek492ht4pr0jm2pg` ausgewählt
  - Videovorschau erscheint sofort im Preview-Bereich (Frau mit lila Haaren, Fantasy-Szene)

---

### 6. Auto-Edit auslösen
- **Aktion:** Inspector-Buttons "Timeline generieren" und "Auto-Edit" angeklickt; alternativ via KI-Chat: "auto-edit starten"
- **Erwartet:** Auto-Edit Worker startet, Timeline wird befüllt
- **Ergebnis:** ⚠️ Teilweise bestanden
- **Details (Fehlgeschlagen — Inspector-Buttons):**
  - Klicks auf "Timeline generieren" (Koordinaten 2846,814) und "Auto-Edit" (2846,920) zeigten keinerlei Reaktion in der Konsole
  - Kein Konsolen-Output, kein Fortschrittsbalken, keine Fehlermeldung
  - **BUG #3**: Inspector-Buttons nicht erreichbar wenn KI-Chat-Dock geschlossen ist (Koordinaten-Verschiebung durch Dock-Layout-Änderung)
  - Workaround: Chat-Dock öffnen, dann funktionieren die Buttons mit den verschobenen Koordinaten (2505,814 und 2505,920)
- **Details (Bestanden — via KI-Chat):**
  - Chat-Befehl "auto-edit starten" erkannt und ausgeführt
  - Konsole: `[Auto-Edit] Phase 3 DJ-Pacing starte (Rate=4 Beats, Reaktivitaet=50%, Breakdown=halve, 9 Clips, 0 Anker)...`
  - Worker läuft in eigenem Thread, kein UI-Freeze
  - Konsole: `[OTIO] Timeline gespeichert: exports\auto_edit_phase3.otio`
  - Konsole: `[Auto-Edit] Phase 3 fertig: 6718 Segmente, OTIO Timeline generiert.`
  - Timeline-View zeigt V1 Track mit orangen Clip-Blöcken
  - Status-Leiste: `6718 Cuts | Beat:6718 | 1746s | 6718 Segmente`

---

### 7. Chat/KI-Dock testen
- **Aktion:** "KI Chat" Toggle aktivieren → Befehl "auto-edit starten" eingeben → Enter
- **Erwartet:** Chat-Dock öffnet, Befehl erkannt, KI antwortet
- **Ergebnis:** ✅ Bestanden
- **Details:**
  - KI-Chat-Toggle bei (3008,92) aktiviert — Dock erscheint sofort auf der rechten Seite
  - Chat-Dock zeigt Begrüßung: `Agent bereit. HARDWARE AKTIV: NVIDIA GeForce GTX 1060 (6144 MB VRAM) — Befehle: 'analysiere', 'schneide', 'gpu status'`
  - Eingabe "auto-edit starten" erkannt als Auto-Edit-Kommando (Keyword-Matching)
  - KI-Antwort: `Auto-Edit wird gestartet! Schneide Videos zum Beat mit den aktuellen DJ-Pacing-Einstellungen.`
  - Agent-Status-Anzeige: "Bereit"
  - Befehlsrouting funktioniert korrekt (LLM-freier Direktaufruf von `_auto_edit_to_beat()`)
  - Auto-Edit Worker erfolgreich gestartet (siehe Schritt 6)

---

### 8. App sauber schließen
- **Aktion:** `CloseMainWindow()` via PowerShell (nach Alt+F4 Versagen wegen Fokusverlust)
- **Erwartet:** App schließt ohne Crash, kein Daten-Verlust
- **Ergebnis:** ✅ Bestanden
- **Details:**
  - Alt+F4 hatte keinen Effekt (Fokus lag auf Chat-Eingabefeld)
  - `CloseMainWindow()` via PowerShell schloss die App sauber (Return: True)
  - Kein Crash-Dialog, keine Fehlermeldung
  - Python-Prozess beendet sich sauber
  - OTIO-Datei und DB-Einträge bleiben erhalten (Persistenz funktioniert)

---

## Bug-Liste

### BUG #1 — pytest-Reste in Produktions-DB
- **Schwere:** MEDIUM
- **Schritt:** 1 (App starten)
- **Beschreibung:** Die `pb_studio.db` enthält 5+ Einträge aus vorherigen pytest-Läufen. Die Pfade zeigen auf `C:\Users\david\AppData\Local\Temp\pytest-of-david\...` (nicht mehr existierende Temp-Dateien). Diese erscheinen im Video Pool (MEDIA Workspace) und im Video-Dropdown im EDIT Inspector.
- **Auswirkung:** Verwirrende UI, nicht funktionierende Clip-Einträge, verfälschte Clip-Anzahl bei Auto-Edit
- **Erwartetes Verhalten:** Unit-Tests sollten eine separate Test-Datenbank verwenden (Test-Isolation), nicht die Produktions-DB
- **Mögliche Ursache:** `conftest.py` oder pytest-Fixtures nutzen dieselbe `pb_studio.db` statt einer temporären In-Memory/Test-DB

### BUG #2 — PyTorch fehlt: beat_this KI-Beat-Analyse nicht verfügbar
- **Schwere:** MITTEL-KRITISCH
- **Schritt:** 3 (Beat-Detection)
- **Beschreibung:** Bei jedem Audio-Import erscheint die Fehlermeldung `[Audio] Beat-Analyse übersprungen: name 'torch' is not defined`. Die `beat_this`-Analyse (KI-basierte Präzisions-Beat-Erkennung) ist damit vollständig deaktiviert.
- **Auswirkung:** Nur Librosa-Grundanalyse verfügbar (weniger präzise, keine KI-Schlagzeug-Isolation)
- **Erwartetes Verhalten:** PyTorch korrekt in `beat_analysis_service.py` importieren; bei fehlendem PyTorch informative Fehlermeldung statt NameError
- **Mögliche Ursache:** `import torch` fehlt am Modulanfang; ODER torch ist nicht in Poetry-Abhängigkeiten installiert (`poetry add torch`)
- **Workaround:** Librosa-Analyse liefert BPM korrekt (143.6 BPM), App funktioniert weiter

### BUG #3 — Inspector-Buttons "Timeline generieren" und "Auto-Edit" ohne Reaktion
- **Schwere:** MEDIUM
- **Schritt:** 6 (Auto-Edit)
- **Beschreibung:** Die Schaltflächen "Timeline generieren" und "Auto-Edit" im EDIT-Inspector-Panel reagieren nicht auf Klicks, wenn das KI-Chat-Dock geschlossen ist. Nach Öffnen des Chat-Docks verschiebt sich das Inspector-Panel nach links (~341px), und die Buttons werden an neuen Koordinaten erreichbar.
- **Auswirkung:** Benutzer können Auto-Edit nicht direkt über Inspector-Buttons auslösen — sie müssen zuerst das Chat-Dock öffnen oder den Chat-Befehl verwenden
- **Erwartetes Verhalten:** Buttons sollten unabhängig vom Chat-Dock-Zustand funktionieren
- **Mögliche Ursache:** Layout-Problem: Inspector-Panel überlappt mit nicht-interaktivem Bereich des zweiten Monitors wenn Chat-Dock geschlossen; oder Inspector hat einen versteckten Scroll-Bereich der die Buttons verdeckt
- **Workaround:** Chat-Dock öffnen (KI Chat Toggle), dann Inspector-Buttons sind erreichbar; oder Chat-Befehl "auto-edit starten" verwenden

---

## Positive Beobachtungen

- **GPU-Integration**: NVIDIA GTX 1060 wird korrekt erkannt und aktiviert
- **Proxy-Erstellung**: Automatische FFmpeg Edit-Proxy-Erstellung funktioniert reibungslos
- **Threading**: Auto-Edit Worker läuft in eigenem Thread — keine UI-Freezes
- **OTIO-Export**: Timeline wird korrekt als OpenTimelineIO-Datei gespeichert (`exports\auto_edit_phase3.otio`)
- **Graceful Degradation**: Bei fehlendem PyTorch fällt die App auf Librosa zurück (kein Crash)
- **KI-Chat**: Keyword-Routing ohne LLM funktioniert schnell und zuverlässig
- **DJ-Pacing Engine**: Phase 3 Auto-Edit generiert 6718 Segmente aus 9 Clips — Algorithmus läuft fehlerfrei

---

## Empfehlungen

1. **Sofort**: `import torch` in `beat_analysis_service.py` prüfen und PyTorch in Poetry-Dependencies aufnehmen (`poetry add torch`)
2. **Kurzfristig**: pytest-Fixtures auf separate Test-DB umstellen (SQLite In-Memory oder temporäre Datei in `conftest.py`)
3. **Mittelfristig**: Inspector-Panel-Layout reparieren — sicherstellen, dass Buttons unabhängig vom Chat-Dock-Status erreichbar sind (evtl. Scroll-Bereich ausschalten oder Layout-Kopplung aufheben)
4. **Optional**: Alt+F4 / Schließen-Button Fokus-Handling verbessern (aktuell nicht aktiv wenn Chat-Eingabe fokussiert ist)

---

*Report erstellt von: Claude GUI-Test-Agent (automatisiert)*  
*Testzeit: 2026-03-24, 12:07–12:35 Uhr*
