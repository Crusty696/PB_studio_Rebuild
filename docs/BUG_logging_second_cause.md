# Bekannter Bug: Logging-Datei stoppt nach Worker-Thread-Start

## Status
**OFFEN** — Teil-Fix geliefert (2026-04-14), zweite Ursache dokumentiert.

## Symptom
`logs/pb_studio.log` hoert waehrend einer laufenden Session auf zu wachsen, obwohl die UI-Konsole (Widget `console_text`) weiter Nachrichten empfaengt.

## Was bereits gefixt wurde
`database/alembic/env.py:21` rief `fileConfig(...)` ohne Guard auf. Das entfernt die `RotatingFileHandler` aus `main.setup_logging()` und laesst den Root-Logger nur noch mit dem Console-Handler aus `alembic.ini` zurueck.

Fix: `if config.config_file_name is not None and not logging.getLogger().handlers:` — fileConfig nur noch, wenn Host-App noch kein Logging konfiguriert hat.

**Verifikation:** Boot-Logs gingen vorher bis zur `alembic.runtime.plugins.setup plugin`-Zeile, jetzt gehen sie vollstaendig durch (127 statt 98 Boot-Zeilen, bis `GPU erkannt: GeForce GTX 1060`).

## Zweite, noch offene Ursache

### Reproduktion
1. App starten, ein paar Minuten idle laufen lassen — Log schreibt normal.
2. Eine Analyse-Task triggern, die einen neuen Worker-Thread oeffnet (z.B. Flow 4 Szenen-Erkennung).
3. Nach einem `Qt C++ QObject::moveToThread ... Cannot move to target thread`-Warning verstummt `pb_studio.log` fuer den Rest der Session.
4. UI-Konsolen-Widget laeuft dabei weiter, weil `console_text.append(...)` direkt ans Widget geht, nicht durchs Python-Logging-System.

### Beispiel aus Flow 4 Retry-Run (2026-04-14 09:03)
```
2026-04-14 09:03:12 [INFO    ] services.video_service: --> Proxy-Pfad committed für clip_id=101
2026-04-14 09:03:12 [INFO    ] root: [TaskEngine] Gestartet: Medien-DB laden (task_id=task_4b06dde37e42)
2026-04-14 09:03:13 [WARNING ] database.session: [DB-Pool] Hohe Auslastung: 5/20 Connections checked out
2026-04-14 09:03:13 [WARNING ] database.session: [DB-Pool] Hohe Auslastung: 6/20 Connections checked out
2026-04-14 09:03:13 [WARNING ] root: [Qt C++] QObject::moveToThread: Current thread (0x1ec5c931770) ...
Cannot move to target thread (0x1ec18f17d5...
 (file: ?, line: 0)
<EOF>
```
Die App lief danach noch ~2 Minuten (Video-Analyse, Szenen-Erkennung). DB-Deltas wurden geschrieben. Nur das File-Log stand still.

### Hypothesen (nicht verifiziert)
1. **Logging-Lock bleibt im Worker-Thread gehalten.** Wenn ein Thread im `emit()` den internen `_lock` des `RotatingFileHandler` haelt und dann blockiert (z.B. auf DB-Pool-Connection), koennen andere Threads nicht mehr schreiben.
2. **Qt-Thread wechselt den File-Descriptor.** Nach `moveToThread` auf das Worker-QObject koennte ein Windows-File-Handle-Problem auftreten, wenn der RotatingFileHandler seinen Stream in einem nicht-main-Thread oeffnet.
3. **Buffer-Flush-Problem.** RotatingFileHandler nutzt implizit Python-File-Buffering; bei Thread-Wechsel kann ein flush ausstehen. Zu sehen: die letzte Zeile ist oft abgeschnitten mit halber Message.

### Naechster Untersuchungs-Schritt (wenn wir zurueckkommen)
- Monkey-Patch `RotatingFileHandler.emit` mit einem `print(f"emit from thread {threading.get_ident()}")` auf stderr → sieht man wann es aufhoert.
- Oder: einen zweiten, minimalistischen `FileHandler` ohne Rotation zum Vergleich an den Root-Logger haengen — wenn der weiter schreibt, ist es rotation-spezifisch.
- Oder: `QtThread.currentThread()` vs `threading.current_thread()` im Handler loggen, um Zusammenhang mit Qt-Thread zu verifizieren.

### Workaround bis zum Fix
- Smoke-Tests laufen unter 60s → nicht betroffen.
- Laengere Runs mit Analyse-Tasks: Crash-Erkennung zusaetzlich ueber UI-Konsolen-Inhalt (via `click-element --name-re "Konsole"` und `list-elements` auf das Text-Widget) oder ueber stderr-Capture des App-Subprozesses.
- Im Harness nicht blind `find-crash` vertrauen, wenn der letzte Log-Eintrag > 30s alt ist bei laufender App.

## Aufwandsschaetzung fuer den Fix
~2-4 Stunden: Hypothese 1 bestaetigen (Diagnose-Patch), dann entweder (a) `delay=True` + explizites `logging.shutdown()` im Exception-Pfad oder (b) einen Queue-basierten Handler (`logging.handlers.QueueHandler` + `QueueListener`) der das Schreiben aus dem Main-Thread macht und nicht aus Worker-Threads.

(b) waere die saubere Variante fuer eine Qt-App mit vielen Worker-Threads.
