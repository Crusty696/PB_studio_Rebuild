

**PB Studio v0.5.0**

Gemma 4 \+ Ollama — Arbeitsplan für den Teamleiter

*Vollständige Implementierungsanweisung inkl. main.py-Analyse*

Stand: April 2026  |  Basis: main.py v0.5.0 (702 Zeilen)

| Eigenschaft | Wert |
| :---- | :---- |
| Ziel | Gemma 4 E4B via Ollama unsichtbar in PB Studio integrieren |
| Betroffene Dateien | 7 bestehende \+ 2 neue Dateien |
| Neue Abhängigkeit | httpx ^0.27 (einzige äußere Abhängigkeit) |
| Neue Codezeilen | \~280–320 Zeilen (netto) |
| GPU | AMD RX 7800 XT (ROCm, HSA\_OVERRIDE\_GFX\_VERSION=11.0.0) |
| LLM ersetzt | Qwen 2.5 0.5B → Gemma 4 E4B (9,6 GB VRAM Q4\_K\_M) |
| User-sichtbare Änderungen | Status-Dot im Chat, Setup-Dialog einmalig |

# **Teil 1 — Analyse main.py: Alle Eingriffspunkte**

Die Datei main.py (702 Zeilen, v0.5.0) wurde vollständig analysiert. Nachfolgend alle Stellen, die angepasst, erweitert oder ersetzt werden müssen.

| Zeile(n) | Bereich | Befund | Aktion |
| :---- | :---- | :---- | :---- |
| 22 | Imports | from ui.theme import get\_stylesheet — OK | Keine Änderung |
| 26 | APP\_VERSION | 0.5.0 — Versionsnummer | Keine Änderung |
| 620–627 | SetupWizard | Existiert bereits: is\_setup\_complete() \+ SetupWizard aus ui/dialogs/setup\_wizard.py |  **Erweitern — Ollama-Setup einbauen** |
| 629–633 | Splash-Sequenz | show\_message('Initialisiere Datenbank...') — Ideal für Ollama-Start |  **Ollama.start() zwischen DB-Init und Window-Load** |
| 635–641 | startup\_checks | check\_system() prüft GPU/FFmpeg — kein Ollama-Check |  **Ollama-Status zu startup\_checks hinzufügen** |
| 655–665 | Console-Messages | Keine KI-Statusmeldung |  **Ollama/Gemma-Status in Konsole ausgeben** |
| 666 | Status Bar | Zeigt System-Status ohne AI-Info |  **AI-Ready-Info ergänzen** |
| 380–430 | closeEvent | ModelManager().unload() vorhanden — kein Ollama-Stop |  **OllamaService.get().stop() hinzufügen** |
| 480–530 | setup\_logging() | Vollständig — keine Änderung nötig | Keine Änderung |
| 540–570 | \_global\_exception\_hook | Crash-Dialog vorhanden — kein Ollama-Cleanup | Optional: Ollama-Log bei Crash miteinschliessen |
| 590–620 | main() Entry Point | QApplication, Splash, DB-Init, Translator — vollständig | Nur 3 neue Zeilen nötig |

# **Teil 2 — Neue Dateien (komplett neu erstellen)**

## **2.1  services/ollama\_service.py  — Das Herzstück**

Singleton-Service. Der einzige Ort in der gesamten Codebase der von Ollama weiß. Alle anderen Module rufen nur diesen Service auf.

| *Wichtig für den Teamleiter: Diese Datei muss zuerst fertig sein, bevor irgendeine andere Änderung implementiert wird. Alle anderen Aufgaben hängen davon ab.* |
| :---- |

