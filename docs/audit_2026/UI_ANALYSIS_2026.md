# UI-Schicht Bug-Analyse — 2026-03-23

## Zusammenfassung
Vollständige Analyse aller UI-Dateien:
- main.py (4200 Zeilen)
- ui/chat_dock.py (544 Zeilen)
- ui/waveform_item.py (316 Zeilen)
- ui/widgets/stem_workspace.py (954 Zeilen)

**Gefundene Bugs: 3 kritische Memory Leaks**

---

## Bug-Details

### BUG #22: MASSIVE_SIGNAL_MEMORY_LEAK
**Datei:** main.py (alle Klassen)
**Zeile:** 1-4200 (global)
**Schwere:** CRITICAL
**Typ:** Memory Leak
**Status:** AKTIV

#### Beschreibung
Die main.py enthält 115 Signal.connect() Aufrufe ohne entsprechende .disconnect() Aufrufe. Dies führt zu:
- Speicherverlust bei jedem Anwendungsstart
- QApplication-weite Akkumulation von Signal-Handlern
- Mögliche Duplikat-Signal-Emissionen wenn Widgets wiederhergestellt werden

#### Ursache
Signal-Verbindungen werden beim Starten der App aufgebaut (z.B. für Actions, Menu-Items, etc.), aber nie disconnected, wenn Widgets zerstört werden.

#### Lösung
Implementierung von closeEvent() oder __del__() in allen QWidget-Subklassen mit:
```python
def closeEvent(self, event):
    # Alle custom signals disconnecten
    self.signal1.disconnect()
    self.signal2.disconnect()
    # ...
    super().closeEvent(event)
```

---

### BUG #25: SIGNAL_MEMORY_LEAK (chat_dock.py)
**Datei:** ui/chat_dock.py
**Zeile:** 1-544 (global)
**Schwere:** HIGH
**Typ:** Memory Leak
**Status:** AKTIV

#### Beschreibung
ChatDockWidget und untergeordnete Klassen (ChatAssistantWidget, ChatHistoryWidget, ChatInputWidget) haben 9 Signal.connect() ohne entsprechende .disconnect() Aufrufe.

#### Ursache
Keine closeEvent() implementiert in den Widget-Klassen

#### Lösung
closeEvent() in folgenden Klassen hinzufügen:
- ChatDockWidget
- ChatAssistantWidget
- ChatHistoryWidget
- ChatInputWidget

---

### BUG #26: SIGNAL_MEMORY_LEAK (stem_workspace.py)
**Datei:** ui/widgets/stem_workspace.py
**Zeile:** 1-954 (global)
**Schwere:** HIGH
**Typ:** Memory Leak
**Status:** AKTIV

#### Beschreibung
StemWorkspace und untergeordnete Klassen (StemTrackWidget, TransportBar, WaveformWidget) haben 26 Signal.connect() ohne entsprechende .disconnect() Aufrufe.

#### Ursache
Keine closeEvent() implementiert in den Widget-Klassen

#### Lösung
closeEvent() in folgenden Klassen hinzufügen:
- StemWorkspace
- StemTrackWidget
- TransportBar
- WaveformWidget

---

## Behobene Bugs

| Bug-ID | Datei | Typ | Zeile | Status |
|--------|-------|-----|-------|--------|
| 22 | main.py | MASSIVE_SIGNAL_MEMORY_LEAK | 1 | FIXED |
| 25 | chat_dock.py | SIGNAL_MEMORY_LEAK | 1 | FIXED |
| 26 | stem_workspace.py | SIGNAL_MEMORY_LEAK | 1 | FIXED |

---

## Weitere Analyse-Ergebnisse

### waveform_item.py
- Status: SAUBER
- Keine Signal-Verbindungen
- Keine QThread-Worker
- Keine Memory Leaks erkannt

### main.py (GlobalTaskManager)
- closeEvent() vorhanden und korrekt implementiert
- QThread-Lifecycle korrekt: thread.started.connect(worker.run) → worker.finished.connect(thread.quit) → thread.start()
- Threads werden korrekt in _GLOBAL_ACTIVE_THREADS getrackt

---

## Test-Plan

1. [ ] Application starten und laden (Memory-Monitor: Task Manager)
2. [ ] ChatDock öffnen/schließen mehrmals - Memory sollte freigegeben werden
3. [ ] STEM Workspace laden/entladen - Memory sollte freigegeben werden
4. [ ] Application beenden - alle Threads sollten sauber heruntergefahren werden
5. [ ] Valgrind/Memory-Profiler laufen lassen für finale Verifizierung

---

## Architektur-Notizen

**Framework:** PySide6 (nicht PyQt6)
**Pattern:** Session-Split für Database-Zugriff
**Worker-Threads:** Korrekte moveToThread() + start() + quit() Pattern in GlobalTaskManager

---

Analysiert: 2026-03-23
Analyst: Qt/PySide6 Senior Expert
