# PB Studio — Live-Verify Handover (autonom)

> **Zweck:** Anleitung für einen autonomen Coworker-Agenten (Claude Desktop mit
> Computer-Use / Terminal-Zugriff auf **diese** Maschine), die offenen
> `code-fix-pending-live-verification`-Bugs **ohne den User** real in der App zu
> verifizieren.
>
> **Stand:** 2026-05-29 · Branch `feat/video-pipeline-engine-2026-05-19` ·
> Maschine: Surface Book 2, GTX 1060, Windows 11.

---

## 0. Wichtigste Regel — Ehrlichkeit

- **`status: fixed` setzt NUR der menschliche User.** Der Coworker setzt **niemals**
  `fixed`. Erlaubte Verdikte des Coworkers: `PASS (agent-verify)`, `FAIL`,
  `INCONCLUSIVE`, `BLOCKED`.
- **Code-Edit ≠ verifiziert.** Nur echter App-Workflow + Log-/DB-/Screenshot-Beleg zählt.
- **Smoke-Test grün ≠ verifiziert.** Reale Aktion in der laufenden GUI ist Pflicht.
- Bei Unsicherheit: `INCONCLUSIVE` + Grund. Nicht schönreden.
- **Kein Code ändern.** Dies ist reine Verifikation. Findet der Coworker einen neuen
  Bug → als neuen `B-XXX` dokumentieren, **nicht** selbst fixen.

---

## 1. Preflight (einmalig vor allen Suites)

### 1.1 Umgebung
```powershell
# conda-Python der App (NICHT system-python, NICHT .venv310 — existiert nicht):
$PY = "C:/Users/David Lochmann/miniconda3/envs/pb-studio/python.exe"
& $PY -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
# ERWARTET: torch 1.12.1+cu113 cuda True NVIDIA GeForce GTX 1060
```
Wenn `cuda False` → **STOP**, GPU-Preflight (1.2) klären, sonst laufen GPU-Tests sinnlos.

### 1.2 GPU-Preflight
```powershell
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
# ERWARTET: NVIDIA GeForce GTX 1060, 546.33, 6144 MiB
```
GPU-Hartregel: ausschließlich GTX 1060 / CUDA 11.3 / `h264_nvenc`/`hevc_nvenc`. Kein
anderer GPU-Backend. dGPU kann am SB2 transient verschwinden (Code 45/47) → siehe Suite A.

### 1.3 Pfade
| Was | Pfad |
|---|---|
| Repo-Root | `C:\Users\David Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild` |
| App-Entry | `main.py` (`& $PY main.py`) |
| App-Log | `logs\pb_studio.log` (RotatingFileHandler, 5 MB ×3) |
| Haupt-DB | `pb_studio.db` (SQLite, im Repo-Root) |
| Brain-DB | `brain_v3\state.db` |
| Vektor-DB | `data\vector\embeddings.db` |
| GUI-Harness | `tests\gui_harness.py` (env `PB_PYTHON` = conda-python setzen) |
| Verdikt-Reports | `outputs\VERIFY_<datum>\` (anlegen) |

### 1.4 Testdaten (Standard)
| Typ | Pfad |
|---|---|
| Audio (DJ-Mix, 555 MB) | `C:\Users\David Lochmann\Music\Audio\Psy-Set\Progressive_Psy_Summer_Dream.wav` |
| Videos (200 Clips) | `C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur` |

> Für schnelle Läufe: ersten **3–5 min** Audio-Ausschnitt + ~10–20 Videos nutzen.

### 1.5 App starten + Log live mitlesen
```powershell
# App im Hintergrund starten, stdout/stderr fangen:
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
Start-Process -FilePath $PY -ArgumentList "main.py" `
  -RedirectStandardOutput "outputs\verify_app_$ts.out.log" `
  -RedirectStandardError  "outputs\verify_app_$ts.err.log" -PassThru