| \# services/ollama\_service.py """ OllamaService — zentraler Lifecycle-Manager für Ollama \+ Gemma 4\. Alle Aufrufe aus dem Rest der App laufen ausschliesslich über diese Klasse. Kein anderes Modul importiert httpx oder kennt Port 11434\. """ import subprocess, os, asyncio, httpx, json, socket, time, logging from pathlib import Path from typing import Callable logger \= logging.getLogger(\_\_name\_\_) OLLAMA\_BASE  \= "http://localhost:11434" OLLAMA\_MODEL \= "gemma4:e4b" def \_find\_ollama\_bin() \-\> Path:     """Ollama-Binary suchen: PyInstaller-Bundle \> System-PATH \> Standard-Pfade."""     import sys     if getattr(sys, 'frozen', False):  \# PyInstaller-Bundle         base \= Path(sys.\_MEIPASS) / 'redist'         return base / ('ollama.exe' if os.name=='nt' else 'ollama')     for candidate in \[         Path.home() / '.local' / 'bin' / 'ollama',         Path('C:/Users') / os.getenv('USERNAME','') / 'AppData/Local/Programs/Ollama/ollama.exe',         Path('/usr/local/bin/ollama'),     \]:         if candidate.exists(): return candidate     return Path('ollama')  \# System-PATH-Fallback class OllamaService:     """Singleton. Verwaltet Ollama-Prozess und stellt chat/vision bereit."""     \_instance: 'OllamaService | None' \= None     \_process: subprocess.Popen | None \= None     @classmethod     def get(cls) \-\> 'OllamaService':         if cls.\_instance is None:             cls.\_instance \= cls()         return cls.\_instance     \# ── Lifecycle ─────────────────────────────────────────────     def start(self) \-\> None:         """Ollama als versteckter Subprocess starten (no-op falls schon läuft)."""         if self.\_is\_port\_open():             logger.info('Ollama: bereits aktiv auf Port 11434')             return         env \= os.environ.copy()         env\['HSA\_OVERRIDE\_GFX\_VERSION'\] \= '11.0.0'   \# AMD RX 7800 XT (gfx1101)         env\['OLLAMA\_KEEP\_ALIVE'\] \= '0'               \# VRAM sofort freigeben         flags \= 0x08000000 if os.name \== 'nt' else 0  \# CREATE\_NO\_WINDOW         try:             self.\_process \= subprocess.Popen(                 \[str(\_find\_ollama\_bin()), 'serve'\],                 stdout=subprocess.DEVNULL,                 stderr=subprocess.DEVNULL,                 env=env,                 creationflags=flags,             )             self.\_wait\_for\_port(timeout=30)             logger.info('Ollama gestartet (PID %s)', self.\_process.pid)         except FileNotFoundError:             logger.error('Ollama-Binary nicht gefunden: %s', \_find\_ollama\_bin())     def stop(self) \-\> None:         """Ollama-Prozess sauber beenden (aufgerufen aus closeEvent)."""         if self.\_process:             self.\_process.terminate()             try: self.\_process.wait(timeout=5)             except subprocess.TimeoutExpired: self.\_process.kill()             self.\_process \= None             logger.info('Ollama gestoppt.')     @property     def is\_ready(self) \-\> bool:         return self.\_is\_port\_open()     def \_is\_port\_open(self) \-\> bool:         try:             with socket.create\_connection(('localhost', 11434), timeout=1):                 return True         except OSError:             return False     def \_wait\_for\_port(self, timeout: int \= 30\) \-\> None:         deadline \= time.time() \+ timeout         while time.time() \< deadline:             if self.\_is\_port\_open(): return             time.sleep(0.5)         raise TimeoutError('Ollama hat Port 11434 nicht geöffnet.')     \# ── Model Management ──────────────────────────────────────     async def ensure\_model(         self,         progress\_cb: Callable\[\[str, float\], None\] | None \= None,     ) \-\> None:         """Modell vorhanden? Sonst mit Streaming-Fortschritt ziehen."""         async with httpx.AsyncClient(timeout=10) as client:             r \= await client.get(f'{OLLAMA\_BASE}/api/tags')             models \= \[m\['name'\] for m in r.json().get('models', \[\])\]             if any(OLLAMA\_MODEL in m for m in models):                 logger.info('Gemma 4 bereits vorhanden.')                 return         logger.info('Ziehe Gemma 4 E4B (\~9,6 GB)...')         async with httpx.AsyncClient(timeout=None) as client:             async with client.stream('POST',                 f'{OLLAMA\_BASE}/api/pull',                 json={'name': OLLAMA\_MODEL},             ) as resp:                 async for line in resp.aiter\_lines():                     if not line: continue                     data \= json.loads(line)                     total \= data.get('total', 1\) or 1                     done  \= data.get('completed', 0\)                     if progress\_cb:                         progress\_cb(data.get('status', ''), done / total)     \# ── Inference ─────────────────────────────────────────────     async def chat(self, messages: list\[dict\], temperature: float \= 0.7) \-\> str:         """Text-Chat für Multi-Agent-System (ersetzt Qwen)."""         async with httpx.AsyncClient(timeout=60) as client:             r \= await client.post(f'{OLLAMA\_BASE}/api/chat', json={                 'model': OLLAMA\_MODEL,                 'messages': messages,                 'stream': False,                 'options': {'temperature': temperature, 'num\_ctx': 4096},             })             return r.json()\['message'\]\['content'\]     async def vision(self, frame\_paths: list\[str\], prompt: str) \-\> dict:         """Multi-Frame-Vision für Scene-Captioning."""         import base64         images \= \[base64.b64encode(open(p,'rb').read()).decode() for p in frame\_paths\[:4\]\]         async with httpx.AsyncClient(timeout=120) as client:             r \= await client.post(f'{OLLAMA\_BASE}/api/generate', json={                 'model': OLLAMA\_MODEL,                 'prompt': prompt,                 'images': images,                 'stream': False,                 'format': 'json',                 'options': {'temperature': 0.1},             })             return json.loads(r.json()\['response'\]) |
| :---- |

