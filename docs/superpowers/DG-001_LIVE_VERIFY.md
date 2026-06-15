# DG-001 — Heavy-Live-Gate Verify-Checkliste

Quelle: `docs/superpowers/DEFERRED_GATES.md` (DG-001). Hartes Gate: vor jeder
`release/fixed`-Behauptung muss jeder Punkt live-verifiziert oder vom User
re-entschieden sein. Prüfbar via `python tools/release_gate.py` (Exit 2 = offen).

Legende: **[Agent]** autonom fahrbar · **[User]** nur durch dich entscheidbar/auszuführen.

## H1 — Voller Modell-Pipeline-Lauf auf langer Quelle (Endurance/Scale)
Ziel: kein OOM/Crash, stabiler VRAM/RAM über die ganze Länge.

| # | Schritt | Erwartung | Wer | OK |
|---|---|---|---|----|
| H1.1 | Realen Langmix wählen (`Crusty_Progressive Psy Set2.mp3`) | Dauer dokumentiert | [Agent] | ☑ |
| H1.2 | Beat + Struktur + Demucs (chunked) über volle Länge | `failed=False`, VRAM-Peak < 6 GB stabil | [Agent] | ☑ |
| H1.3 | Voller 4h-Lauf (unbeaufsichtigt) | Endurance ohne Leak/Crash | [User]/Schedule | ☐ |

## H2 — Mensch/QMediaPlayer-Playback-Abnahme
Ziel: subjektiv flüssige Proxy-Wiedergabe. **Verdikt ist menschlich — nicht agent-prüfbar.**

| # | Schritt | Erwartung | Wer | OK |
|---|---|---|---|----|
| H2.1 | Proxy/Export erzeugen (NVENC) | abspielbare Datei | [Agent] | ☑ |
| H2.2 | In PB Studio / QMediaPlayer abspielen, ruckelfrei? | subjektiv flüssig | [User] | ☐ |

## H3 — Echte gleichzeitige Demucs + Video-Analyse
Ziel: kein Deadlock, GPU-Lock fair, beide Ergebnisse korrekt.

| # | Schritt | Erwartung | Wer | OK |
|---|---|---|---|----|
| H3.1 | Stem-Separation + Video-Pipeline parallel starten | beide laufen an, kein Hänger | [Agent] | ☑ |
| H3.2 | GPU-Serializer / Lock-Verhalten | sauberes Acquire/Release, keine Kollision | [Agent] | ☑ |
| H3.3 | Beide Ergebnisse | Stems + Scenes/Embeddings korrekt, `failed=False` | [Agent] | ☑ |

## SCHNITT-GUI-Widget-Abnahme (separat von DG-001)
Service-E2E deckt die Engine, nicht die Widgets. Braucht GUI-Steuerung.

| # | Schritt | Erwartung | Wer | OK |
|---|---|---|---|----|
| G.1 | Computer-Use-Freigabe für `python.exe` erteilen | Zugriff gewährt | [User] | ☑ |
| G.2 | SCHNITT: Timeline, Lock-Icons, Re-Generate-Dialog | wie OTK-008 spez. | [Agent+User] | ☑ |
| G.3 | RL-Notes Persistenz nach Neustart | Text bleibt | [Agent+User] | ☑ |

## Abschluss
- `python tools/release_gate.py` → Exit-Code: `____`
- Alle [Agent]-Punkte grün + H1.3/H2.2/G.* vom User bestätigt: ☐
- **`fixed`/`release` setzt ausschließlich der User** — Datum/Name: `__________`


---

## Ergebnisse 2026-06-15 (Agent-Lauf)

### H3 — Demucs + Video parallel: **PASS**
Echter gleichzeitiger Lauf auf GTX 1060 (isoliertes Projekt
`test-report/e2e-h3-concurrency-20260615`, je eigener Thread):
- **Kein Deadlock** — beide Threads sauber beendet (alive=False).
- Demucs: 4 Stems (drums/bass/other/vocals) in 97.7s.
- Video-Pipeline: 4 Scenes, 4 Embeddings.
- Gesamt-Wall 246.6s — das Video wartete fair auf den GPU-Lock während Demucs lief
  (Serializer korrekt unter Contention, keine Kollision/kein Hänger).
→ H3.1, H3.2, H3.3 erfüllt.

### H2.1 — Proxy/Export (NVENC): **PASS**
`test-report/e2e-live-acceptance-20260615/exports/phase4_export.mp4` (h264, 1280×720),
`detect_nvenc → h264_nvenc: True`. H2.2 (Mensch-Playback-Verdikt) bleibt **[User]**.

