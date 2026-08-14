# W3 Audio V2 — Live-Session 2026-08-14

Status: W3 grösstenteils belegt. B-820 gefunden, gefixt und live bestätigt.
Offen bleibt nur der Teilschritt „fehlendes Stem" (nicht auslösbar, siehe Nachtrag).
Runs: `20260814T0405-w3-audio-v2` (Run 1) und `20260814T0530-w3-b820-verify` (Run 2)
HEAD Run 1: `22f96b8` · Baseline Run 2: `3507828` plus B-820-Fix

> Der Abschnitt bis zur Trennlinie beschreibt Run 1 und den Stand **vor** dem
> Fix. Der Nachtrag am Ende hält Fix und Run 2 fest.

## Scope

Isolierter Root `C:\Users\David_Lochmann\AppData\Local\PBStudioW3AudioV2\` mit
eigenem `AppData\Roaming`, `AppData\Local`, Projekt und Manifest-Ordner.
Projekt `w3-audio-v2` ist eine 245-MB-Kopie von `PBStudioW3Current\W3-runde4-s1`;
das Original blieb unangetastet, damit die bisherige W3-Teilevidenz erhalten
bleibt. In der Kopie-DB war genau ein absoluter Altpfad (`projects.path`), der
auf den neuen Ort umgeschrieben wurde. Medienpfade zeigen auf read-only Quellen.

Start ausschließlich über
`tests/gui_harness.py start --force --freeze-probe --stability-project <projekt>`.

## Ergebnis pro Teilschritt

| Teilschritt | Ergebnis |
|---|---|
| App-Start / Systemcheck | **pass** |
| Projekt-Load im isolierten Scope | **pass** |
| Fehlende Audio-Quelldatei | **pass** (Fehlerpfad korrekt) |
| Audio-V2-Cancel — Mechanik | **pass** |
| Audio-V2-Cancel — persistierter Status | **fail** → B-820 |
| Retry | nicht ausgeführt (durch B-820 gestoppt) |
| Neustartvergleich | nicht ausgeführt |
| Fehlendes Stem | nicht ausgeführt |
| Shutdown / Hostschutz | **pass** |

## B-758 auf Current HEAD live bestätigt

App-Log 04:17:20:

```
PyTorch CUDA compiled: 11.3, Treiber: 546.33
PyTorch CUDA available check: True
GPU erkannt: NVIDIA GeForce GTX 1060 (6143 MB VRAM)
Startup checks completed: GPU: NVIDIA GeForce GTX 1060 6GB  |  Ollama  |  FFmpeg 6.1.1
```

Kein `CUDA GPU FAIL`, kein `NVENC Encode FAIL`, kein Modal. Statusleiste
`System bereit | GPU: NVIDIA GeForce GTX 1060 6GB | Ollama | FFmpeg 6.1.1 | AI ready`.

Das ist der erste B-758-Livebeweis aus dieser Session selbst; die früheren
Belege stammten aus der Codex-Session vom 2026-08-12 und wurden hier nicht
nachgestellt. `fixed` bleibt Userrecht.

## Fehlende Audio-Quelldatei (Track 3)

Der DB-Eintrag `lv3_maceo_45s_v2` (id=3) zeigt auf
`tests/qa_material/lv3_maceo_45s_v2.wav` — diese Datei existiert nicht mehr.
Testdatenlage, kein Produktdefekt.

Das App-Verhalten war korrekt:

```
[StemSeparator] Modell 'htdemucs' geladen auf cuda:0
B-597 GPU_EXECUTION_LOCK released reason=audio_v2.stem_gen held_ms=1560.0
B-597 audio_stage failed track=3 stage=stem_gen ... Error opening input: No such file or directory
[TaskEngine] Worker-Fehler 'AudioPipelineV2' (task_id=task_85de27a30ee3)
```

GPU-Lock sauber freigegeben, Fehler ehrlich propagiert, kein Crash, kein
falsch gemeldeter Erfolg.

## Cancel — was funktioniert

Track 2 `lv3_maceo_45s`, `Audio komplett analysieren` 05:03:18,
Cancel-Klick 05:03:25.

- `stem_gen` erkannte vorhandene Stems und reuste sie (`duration_ms=332.1`,
  `result_keys=['reused','stem_paths']`).
- `GPU_EXECUTION_LOCK released reason=audio_v2.beat_grid held_ms=10915.0` —
  kein Lock-Leak.
- `AudioPipelineV2Worker abgebrochen` als INFO, nicht als ERROR.
- B-724-Vertrag griff: `Task task_656c1dc577f8 ist bereits 'cancelled' —
  spaeter Worker-Abbruch wird nicht als Fehler uebernommen`.
- `mark_cancelled()` schrieb den richtigen Zustand.
- Latenz Cancel-Klick bis Stage-Ende rund 6 s.

## Cancel — was bricht (B-820)

Dieselbe Sekunde, direkt hintereinander:

```
05:03:31 Analysis cancelled: audio/2/bpm_detection
05:03:31 Reconciled status='done' for audio/2/bpm_detection from DB evidence
```

Persistierter Endzustand `analysis_status` id=158: `status='done'`,
`value_summary='{"bpm": 130.4, "beats": 99}'`, `completed_at` gesetzt,
`error_message=None`.

Root Cause: `services/analysis_status_service.py` `_ensure_status_done()`
Zeile 750-754 überschreibt jeden Nicht-`done`-Status auf `done` und löscht
`error_message`, sobald das Artefakt existiert. Aufruf aus
`_infer_audio_status()` Zeile 643. Die Stage persistiert ihr Beatgrid vor dem
Cancel-Check, also liegt „DB evidence" vor und der nächste Status-Refresh macht
den Cancel rückgängig.

Damit ist der B-751-Cancelvertrag nicht dauerhaft. Details in
`wiki/bugs/B-820-cancel-status-wird-von-status-reconciler-auf-done-ueberschrieben.md`.

Erste-Fehler-Regel: W3 stoppt hier. Kein Code angefasst, kein Fix vorgeschlagen.

## Shutdown und Hostschutz

`gui_harness.py kill` → `method: graceful`. Shutdown-Log vollständig
(Ollama gestoppt, EmbeddingJobQueue stopped, VRAM-Hygiene, ModelManager.unload
synchron, CUDA synchronize + empty_cache, MemoryUpdater-Flush). Kein Fatal.

Prozessgate: 0 Python-Reste. Das laufende `ollama.exe` PID 1592 ist identisch
mit dem Vorbestand von vor dem Run.

Pre/Post-Manifest beide `verdict: pass`. Alle fünf Host-/Repo-DBs
byte-identisch. Verändert wurden nur die isolierte Projekt-DB
(1314816 → 1380352 B) und drei neu erzeugte isolierte
`AppData\Roaming\PB_Studio\brain_v3\`-DBs.

## Umgebungsbefund

Das conda-env `pb-studio` hatte keine GUI-Automations-Deps: `pygetwindow`,
`pywinauto`, `pyautogui`, `mss` fehlten alle. Sie stehen in keiner
Requirements-Datei und lebten nur ad-hoc im entfernten `.venv310`.

Auf Userentscheidung 2026-08-14 nachinstalliert. Gegenprobe danach: torch
1.12.1+cu113, torchvision 0.13.1+cu113, torchaudio 0.12.1+cu113, numpy 1.26.4,
pillow 11.3.0, PySide6 6.7.3 unverändert, `torch.cuda.is_available() = True`.

Ein Eintrag in `environment.yml` / `requirements-py310-cu113.txt` wurde
bewusst **nicht** vorgenommen — dafür fehlt die explizite Userfreigabe.
Solange das offen ist, fehlen die Deps nach dem nächsten Env-Neuaufbau wieder.

Zwei Nebenbefunde ohne eigenes Bugfile:

1. Ein App-Start aus Git-Bash scheitert reproduzierbar mit
   `ImportError: DLL load failed while importing QtWidgets` und
   `DLL load failed while importing _ctypes`, weil die conda-DLL-Pfade im
   Git-Bash-PATH fehlen. Aus PowerShell funktioniert derselbe Aufruf.
   Kein Produktdefekt.
2. `gui_harness.py start --force` wirft im Readerthread
   `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`. Die App
   startet trotzdem.

## Evidenz

- Screenshots `tests/qa_artifacts/w3_*_20260814_*.png`
- Manifeste unter
  `C:\Users\David_Lochmann\AppData\Local\PBStudioW3AudioV2\PBStudioStability\`
  (`-pre` und `-post`)
- App-Log `logs/pb_studio.log`, 04:17:13 bis 05:07:24

## Nächste einzige Task

`ROOT-CAUSE / B-820 Cancel-Status wird vom Status-Reconciler auf done
überschrieben`. Danach W3 fortsetzen mit Retry, Neustartvergleich und
fehlendem Stem.

---

# Nachtrag — B-820-Fix und zweiter Live-Run

Run: `20260814T0530-w3-b820-verify`
Codestand: B-820-Fix (Commit siehe unten), Baseline `3507828`

## B-820 gefixt (TDD RED → GREEN)

`services/analysis_status_service.py`:

- Neue Modulkonstante `CANCELLED_MARKER = "cancelled"`; `mark_cancelled()`
  nutzt sie statt String-Literalen.
- `_ensure_status_done()` bekommt einen vorgelagerten Zweig, der einen
  bewussten User-Cancel (`status='error'` + `error_message=CANCELLED_MARKER`)
  unangetastet lässt.
- Der irreführende Docstring wurde korrigiert.
- Der B-461-Pfad bleibt erhalten: ein echter Fehler wird weiterhin auf `done`
  gehoben, wenn der Wert nachweislich in der DB steht.

Tests: `tests/test_services/test_b820_cancel_survives_reconcile.py`, vier
Verträge. **RED `3 failed, 1 passed`** — der Video-Test schlug ebenfalls fehl
und bestätigte damit, dass B-820 Audio *und* Video betraf.
**GREEN 16 passed.** Breitere Gegenprobe
`-k "cancel or b724 or b751 or b753 or b754 or b755 or b756 or analysis_status"`:
**125 passed**. `py_compile` und Ruff grün.

## Ergebnis pro Teilschritt (Run 2)

| Teilschritt | Ergebnis |
|---|---|
| B-820-Fix live | **pass** |
| Retry nach Cancel | **pass** |
| Neustartvergleich | **pass** |
| Fehlendes Stem | **nicht auslösbar** → offen |
| Hostschutz | **pass** |

### B-820 live

```
05:34:27 Analysis started: audio/2/bpm_detection
05:34:37 GPU-ZWANG: beat_this wird auf CUDA geladen (NVIDIA GeForce GTX 1060)
05:34:50 B-597 GPU_EXECUTION_LOCK released reason=audio_v2.beat_grid held_ms=22524.9
05:34:50 Analysis cancelled: audio/2/bpm_detection
```

DB danach: `status='error'`, `error_message='cancelled'`, `completed_at=None`.
Kein `Reconciled status='done'` mehr. Vor dem Fix stand hier `done`.

Nebenbeobachtung, nicht mitgefixt: um 05:34:28, also während der Schritt noch
lief (`running`), hob der Reconciler ihn einmal auf `done`, weil das alte
Beatgrid noch dalag. Das ist nicht der Cancel-Fall.

### Retry

Nach erneuter Track-Selektion lief die komplette Audio-V2-Pipeline durch —
10 Schritte alle `done` (`stem_separation`, `bpm_detection`, `onset_detection`,
`key_detection`, `structure_detection`, `lufs_analysis`, `spectral_analysis`,
`mood_genre_classify`, `waveform_analysis`, `av_pacing_curves`).
`bpm_detection` wechselte korrekt von `cancelled` auf `done`.

### Neustartvergleich

App graceful beendet, neu gestartet, Projekt erneut geöffnet. Alle 10 Schritte
standen unverändert auf `done`. Kein Verlust, kein Reset, kein wieder
auftauchender Cancel.

### Fehlendes Stem — offen

`vocals.wav` wurde im isolierten Stems-Ordner entfernt (mit Backup). Der
`Stems`-Button reagierte auf drei Klickversuche nicht: keine Logzeile, keine
Regenerierung. Wahrscheinlichste Erklärung ist, dass die Klicks das Fenster
nicht erreichten — `gui_harness` klickt per `click_input` an Bildschirm-
koordinaten, ein fremdes Fenster lag deckungsgleich über der App und `focus`
schlug zuletzt mit `focus failed: Error code from Windows: 0` fehl.
**Nicht bewiesen.** Der Teilschritt bleibt offen.

`vocals.wav` wurde aus dem Backup wiederhergestellt. Die Host-Stems blieben
durchgehend unberührt.

## Zwei neue Bugs

- **B-821** (medium): Analyse-Button wirkt nach einem Cancel tot und meldet
  nichts ins Logfile. Verdacht: `_v2_finalize()` → `_refresh_media_table_debounced()`
  verwirft die Selektion, `_analyze_selected_audio()` bricht dann still ab und
  schreibt den Hinweis nur nach `console_text`. Hypothese, im Code nicht bewiesen.
- **B-822** (high): `audio_tracks.stem_*_path` zeigte im isolierten Projekt auf
  `Documents\PB_studio_Rebuild\projects\runde4-s1\...`, also aus dem Projekt
  heraus in einen Host-Ordner. Lesezugriff belegt, Schreibzugriff nicht
  provoziert. Für den Test wurden die Spalten in der isolierten Kopie auf den
  projektinternen Ordner umgeschrieben.

## Hostschutz Run 2

Pre- und Post-Manifest beide `pass`. Verändert wurde ausschließlich die
isolierte Projekt-DB (1380352 → 1445888 B). Alle fünf Host-/Repo-DBs
byte-identisch. Graceful Shutdown, 0 Python-Prozessreste, `ollama.exe` PID 1592
weiterhin der Vorbestand von vor der Session.

## Umgebung nachgezogen

Die vier GUI-Automations-Deps sind jetzt in `requirements-py310-cu113.txt`
gepinnt (`pywinauto`, `pyautogui`, `pygetwindow`, `mss`), mit Begründung im
Kommentar. `environment.yml` zieht die Datei bereits als pip-Sektion und
braucht keine Änderung.

## Nächste einzige Task

`ROOT-CAUSE / B-821 Analyse-Button wirkt nach Cancel tot` — er blockiert den
offenen W3-Teilschritt „fehlendes Stem". Danach B-822 und der Rest von W3.