*Neue Datei: services/ollama\_service.py (\~95 Zeilen)*

## **2.2  ui/widgets/ai\_status\_dot.py  — Minimaler UI-Indikator**

Kleiner grüner/gelber Punkt der im ChatDock erscheint. Keine Erwähnung von Ollama oder Gemma in der UI.

| \# ui/widgets/ai\_status\_dot.py from PySide6.QtWidgets import QLabel from PySide6.QtCore import QTimer from services.ollama\_service import OllamaService class AiStatusDot(QLabel):     """Kleiner Status-Indikator für den ChatDock-Header."""     def \_\_init\_\_(self, parent=None):         super().\_\_init\_\_("●", parent)         self.setFixedSize(16, 16\)         self.setToolTip('AI: bereit')         self.\_timer \= QTimer(self)         self.\_timer.timeout.connect(self.\_update)         self.\_timer.start(5000)  \# alle 5 Sek. prüfen         self.\_update()     def \_update(self):         ready \= OllamaService.get().is\_ready         self.setStyleSheet(             f'color: {"\#2ECC71" if ready else "\#F39C12"};'             f'font-size: 10px;'         )         self.setToolTip(f'AI: {"bereit" if ready else "wird geladen..."}') |
| :---- |

*Neue Datei: ui/widgets/ai\_status\_dot.py (\~25 Zeilen)*

# **Teil 3 — main.py: Konkrete Anpassungen (7 Eingriffe)**

| *Für den Teamleiter: Die nachfolgenden Eingriffe sind in Reihenfolge geordnet. Jeder Eingriff zeigt EXAKT welche Zeile ergänzt wird, was hinzugefügt wird und warum.* |
| :---- |

## **Eingriff 1 — Import hinzufügen (Zeile \~22)**

Nach dem letzten bestehenden Service-Import, vor der APP\_VERSION-Definition:

| \# \--- HINZUFÜGEN nach 'from ui.theme import get\_stylesheet' \--- from services.ollama\_service import OllamaService |
| :---- |

## **Eingriff 2 — closeEvent: Ollama stoppen (Zeile \~420)**

Im closeEvent, direkt nach dem bestehenden ModelManager().unload()-Block:

| \# Bestehender Code (Zeile \~416–420): try:     from services.model\_manager import ModelManager     ModelManager().unload() except (ImportError, RuntimeError, AttributeError) as exc:     logger.warning('closeEvent: failed to unload GPU models: %s', exc) \# \--- NEU: Direkt danach einfügen \--- try:     OllamaService.get().stop()     logger.info('closeEvent: Ollama gestoppt.') except Exception as exc:     logger.warning('closeEvent: Ollama-Stop fehlgeschlagen: %s', exc) |
| :---- |

## **Eingriff 3 — Splash: Ollama starten (Zeile \~629–633)**

Im main()-Block, zwischen 'check\_system()' und dem SetupWizard-Block. Der Ollama-Start läuft im Hintergrund während der Splash sichtbar ist:

| \# Bestehender Code (Zeile \~626): splash.show\_message('Initialisiere Datenbank...') QApplication.processEvents() \# \--- NEU: Nach der DB-Init-Meldung, vor from services.startup\_checks \--- splash.show\_message('Starte KI-Engine...') QApplication.processEvents() try:     OllamaService.get().start()  \# nicht-blockierend, Port-Check async     logger.info('Ollama-Start eingeleitet.') except Exception as exc:     logger.warning('Ollama-Start fehlgeschlagen (nicht-kritisch): %s', exc) QApplication.processEvents() |
| :---- |

## **Eingriff 4 — SetupWizard: Ollama-Setup integrieren (Zeile \~620–627)**

