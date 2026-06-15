# PB Studio — E2E Live-Abnahme (Pflicht-Checkliste)

status: template
created: 2026-06-15
zweck: EINE verbindliche End-to-End-Live-Abnahme statt verteilter "test-grün"-Subtasks.

Diese Checkliste schließt die Lücke zwischen "code/test-grün" und "vom User
live-verifiziert". Solange offene Deferred Gates existieren
(`docs/superpowers/DEFERRED_GATES.md`, hart geprüft via
`python tools/release_gate.py`), ist KEIN `release`/`fixed` erlaubt.

Eine Abnahme zählt nur, wenn EIN durchgehender Lauf
**Import → Analyse → SCHNITT → Export** ohne Crash und mit den unten
genannten Erwartungswerten beobachtet wurde. Teil-PASS einzelner Subtasks
ersetzt diese Abnahme nicht.

---

## Vorbedingungen

- Start ausschließlich über `start_pb_studio.bat` (wählt den korrekten
  conda-Interpreter `pb-studio`, Python 3.10 / torch 1.12.1+cu113).
- Beim Start dürfen im System-Check **keine roten Errors** stehen. Ein
  Deferred-Gates-**Banner** (Warnung) ist erwartet und erlaubt.
- GPU sichtbar (CUDA `cuda:0`, GTX 1060). FFmpeg in `bin/` oder PATH.
- Frisches oder bekanntes Test-Projekt; Datensatz dokumentieren
  (Dateiname Audio + Anzahl Videoclips).

---

## Phase 1 — PROJEKT

| # | Schritt | Erwartung | OK |
|---|---|---|----|
| 1 | Neues Projekt anlegen oder bekanntes öffnen | Projekt lädt, kein Traceback in `logs/pb_studio.log` | ☐ |
| 2 | Projektname/Workspace sichtbar | Titel + leere/gefüllte Material-Liste korrekt | ☐ |

## Phase 2 — MATERIAL & ANALYSE

| # | Schritt | Erwartung | OK |
|---|---|---|----|
| 3 | Audio importieren (MP3/WAV/FLAC) | Track erscheint, Dauer/BPM-Feld gefüllt | ☐ |
| 4 | Videoclips importieren (MP4/MOV) | Clips in Media-Grid, Thumbnails laden (max. 4 gleichzeitig) | ☐ |
| 5 | "Audio analysieren" | Stems (Vocals/Drums/Bass/Other), Beatgrid, Struktur; `failed=False`; kein V2-Fehler in Konsole | ☐ |
| 6 | Videoanalyse (Scene + RAFT + SigLIP) | Pro Clip Szenen + Motion + Embeddings; keine OOM/CUDA-Errors | ☐ |
| 7 | RAM/VRAM beobachten (langer Mix > 60 min) | RAM-Peak für Waveform-Schritt < 1 GB; kein VRAM-OOM | ☐ |

## Phase 3 — SCHNITT

| # | Schritt | Erwartung | OK |
|---|---|---|----|
| 8 | Preset wählen (Techno/Cinematic/House/Festival) | Auto-Edit startet, Stage-Progress sichtbar | ☐ |
| 9 | Sub-Tab *Schnitt* | Preview + Transport + Timeline mit Clips; Lock-Icons funktionieren | ☐ |
| 10 | Sub-Tab *Pacing & Anker* | PacingCurve, Cut-Rate, Re-Generate (mit Bestätigungsdialog) | ☐ |
| 11 | Re-Generate mit 1 gelockten Clip | Gelockter Clip bleibt erhalten, Rest neu | ☐ |
| 12 | Sub-Tab *Audio* | Waveform + Beatgrid + Struktur-Marker, Stems-Mixer, LUFS/Tonart | ☐ |
| 13 | Sub-Tab *RL & Notes* | 👍/👎 speicherbar; Notiz schreiben → App neu starten → Notiz noch da | ☐ |

## Phase 4 — EXPORT

| # | Schritt | Erwartung | OK |
|---|---|---|----|
| 14 | Export starten | Render läuft; FFmpeg nutzt `h264_nvenc` (oder dokumentierter CPU-Fallback) | ☐ |
| 15 | Ergebnisdatei prüfen | Datei in `exports/`, abspielbar, Audio LUFS-normalisiert | ☐ |
| 16 | Logs prüfen | Kein `Traceback`/`CRITICAL`/Resolver-Fehler in `logs/pb_studio.log` und `outputs\app_run_*.log` | ☐ |

---

## Deferred Gates (DG-001) — Heavy-Live-Gate

Vor `release`/`fixed` zusätzlich erforderlich (siehe `DEFERRED_GATES.md`):

| # | Schritt | Erwartung | OK |
|---|---|---|----|
| H1 | Voller 4h-Modell-Pipeline-Lauf auf GTX 1060 | Durchlauf ohne Crash/OOM | ☐ |
| H2 | Mensch/QMediaPlayer-Proxy-Playback | Subjektiv flüssige Wiedergabe abgenommen | ☐ |
| H3 | Echte gleichzeitige Demucs + Video-Analyse | Kein Deadlock; GPU-Lock fair; beide Ergebnisse korrekt | ☐ |

---

## Sign-off

- Datensatz (Audio / #Clips): `__________________`
- Beobachtete Auffälligkeiten / neue Funde (→ neues Bugfile, nicht hier fixen): `__________________`
- `python tools/release_gate.py` Exit-Code: `____` (0 = frei, 2 = blockiert)
- Alle 16 Schritte PASS **und** (für release) H1–H3 PASS: ☐
- **`fixed`/`release` wird ausschließlich vom User gesetzt** — Datum/Name: `__________________`