# Log live taillen (eigene Konsole):
Get-Content "logs\pb_studio.log" -Wait -Tail 30
```
App sauber schließen: GUI-Fenster zu, oder
`& $PY tests\gui_harness.py kill --grace-sec 25`.

### 1.6 Verdikt-Report anlegen
Lege `outputs\VERIFY_<datum>\verdicts.md` an. Pro Bug eine Zeile (Template in §9).
**Inkrementell schreiben** — nach JEDEM Bug sofort speichern. (Auf dieser Maschine kann
die dGPU mitten im Lauf abklappen und alles schließen → ein verlorener In-Memory-Stand
ist sonst weg. Report-on-disk überlebt das.)

---

## 2. Bug-Übersicht (was zu verifizieren ist)

Quelle: `docs/superpowers/ACTIVE_PLAN.md` + Vault `C:\Brain-Bug\projects\pb-studio\wiki\bugs\`.
~94 Bugs `code-fix-pending-live-verification`. Gruppiert in **Suites A–G** nach App-Workflow,
damit ein End-to-End-Durchlauf je Suite viele Bugs auf einmal abdeckt.

---

## SUITE A — GPU-Stabilität (B-433, B-265, B-281)

### A1 · B-433 — dGPU-Flap bei Stromquellen-Wechsel → CUDA-Reprobe
**Code:** `main.py:1426` Power-Filter behandelt `WM_POWERBROADCAST` wParam `0x000A`.
**Runtime-Wiring schon belegt** (2026-05-29, synthetische 0x000A → Log-Marker). **Offen:**
echte dGPU-Verlust-Recovery.
- **Schritt:** App starten, langen GPU-Workload anstoßen (Audio-Analyse + Video-Proxy-Gen
  auf Testdaten). Während Last läuft, einen echten Stromquellen-Wechsel provozieren ist
  **nicht zuverlässig erzwingbar** → daher: Lauf laufen lassen, im Log beobachten.
- **PASS-Kriterium (echte Recovery):** bei realem Flap erscheint
  `B-433: Power-Source-Change (wParam=0x000A)` **und** danach
  `B-218: CUDA-Context verloren ... Fallback auf CPU` → App läuft auf CPU weiter, **kein Crash**.
- **Beleg:** `Select-String "B-433|CUDA-Context verloren|Fallback auf CPU" logs\pb_studio.log`
- **Wenn kein Flap im Lauf:** `INCONCLUSIVE (kein Flap aufgetreten)` — Wiring ist separat bewiesen.

### A2 · B-265 — GTX 1060 CUDA-Verfügbarkeit
**Kein Code-Bug** (SB2-Hardware). Verify = Preflight.
- **PASS:** §1.1 + §1.2 grün **und** App-Log zeigt `GPU-Info Cache: NVIDIA GeForce GTX 1060 | CUDA 11.3`.
- **FAIL/BLOCKED:** Log zeigt `Keine CUDA-GPU` / `held_for_eject` (Code 47) → dGPU abgeklappt,
  User-Aktion nötig (re-attach/Treiber-Reset). Notieren, nicht fixen.

### A3 · B-281 — NVENC-Proxy fällt auf CPU
**Kein Code-Bug.** Verify = NVENC-1-Frame-Test gegen `bin\ffmpeg.exe`.
```powershell
$bin = "bin\ffmpeg.exe"
& $bin -hide_banner -version | Select-Object -First 1   # ERWARTET: ffmpeg 6.1.1
& $bin -hide_banner -loglevel error -f lavfi -i color=black:s=256x256:d=1 -frames:v 1 -c:v h264_nvenc -y "$env:TEMP\t.mp4"; "h264_nvenc exit=$LASTEXITCODE"
& $bin -hide_banner -loglevel error -f lavfi -i color=black:s=256x256:d=1 -frames:v 1 -c:v hevc_nvenc -y "$env:TEMP\t2.mp4"; "hevc_nvenc exit=$LASTEXITCODE"
```
- **PASS:** beide exit 0. (Zusätzlich real: App → Ordner importieren → Proxy-Gen → Log darf
  **nicht** `Fallback auf libx264 (CPU)` zeigen.)
- **FAIL:** App-Log zeigt `NVENC nicht verfuegbar ... Fallback auf libx264` trotz exit-0-Test
  → `bin\ffmpeg.exe`-Version/Build prüfen.

---

## SUITE B — GUI Schnitt / Timeline (B-384..B-391)

**Setup:** App → Projekt anlegen → Audio importieren (Testdaten) → Audio analysieren
(Beat/Pacing) → Videos importieren → "Beat→Timeline" / Auto-Cut ausführen → **SCHNITT**-Tab.

| Bug | App-Aktion | PASS-Kriterium | Beleg |
|---|---|---|---|
| **B-384** | Rechtsklick auf Timeline → Kontextmenü → "Alle Anker entfernen" (auch wenn Anker unsichtbar/außerhalb Viewport) | Alle Anker weg, auch nicht-sichtbare | DB: Anchor-Tabelle leer für Projekt; Screenshot |
| **B-385** | Zoom/Resize der Timeline (triggert `render_grid_lines`) | Waveform bleibt sichtbar, Gridlines neu, Scene nicht geleert | Screenshot vor/nach Zoom |
| **B-386** | Waveform mit ungleich langen Bändern rendern (Audio laden) | Kein Crash/IndexError beim Paint | Log ohne Traceback |
| **B-387** | Schnell zwischen 2 Videos in Preview wechseln (späte Frames fremder Pfade) | Vorschau zeigt nur Frame des **aktuell** gewählten Clips | Screenshot; ggf. INCONCLUSIVE (Race schwer erzwingbar) |
| **B-388** | Thumbnails in Media-Grid laden | Thumbnails erscheinen (QPixmap), kein Render-Fehler | Screenshot; Log |
| **B-389** | Clip löschen während Thumbnail noch lädt | Kein Crash, kein Thumbnail auf gelöschter Card | Log ohne Traceback |
| **B-390** | EFFEKTE-Tab → Convert-Effekt-Preview, schnelle Param-Änderung | Nur neueste Preview sichtbar (alte Worker verworfen) | Screenshot. **Hinweis:** EFFEKTE-Tab war in Lauf 2 nicht erreichbar = separate UX-Lücke → falls nicht erreichbar: `BLOCKED (Tab nicht erreichbar)` |
| **B-391** | Frame-Extract (Thumbnail/Preview-Generierung) | Funktioniert; bei Fehler sauberer Exitcode-Fallback statt stillem `-v quiet` | Log zeigt `-v error` Verhalten |

**Status laut Vorlauf:** B-384/385/386 = PASS (Agent-Verify) · B-387 = INCONCLUSIVE ·
B-390 = INCONCLUSIVE-GUI. Coworker: erneut bestätigen oder offene klären.

---

## SUITE C — Chat / Agent-Workflow (B-409..B-417)  *(komplett ungetestet)*

**Setup:** App → Chat-Dock öffnen → lokalen Agent/Ollama aktiv (phi3:mini). Pro Bug einen
Chat-Befehl absetzen.

| Bug | Chat-Eingabe / Aktion | PASS-Kriterium | Beleg |
|---|---|---|---|
| **B-409** | Langen Agent-Task starten, dann Chat-Watchdog/Abbruch auslösen | Worker-Cancel greift, UI-Slots getrennt, kein Zombie-Thread | Log |
| **B-410** | Zwei Agent-Tasks (quasi-)parallel | Registry-Lock hält über Swap+process+restore; keine Registry-Vermischung | Log |
| **B-411** | Action absetzen, deren Handler `{"error":...}` liefert | Antwort meldet **error**, `result` leer; kein Fake-Erfolg | Chat-Antwort + Log |
| **B-412** | Chat: `create_project` / `open_project` / `undo` / `redo` / `sync_anchors` | Läuft im Qt-Main-Thread (BlockingQueued), kein Crash | UI reagiert; Log |
| **B-413** | Chat: `clear timeline` (destruktiv) | Wird als destruktiv erkannt → Bestätigung verlangt | Chat-Dialog |
| **B-414** | Destruktive Action mit Fremd-Param (`clear_timeline` + `project_id`) | Wird **vor** Ausführung abgelehnt (unbekannter Param) | Chat-Antwort |
| **B-415** | Chat: `add_to_timeline` | Nur Medien des **aktiven** Projekts, keine soft-deleted | DB-Check Timeline-Einträge |
| **B-416** | Chat: "erkläre pacing" / "analysiere den Begriff X" | Wird **nicht** als Quick-Command gematcht (normale Erklär-Antwort) | Chat-Antwort |
| **B-417** | Projekt wechseln während Agent-Antwort unterwegs | Stale Worker-Ergebnis verworfen (Request-ID/Projektkontext) | Chat zeigt kein altes Ergebnis |

---

## SUITE D — Export (B-393..B-408)

**Setup:** Projekt mit Timeline (Audio + Video-Clips) → Export-Dialog.

| Bug | Aktion | PASS-Kriterium | Beleg |
|---|---|---|---|
| **B-393** | Export mit `output_name` = `../evil` o.ä. | Path-Traversal abgelehnt, filename-only erzwungen | Fehler-Dialog; kein File außerhalb Zielordner |
| **B-394** | Agent-Export mit absolutem `output_path` | Abgelehnt, kein Task emittiert | Chat/Log |
| **B-395** | Clip mit `source_duration <= 0` exportieren | Vor FFmpeg abgelehnt | Log |
| **B-396** | Clip mit Source-Range > `clip.duration` | Range auf Clip-Dauer begrenzt | Output-Länge; Log |
| **B-397** | Timeline mit Lücke (Gap) exportieren | Vor Renderer abgelehnt statt still verkürzt | Fehler-Meldung |
| **B-398** | Export-Summary anzeigen | Zählt nur exportierbare aktive Medien | Summary-UI |
| **B-399** | Audio mit `start_time`/`source_start/end` exportieren | Audio korrekt geschnitten + per `adelay` auf Timeline-Start | Export hörbar/Wellenform korrekt |
| **B-400** | Export starten/abbrechen mehrfach | Orphan-Cleanup entfernt `pb_concat_*` + `pb_fcs_*` Temp-Files | Temp-Ordner leer nach Lauf |
| **B-407** | Export mit LUFS-Normalisierung, Timeout provozieren | Timeout → harter RuntimeError, kein stiller Soft-Fallback | Log zeigt RuntimeError |
| **B-408** | LUFS auf soft-deleted AudioTrack | Kein Schreiben von `lufs` auf gelöschte Tracks | DB-Check |

> **Echter Export-Beleg:** Output-MP4 in Zielordner existiert, spielt ab, `h264_nvenc`/
> `hevc_nvenc` im FFmpeg-Log (kein libx264 für Video).

---

## SUITE E — Convert / Batch-Convert (B-392, B-401..B-406)

**Setup:** App → KONVERTIEREN-Tab → Videos aus Testdaten.

| Bug | Aktion | PASS-Kriterium | Beleg |
|---|---|---|---|
| **B-392** | ConvertWorkspace öffnen | 2 dokumentierte Tabs vorhanden | Screenshot |
| **B-401** | Batch-Convert starten, dann **Abbrechen** | Cancel greift sofort (Popen+Watchdog), kein Hängen | Log; Prozess weg |
| **B-402** | Batch-Convert laufen lassen | Progressbar 0..100 % korrekt | Screenshot Progress |
| **B-403** | Batch-Convert | Nutzt `bin\ffmpeg.exe` (nicht PATH-`ffmpeg`) | Log FFmpeg-Pfad |
| **B-404** | Convert mit Codec **HEVC** | Mappt auf `hevc_nvenc` (nicht `libx265`) | FFmpeg-Cmd im Log |
| **B-405** | Convert mit Codec **AV1** | `libaom-av1` für GTX-1060 **abgelehnt**, kein FFmpeg-Start | Fehler/Log |
| **B-406** | Proxy-Erstellung (`create_proxy`) | Nutzt `h264_nvenc` Edit-Proxy-Param (nicht `libx264`) | FFmpeg-Cmd im Log |

---

## SUITE F — Packaging / Installer (B-421..B-430)

Großteils statisch/Build-seitig. Voll nur mit echtem PyInstaller-Build verifizierbar.

| Bug | Aktion | PASS-Kriterium |
|---|---|---|
| **B-421/422/423** | `pyinstaller pb_studio.spec` bauen | Build enthält config, translations, migrations, ffmpeg/ffprobe, packaging-hiddenimports |
| **B-427** | `check_ffmpeg` mit System-PATH-ffmpeg | akzeptiert PATH |
| **B-428/429** | NSIS-Text / README prüfen | CUDA 11.3 (kein CPU-Mode), Qt 6.6–6.7 |
| **B-430** | Smoke-Test des Builds | CUDA/Torch-DLLs, FFmpeg, config, translations vorhanden |

> Wenn kein Build gewünscht: `INCONCLUSIVE (kein Build durchgeführt)`. Statisch grün ist
> separat in der ACTIVE_PLAN belegt.

---

## SUITE G — Echte offene Bugs (`open` / `partial-fix`)

| Bug | Aktion | Beobachten |
|---|---|---|
| **Demucs hängt nach Chunk 51** (`open`) | Full-Mix-Stem-Separation auf großem Audio (DJ-Mix 555 MB) starten | Hängt es bei Chunk ~51? GPU blockiert? Log + nvidia-smi |
| **Effekte-Tab unerreichbar** (`partial-fix`) | EFFEKTE-Tab öffnen/erreichen versuchen | Erreichbar ja/nein → bestätigt B-390-UX-Lücke |
| **B-077** (`partial-fix`) | Viele Timeline-Edits schnell | Main-Thread-Freeze bei sync DB-Writes? UI-Lag messen |
| **AutoEditWorker 0xC0000005** (`reverted`) | Auto-Edit-Lauf | Access-Violation/Crash? (war reverted) |

---

## 9. Verdikt-Report-Template

`outputs\VERIFY_<datum>\verdicts.md` — pro Bug eine Zeile, **sofort nach jedem Bug speichern**:

```markdown
# Verify-Report <datum> (autonom, <agent>)
| Bug | Verdikt | Beleg | Notiz |
|-----|---------|-------|-------|
| B-384 | PASS (agent-verify) | screenshot_384.png + DB anchors=0 | Kontextmenü ok |
| B-387 | INCONCLUSIVE | — | Race nicht erzwingbar, Code-Guard vorhanden |
| B-409 | FAIL | log Zeile 1234 Traceback | Cancel greift nicht |
| ...   | ...     | ...   | ... |
```
**Verdikt-Werte:** `PASS (agent-verify)` · `FAIL` · `INCONCLUSIVE` · `BLOCKED`.
**Niemals `fixed`** — das setzt nur der menschliche User danach.

Evidenz-Dateien (Screenshots, Log-Auszüge) im selben Ordner ablegen.

---

## 10. Vault-Pflicht (nach jedem Bug)

Nach **jedem** verifizierten Bug sofort:
- `C:\Brain-Bug\projects\pb-studio\log.md`: Eintrag
  `## YYYY-MM-DD HH:MM live-verify | B-XXX <verdikt>` + 1–3 Zeilen + Pfade.
- Bug-File `wiki\bugs\B-XXX-*.md`: Recheck-Sektion mit Beleg anhängen. **status NICHT auf
  `fixed`** ändern (nur Verdikt dokumentieren).
- Max. 1 Bug ungeloggt.

---

## 11. Ehrliche Grenzen (was autonom NICHT sicher geht)

- **Race-Conditions** (B-387, B-410, B-417): schwer erzwingbar → meist `INCONCLUSIVE`, nur
  Code-Guard-Existenz + Best-Effort-Repro.
- **B-433 echte dGPU-Recovery:** nur bei realem Flap belegbar (nicht erzwingbar).
- **OS-Hard-Kill durch dGPU-Reset:** kann den Coworker-Prozess + App schließen → genau deshalb
  Report-on-disk + WT-Software-Rendering (siehe B-433-Mitigation).
- **Packaging (Suite F):** voll nur mit echtem Build.
- **Hörbare/visuelle Qualität** (Export-Klang, Schnitt-Gefühl): Agent kann Existenz +
  technische Korrektheit prüfen, **nicht** ästhetisch beurteilen.
```