Der bestehende SetupWizard in ui/dialogs/setup\_wizard.py muss um einen Ollama-Schritt erweitert werden. Der Import bleibt identisch, aber die SetupWizard-Klasse bekommt einen neuen Step.

NICHT in main.py ändern, sondern in der Wizard-Klasse selbst:

| \# ui/dialogs/setup\_wizard.py  (bestehende Datei ERWEITERN) \# In der SetupWizard-Klasse: neuen Schritt 'AI Setup' hinzufügen. \# Dieser Schritt läuft nur einmalig (Flag: \~/.pbstudio/ai\_setup\_done) from PySide6.QtCore import QThread, Signal from services.ollama\_service import OllamaService import asyncio, json from pathlib import Path AI\_SETUP\_FLAG \= Path.home() / '.pbstudio' / 'ai\_setup\_done.json' def is\_ai\_setup\_complete() \-\> bool:     return AI\_SETUP\_FLAG.exists() class AiSetupWorker(QThread):     progress \= Signal(str, float)   \# (text, 0.0–1.0)     finished \= Signal()     error    \= Signal(str)     def run(self):         async def \_run():             svc \= OllamaService.get()             self.progress.emit('Starte KI-Engine...', 0.05)             svc.start()             await svc.ensure\_model(                 progress\_cb=lambda status, pct:                     self.progress.emit(                         f'Lade KI-Modell... {status}',                         0.1 \+ pct \* 0.85                     )             )             self.progress.emit('KI-Features bereit.', 1.0)             AI\_SETUP\_FLAG.parent.mkdir(parents=True, exist\_ok=True)             AI\_SETUP\_FLAG.write\_text(json.dumps({'model': 'gemma4:e4b'}))         asyncio.run(\_run())         self.finished.emit() \# SetupWizard-Klasse: is\_ai\_setup\_complete() in is\_setup\_complete() integrieren \# und AiSetupWorker als zusätzliche Page einbauen. |
| :---- |

## **Eingriff 5 — Console-Messages: KI-Status ausgeben (Zeile \~655–665)**

Im main()-Block, nach den bestehenden console\_text.append() Zeilen:

| \# Bestehende Zeilen (\~658–665): window.console\_text.append('\[System\] SQLite Datenbank (pb\_studio.db) erfolgreich initialisiert.') window.console\_text.append('\[System\] PB Studio Gold-Accent Theme aktiv — v0.5 Design.') window.console\_text.append(f'\[System\] Version {APP\_VERSION} — Workspace UI \+ KI-Pacing \+ Beat-Snap.') window.console\_text.append(f'\[System\] {\_sys\_status.status\_bar\_text()}') \# \--- NEU: Direkt danach \--- if OllamaService.get().is\_ready:     window.console\_text.append('\[KI\] AI-Engine aktiv. Modell: Gemma 4 E4B (lokal).')     logger.info('Ollama bereit beim App-Start.') else:     window.console\_text.append('\[KI\] AI-Engine wird im Hintergrund gestartet...')     logger.info('Ollama noch nicht bereit, lädt im Hintergrund.') |
| :---- |

## **Eingriff 6 — Status Bar: AI-Info einblenden (Zeile \~666)**

| \# Bestehende Zeile (\~666): window.status\_bar.showMessage(f'PB\_studio v{APP\_VERSION}  |  {\_sys\_status.status\_bar\_text()}') \# ERSETZEN DURCH: \_ai\_status \= '● AI ready' if OllamaService.get().is\_ready else '● AI loading...' window.status\_bar.showMessage(     f'PB\_studio v{APP\_VERSION}  |  {\_sys\_status.status\_bar\_text()}  |  {\_ai\_status}' ) |
| :---- |

## **Eingriff 7 — startup\_checks.py: Ollama-Status prüfen**

In services/startup\_checks.py (nicht main.py), die check\_system()-Funktion um Ollama-Check erweitern:

| \# services/startup\_checks.py  (bestehende Datei ERWEITERN) \# In check\_system() oder SystemStatus hinzufügen: from services.ollama\_service import OllamaService def check\_ollama() \-\> dict:     """Prüft ob Ollama erreichbar ist (non-blocking)."""     return {         'available': OllamaService.get().is\_ready,         'model': 'gemma4:e4b',     } \# check\_system() kann diesen Check aufrufen und in SystemStatus speichern. \# startup\_check\_dialog.py kann Ollama-Status optional anzeigen \# (nicht als Fehler — App läuft auch ohne Ollama, nur ohne AI-Features). |
| :---- |