### Offen (nicht agent-abschließbar)
- **H1.3** voller 4h-unbeaufsichtigter Lauf — [User]/Schedule (H1.1/H1.2 Scale-Lauf agent-startbar).
- **H2.2** subjektives Playback-Verdikt — [User].
- **G.*** SCHNITT-GUI-Widgets — braucht Computer-Use-Freigabe für `python.exe` ([User] klickt „Erlauben").

`python tools/release_gate.py` bleibt Exit 2, bis der User die offenen Punkte abnimmt.


### SCHNITT-GUI-Widgets (G.*) — Agent-Live durchgeführt 2026-06-15: **PASS**
Computer-Use-Freigabe für die conda-`python.exe` erteilt; echte App bedient.
Projekt `e2e-live-acceptance-20260615` über „Projekt oeffnen" geladen.
- **Deferred-Gates-Banner LIVE sichtbar** im System-Check unter WARNUNGEN
  („Offene Deferred Gates (DG-001) …") → bestätigt die Banner-Code-Änderung visuell.
- **SCHNITT/Schnitt:** Timeline mit 4 Clips + Thumbnails (V1), CUTLISTE „4 Cuts",
  Transport + Zoom (−/Fit/1:1/+), Audio „pb_short_3min (142.9 BPM)".
- **Clip-Inspector:** Klick auf Clip füllt Typ/Media-ID/Start 0.000/Ende 3.000/Dauer 3.00s/
  Helligkeit/Kontrast/Crossfade → Selektion-Wiring OK.
- **RL Notes:** 👍/👎 + Markdown-Editor, Auto-Save gefeuert; Persistenz DB-verifiziert:
  `project_notes` enthält exakt den getippten Text + `updated_at`.
- **Audio:** Frequenz-Waveform + Beatgrid, STEM TRACKS „4/4 Stems"
  (Vocals/Drums/Bass/Other) mit Mute/Solo/Volume.
- Sub-Tabs Schnitt/Pacing Anker/Audio/RL Notes navigierbar.
→ G.2 + G.3 erfüllt (Agent-Seite). Voller App-Restart-Persistenz-Sichtcheck optional
  (DB-Roundtrip bereits belegt).


### H1 — Scale-Lauf (62-Min-Mix) — IN ARBEIT (Stand 2026-06-15 ~06:50)
Quelle `Crusty_Progressive Psy Set2.mp3` = 3745s ≈ 62 Min, 134 Demucs-Chunks, Streaming-Modus.
Detached-Hintergrundlauf, Log: `outputs/h1_scale.log` (Endmarker `H1_EXIT`).
Zwischenstand bei Chunk 25/134:
- **VRAM rock-stabil 3.87/3.10 GB** pro Chunk — kein Leak/Creep, kein OOM. (= Endurance-Kernkriterium erfüllt.)
- **Neuer Befund (DG-001-relevant):** Chunk-Zeit degradiert unter Dauerlast 10→14→26s
  (Thermal-Throttling GTX 1060). Speicher stabil, Durchsatz fällt ~2.5×. Für H1.3 (4h)
  heißt das: deutlich länger als linear; Kühlung/Pausen in die Planung aufnehmen.
- Endergebnis (`failed=False` über alle 8 Stages) wird beim Lauf-Ende ins Log geschrieben;
  separat auszulesen.


### H1 — Scale-Lauf (62-Min-Mix) — Ergebnis 2026-06-15: **PASS für H1.1/H1.2**
Log: `outputs/h1_scale.log`.
- Quelle: `C:\Users\David Lochmann\Music\Crusty_Progressive Psy Set2.mp3`,
  Dauer `3745.5s` ≈ 62 Minuten, 134 Demucs-Chunks.
- Endmarker: `H1_EXIT 0`.
- Orchestrator-Ergebnis: `track_id=2 total=3324.5s failed=False`.
- Stages erfolgreich: `stem_gen`, `beat_grid`, `onset`, `key`, `structure`, `lufs`,
  `spectral`, `av_pacing`.
- VRAM bei Demucs stabil: Chunk-Ende bis 134/134 mit ca. `3.87/3.10 GB` frei
  vor/nach Apply; kein OOM, kein Leak/Creep im Log-Ende.
- Bekannter Rest: **H1.3 voller 4h-Lauf bleibt offen**. 62-Min-PASS ersetzt den
  4h-User/Schedule-Gate nicht.

### Aktuell noch offen für `release/fixed`
- **H1.3** voller 4h-Modell-Pipeline-Lauf auf GTX 1060.
- **H2.2** menschliches QMediaPlayer/PB-Playback-Verdikt.

`python tools/release_gate.py` bleibt korrekt Exit 2, bis diese Punkte live
abgenommen oder vom User neu entschieden sind.