# **Teil 4 — Bestehende Dateien anpassen (5 Dateien)**

## **4.1  agents/orchestrator\_agent.py**

Qwen 2.5 0.5B komplett ersetzen durch OllamaService. Alle spezialisierten Agents (pacing, audio, vision, editor) bleiben unberührt.

| \# agents/orchestrator\_agent.py  (QWEN ENTFERNEN, OLLAMA EINBAUEN) \# ENTFERNEN: alles rund um Qwen-Import und Qwen-Pipeline \# from transformers import AutoModelForCausalLM, AutoTokenizer  \# WEG \# model \= AutoModelForCausalLM.from\_pretrained('Qwen/...')      \# WEG \# ERSETZEN MIT: import asyncio from services.ollama\_service import OllamaService class OrchestratorAgent:     """Koordiniert alle Agents. LLM: Gemma 4 E4B via Ollama."""     SYSTEM\_PROMPT \= """Du bist der KI-Assistent von PB Studio, einem DJ-Video-Produktionstool. Beantworte Fragen präzise. Wenn du Pacing-Aufgaben bekommst, erkläre was du tun wirst. Antworte auf Deutsch."""     def \_\_init\_\_(self):         self.\_svc \= OllamaService.get()     def route(self, user\_message: str, context: dict | None \= None) \-\> str:         """Synchroner Wrapper für Qt-Threads."""         return asyncio.run(self.\_route\_async(user\_message, context or {}))     async def \_route\_async(self, user\_message: str, context: dict) \-\> str:         if not self.\_svc.is\_ready:             return 'KI-Engine wird noch gestartet. Bitte kurz warten.'         ctx\_str \= self.\_format\_context(context)         messages \= \[             {'role': 'system', 'content': self.SYSTEM\_PROMPT \+ ctx\_str},             {'role': 'user',   'content': user\_message},         \]         return await self.\_svc.chat(messages)     def \_format\_context(self, context: dict) \-\> str:         if not context: return ''         return f'\\n\\nAktueller Projektkontext: {context}' |
| :---- |

## **4.2  services/model\_manager.py**

Qwen-VRAM-Slot aus dem Singleton entfernen. Ollama verwaltet seinen eigenen VRAM ausserhalb des ModelManagers.

| \# services/model\_manager.py  (QWEN-SLOT ENTFERNEN) \# ENTFERNEN: Qwen-Registrierung aus dem VRAM-Slot-System \# Falls vorhanden, z.B.: \#   self.\_models\['qwen'\] \= ...      \# ENTFERNEN \#   self.load('qwen', ...)          \# ENTFERNEN \#   self.\_qwen\_model \= None         \# ENTFERNEN \# HINWEIS: OLLAMA\_KEEP\_ALIVE=0 ist in OllamaService.start() gesetzt. \# Ollama entlädt Gemma 4 automatisch nach jeder Inference. \# ModelManager muss NICHTS über Ollama wissen. \# OPTIONAL: Hilfsmethode für VRAM-Status-Abfrage def get\_available\_vram\_mb(self) \-\> float:     """Gibt verfügbares VRAM zurück (Ollama-Slot nicht eingerechnet)."""     \# bestehende GPU-Abfrage bleibt identisch     ... |
| :---- |

## **4.3  services/video\_analysis\_service.py**

SigLIP bleibt vollständig erhalten. Gemma 4 wird als 4\. Schritt NACH SigLIP ausgeführt.

| \# services/video\_analysis\_service.py  (ERWEITERN) import asyncio from services.ollama\_service import OllamaService CAPTION\_PROMPT \= """Analyze these video frames. Return JSON only: {   \\"description\\": \\"one concise sentence\\",   \\"mood\\": \\"energetic|calm|dramatic|ambient\\",   \\"motion\\": \\"static|slow|fast\\",   \\"tags\\": \[\\"3 keywords\\"\] }\\"\\"\\" class VideoAnalysisService:     \# ... bestehender Code vollständig beibehalten ...     def analyze\_scene\_with\_caption(self,                                     scene\_id: int,                                     keyframe\_paths: list\[str\]) \-\> None:         """Neu: Gemma-Caption NACH SigLIP-Embedding. Graceful degradation."""         svc \= OllamaService.get()         if not svc.is\_ready:             logger.debug('Ollama nicht bereit — Caption übersprungen für Scene %d', scene\_id)             return         try:             result \= asyncio.run(svc.vision(keyframe\_paths\[:3\], CAPTION\_PROMPT))             \# DB-Update mit den neuen Feldern             with DBSession(engine) as session:                 \# scene.ai\_caption, scene.ai\_mood, scene.ai\_tags setzen                 ...         except Exception as exc:             logger.warning('Scene-Caption fehlgeschlagen für %d: %s', scene\_id, exc) |
| :---- |

## **4.4  database.py**

Drei neue Spalten im Scene-Model. Migration-Script muss beim ersten Start automatisch ausgeführt werden.

| \# database.py  (ERWEITERN) \# Im VideoClip oder Scene-Model, 3 neue nullable Spalten: from sqlalchemy import Column, JSON, String class Scene(Base):  \# oder VideoClip, je nach bestehendem Schema     \# ... bestehende Felder unberührt ...     ai\_caption \= Column(JSON,   nullable=True)  \# {'description':..., 'mood':..., ...}     ai\_mood    \= Column(String, nullable=True)  \# 'energetic' | 'calm' | ...     ai\_tags    \= Column(JSON,   nullable=True)  \# \['tag1', 'tag2', ...\] \# In init\_db(): SQLite-Migration falls Spalten fehlen def \_migrate\_ai\_columns(conn):     for col, typedef in \[         ('ai\_caption', 'JSON'),         ('ai\_mood',    'TEXT'),         ('ai\_tags',    'JSON'),     \]:         try:             conn.execute(f'ALTER TABLE scenes ADD COLUMN {col} {typedef}')         except Exception:             pass  \# Spalte existiert bereits |
| :---- |

## **4.5  ui/chat\_dock.py**

Status-Dot im Header. Nur 5 Zeilen. Kein Hinweis auf Ollama in der UI.

| \# ui/chat\_dock.py  (MINIMALE ERWEITERUNG) from ui.widgets.ai\_status\_dot import AiStatusDot class ChatDock(QDockWidget):  \# oder wie die Klasse aktuell heisst     def \_\_init\_\_(self, parent=None):         super().\_\_init\_\_(parent)         \# ... bestehender Code ...         \# HINZUFÜGEN im Header-Layout:         self.\_ai\_dot \= AiStatusDot(self)         \# header\_layout.addWidget(self.\_ai\_dot)  \# ganz rechts im Header |
| :---- |

# **Teil 5 — Arbeitsplan für den Teamleiter**

| *Dieser Plan ist für ein Team von 2–4 Entwicklern ausgelegt. Die Aufgaben sind so strukturiert, dass sie parallel entwickelt werden können, mit klaren Abhängigkeiten und definierten Akzeptanzkriterien.* |
| :---- |

## **Sprint-Übersicht**

| Sprint | Dauer | Ziel | Abhängigkeit |
| :---- | :---- | :---- | :---- |
| Sprint 0 | 0,5 Tage | Vorbereitung: Ollama installieren, Modell testen, Repo branchen | Keine |
| Sprint 1 | 1 Tag | services/ollama\_service.py \+ Tests fertigstellen | Sprint 0 |
| Sprint 2 | 1 Tag | main.py Eingriffe 1–7 \+ closeEvent | Sprint 1 |
| Sprint 3 | 1–2 Tage | Qwen ersetzen (orchestrator), SetupWizard erweitern | Sprint 1 |
| Sprint 4 | 1 Tag | VideoAnalysis \+ DB-Migration \+ Status-Dot | Sprint 1 \+ 3 |
| Sprint 5 | 0,5 Tage | End-to-End-Test, Rollback-Plan prüfen | Sprint 2–4 |

## **Sprint 0 — Vorbereitung (0,5 Tage)**

Verantwortlich: Teamleiter persönlich

1. Git: Feature-Branch 'feature/gemma4-integration' erstellen

2. Ollama lokal installieren (Linux: curl \-fsSL https://ollama.com/install.sh | sh)

3. Manuell testen: ollama pull gemma4:e4b (einmalig, \~9,6 GB)

4. ROCm-Flag testen: HSA\_OVERRIDE\_GFX\_VERSION=11.0.0 ollama run gemma4:e4b

5. Prompt testen: 'Beschreibe diese Szene.' mit Testbild — JSON-Output prüfen

6. poetry add httpx — pyproject.toml committen

7. SETUP\_FLAG-Pfad festlegen: \~/.pbstudio/ai\_setup\_done.json — mit Team abstimmen

| *Abnahme Sprint 0: 'ollama run gemma4:e4b' auf AMD RX 7800 XT gibt eine Antwort auf Deutsch zurück.* |
| :---- |

## **Sprint 1 — OllamaService (1 Tag)**

Verantwortlich: Senior-Entwickler A

8. services/ollama\_service.py erstellen (exakt wie in Teil 2.1 spezifiziert)

9. \_find\_ollama\_bin(): alle 4 Pfad-Kandidaten testen (Windows \+ Linux)

10. Unit-Test schreiben: OllamaService.get().start() — Port-Open-Check nach 5 Sek.

11. Unit-Test: ensure\_model() — Mock des Ollama-Endpoints, Progress-Callback prüfen

12. Unit-Test: chat() — Mock-Response, Rückgabetyp str prüfen

13. Unit-Test: vision() — Base64-Encoding prüfen, JSON-Rückgabe validieren

14. is\_ready Property: True/False bei laufendem/gestopptem Ollama

15. Logging auf allen Methoden: INFO für Start/Stop, WARNING für Fehler

| *Kritisch: HSA\_OVERRIDE\_GFX\_VERSION=11.0.0 MUSS als Env-Var im Popen gesetzt sein. Ohne dieses Flag startet ROCm auf gfx1101 (RX 7800 XT) nicht korrekt.* |
| :---- |

| *Abnahme Sprint 1: Alle Unit-Tests grün. OllamaService.get().chat(\[{role:'user', content:'Hallo'}\]) gibt String zurück.* |
| :---- |

## **Sprint 2 — main.py Eingriffe (1 Tag)**

Verantwortlich: Entwickler B

16. Eingriff 1: Import hinzufügen (5 Minuten)

17. Eingriff 2: closeEvent — OllamaService.get().stop() nach ModelManager.unload()

18. Eingriff 3: Splash-Sequenz — OllamaService.get().start() nach DB-Init

19. Eingriff 5: Console-Message '\[KI\] AI-Engine aktiv'

20. Eingriff 6: Status-Bar mit AI-Status erweitern

21. Eingriff 7: services/startup\_checks.py um check\_ollama() erweitern

22. Manueller Test: App starten, Console-Log auf '\[KI\]'-Zeile prüfen

23. Manueller Test: App schliessen, 'Ollama gestoppt' in logs/pb\_studio.log prüfen

| *Abnahme Sprint 2: App startet und schliesst sauber. Keine Regression in bestehenden Features. Console zeigt '\[KI\]'-Zeile.* |
| :---- |

## **Sprint 3 — SetupWizard \+ Orchestrator (1–2 Tage)**

Verantwortlich: Entwickler C (SetupWizard) \+ Senior A (Orchestrator)

Aufgabe C: SetupWizard erweitern (ui/dialogs/setup\_wizard.py):

24. AiSetupWorker(QThread) implementieren (exakt wie in Teil 3 Eingriff 4\)

25. is\_ai\_setup\_complete() Funktion ergänzen

26. Bestehende is\_setup\_complete() aufrufen — AI-Setup als zusätzliche Bedingung

27. Progress-Dialog: Label zeigt 'KI-Modell wird geladen... X MB / Y MB'

28. Kein Hinweis auf 'Ollama' oder 'Gemma' in der UI (nur 'KI-Features' / 'AI Model')

29. Test: AI\_SETUP\_FLAG löschen, App neu starten — Dialog erscheint mit Fortschritt

Aufgabe A: Orchestrator-Agent:

30. OrchestratorAgent: Qwen-Code vollständig entfernen und OllamaService einbauen

31. Graceful Degradation: Bei is\_ready=False Fallback-Text zurückgeben

32. Alle pacing\_agent/audio\_agent/vision\_agent/editor\_agent: Keine Änderung nötig

33. Test: Chat-Dock 'Analysiere meinen DJ-Mix' — Gemma antwortet auf Deutsch

| *Abnahme Sprint 3: Erststart-Dialog zeigt Fortschritt, schliesst bei 100%. Chat-Dock liefert Antworten von Gemma 4 statt Qwen.* |
| :---- |

## **Sprint 4 — Video-Analysis \+ DB \+ Status-Dot (1 Tag)**

Verantwortlich: Entwickler B

34. database.py: ai\_caption, ai\_mood, ai\_tags Spalten \+ \_migrate\_ai\_columns() einbauen

35. init\_db(): Migration beim Start aufrufen (idempotent — keine Fehler bei existierenden Spalten)

36. video\_analysis\_service.py: analyze\_scene\_with\_caption() nach SigLIP-Analyse

37. Reihenfolge sicherstellen: SigLIP → RAFT → PySceneDetect → Gemma-Caption

38. Graceful Degradation: Bei Ollama-Fehler loggen und weiterlaufen (nicht blockieren)

39. ui/widgets/ai\_status\_dot.py erstellen (\~25 Zeilen)

40. ui/chat\_dock.py: AiStatusDot im Header platzieren

41. Test: Video analysieren — ai\_caption in pb\_studio.db prüfen (DB-Browser)

42. Test: Status-Dot grün wenn Ollama läuft, gelb wenn gestoppt

| *Abnahme Sprint 4: Nach Video-Analyse enthält die scenes-Tabelle ai\_caption-JSON. ChatDock zeigt grünen Dot.* |
| :---- |

## **Sprint 5 — End-to-End \+ Rollback (0,5 Tage)**

Verantwortlich: Teamleiter

43. Vollständiger Durchlauf: Import → Analyse → Auto-Edit → Chat → Export

44. VRAM-Monitor: Sicherstellen dass Gemma 4 VRAM nach Inference frei gibt (OLLAMA\_KEEP\_ALIVE=0)

45. Gleichzeitigkeits-Test: Demucs-Job starten, dann Chat-Nachricht — kein VRAM-Crash

46. Logging prüfen: logs/pb\_studio.log auf ERROR/WARNING durchsuchen

47. Rollback-Plan dokumentieren: git revert auf feature-branch, Qwen-Imports reaktivieren

48. PR in main-Branch: Code-Review mit allen Entwicklern

| *Abnahme Sprint 5: Kein bestehender Feature-Regression. VRAM-Konflikt ausgeschlossen. PR freigegeben.* |
| :---- |

# **Teil 6 — Gesamtübersicht: Alle Dateien**

| Datei | Status | Aktion | Sprint | Entwickler |
| :---- | :---- | :---- | :---- | :---- |
| services/ollama\_service.py | NEU | Erstellen (\~95 Zeilen) | 1 | Senior A |
| ui/widgets/ai\_status\_dot.py | NEU | Erstellen (\~25 Zeilen) | 4 | Dev B |
| main.py | ANPASSEN | 7 Eingriffe (Imports, closeEvent, Splash, Console, StatusBar) | 2 | Dev B |
| ui/dialogs/setup\_wizard.py | ERWEITERN | AiSetupWorker \+ Flag-Logik | 3 | Dev C |
| agents/orchestrator\_agent.py | ERSETZEN | Qwen raus, OllamaService rein | 3 | Senior A |
| services/model\_manager.py | BEREINIGEN | Qwen-VRAM-Slot entfernen | 3 | Senior A |
| services/video\_analysis\_service.py | ERWEITERN | analyze\_scene\_with\_caption() | 4 | Dev B |
| database.py | ERWEITERN | 3 neue Spalten \+ Migration | 4 | Dev B |
| ui/chat\_dock.py | MINIMAL | AiStatusDot einhängen (5 Zeilen) | 4 | Dev B |
| services/startup\_checks.py | ERWEITERN | check\_ollama() hinzufügen | 2 | Dev B |
| pyproject.toml | ABHÄNGIGKEIT | httpx ^0.27 hinzufügen | 0 | Teamleiter |

## **Kritische Regeln für das gesamte Team**

* Kein anderes Modul ausser ollama\_service.py importiert httpx oder kennt Port 11434

* Kein anderes Modul ausser ollama\_service.py weiss, dass Gemma 4 oder Ollama existiert

* Alle Ollama-Aufrufe haben Graceful Degradation: bei is\_ready=False Fallback, kein Crash

* In der PySide6-UI: keine Erwähnung von 'Ollama', 'Gemma' oder 'LLM'. Nur 'KI-Features' / 'AI'

* OLLAMA\_KEEP\_ALIVE=0 niemals ändern — verhindert VRAM-Kollision mit Demucs/RAFT/SigLIP

* OllamaService.get().stop() MUSS im closeEvent nach ModelManager.unload() stehen

* Qwen-Code vollständig entfernen (nicht nur auskommentieren) — spart \~240 MB VRAM

| *Gesamtaufwand: \~5 Entwickler-Tage. \~320 neue Codezeilen verteilt auf 10 Dateien. Kein bestehender Feature wird entfernt. Vollständiger Rollback möglich via git revert.* |
| :---- |

PB Studio v0.5.0 — Gemma 4 Arbeitsplan | Erstellt April 2026 | Vertraulich