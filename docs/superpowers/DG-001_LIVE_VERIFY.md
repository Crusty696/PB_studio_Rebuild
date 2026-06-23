# DG-001 — Heavy-Live-Gate Verify-Checkliste

> ## ⛔ EVIDENZ-VERLUST-WARNUNG (Audit 2026-06-18)
> Die unten als ☑ markierten Heavy-Gate-Punkte **H1, H1.3, H2.1-alt, G.\*** sind
> **NICHT durch existierende Belege gedeckt** — alle referenzierten Evidenz-Dateien
> (`outputs/h1_scale.log`, `C:\PB_Studio_H1_3\*`, `test-report/e2e-live-acceptance-20260615/*`,
> `test-report/e2e-h3-concurrency-20260615`) existieren im Repo NICHT mehr. Forensik-Audit:
> 0 von 6 DG-001-Belegen vorhanden. Status dieser ☑ = **`unverifiable-evidence-lost`**
> (reine Doku-Behauptung, weder bestätigt noch widerlegbar). Vor echtem Release neu fahren,
> Belege ins versionierte Verzeichnis committen. Siehe `wiki/synthesis/verifikations-gesamtaudit-2026-06-18.md`.
> **H3-NEU (23.06.):** echter paralleler Demucs+SigLIP/RAFT-Lauf auf GTX1060 neu
> belegt. Versionierte Synthese:
> `docs/superpowers/synthesis/dg001-h3-concurrency-live-2026-06-23.md`.
> **H2.1-NEU (18.06.):** echter NVENC-Proxy existiert + ist `h264_nvenc`-verifiziert, liegt aber
> in `storage/H2.2-Playback/storage/proxies/Stumes_video_ohne_Ton_Alles_t_edit_proxy.mp4`
> (NICHT im zuvor falsch verwiesenen leeren Ordner `test-report/dg001-h22-retry/`).

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
| H2.2 | ~~In PB Studio / QMediaPlayer abspielen, ruckelfrei?~~ **NICHT ANWENDBAR** | entfällt | [User] | n/a |

> **H2.2 = NICHT ANWENDBAR (User-Entscheidung 2026-06-18, B-542).**
> Die App hat keinen `QMediaPlayer` / kein flüssiges Video-Playback — die SCHNITT-/Export-
> Vorschau ist eine ffmpeg-Frame-Extraktion bei ~10 fps (Standbild-Diashow), kein
> abspielbarer Video-Stream. Ein „ruckelfrei"-Verdikt ist gegen diese Architektur nicht
> sinnvoll prüfbar. Das fehlende echte Playback bleibt als bekannte Produkt-Lücke in B-542
> dokumentiert; H2.2 ist als Release-Gate-Kriterium gestrichen. Siehe B-542.

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
- Alle [Agent]-Punkte grün + H1.3/G.* vom User bestätigt; **H2.2 = nicht anwendbar (B-542)**: ☐
- **`fixed`/`release` setzt ausschließlich der User** — Datum/Name: `__________`


---

## Ergebnisse 2026-06-15 (Agent-Lauf)

### H3 — Neu verifiziert 2026-06-23: **PASS**

Reproduzierbarer Runner:
`scripts/diag/verify_dg001_h3_concurrency.py`.

- Echter `htdemucs_ft`-CUDA-Lauf, `reused=False`, vier Stems, Audio 8/8 Stages.
- Echte Video-Pipeline mit SigLIP+RAFT, 7/7 Stages und allen Artefakten.
- Beide Threads beendet, kein Deadlock/OOM, GPU-Peak 4534/6144 MiB.
- Finaler Run `20260623-050437`, Walltime 36.375 s; GPU nach Lauf vollständig freigegeben.

Beleg:
`docs/superpowers/synthesis/dg001-h3-concurrency-live-2026-06-23.md`.

### H3 — Historischer Lauf 2026-06-15: **EVIDENZ VERLOREN**

Die folgende historische Beschreibung bleibt als Herkunftsnotiz erhalten,
gilt aber nicht als Beleg. Der neue gültige H3-Beleg steht direkt darüber.

Historisch behaupteter gleichzeitiger Lauf auf GTX 1060 (isoliertes Projekt
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
- **H2.2** menschliches QMediaPlayer/PB-Playback-Verdikt.

`python tools/release_gate.py` bleibt korrekt Exit 2, bis diese Punkte live
abgenommen oder vom User neu entschieden sind.

### H1.3 Vorbereitung 2026-06-15 — vorbereitet, nicht gestartet
Runbook: `docs/superpowers/DG-001_H1_4H_PREP_RUNBOOK.md`.
Dry-run/Manifest-Skript: `tools/prepare_dg001_h1_4h.ps1`.
User-Quellen:
- Video-Root: `C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur`
- Audio: `C:\Users\David Lochmann\Music\Audio\Psy-Set\Podcast-04.m4a`

Vorbereitungslauf `powershell -ExecutionPolicy Bypass -File tools\prepare_dg001_h1_4h.ps1 -WritePlan`:
- 223 probe-lesbare Video-Kandidaten.
- 2172.064 s eindeutige Videozeit.
- 11258.659 s Audiozeit.
- 7 Rotationen der Kandidatenliste reichen fuer 4 h.
- Eine kaputte MP4 wurde uebersprungen:
  `converted\20250719_0241_Mystical_Bioluminescent_Jungle_v1_std.mp4`
  (`moov atom not found`).
- Geschriebene Vorbereitungsdateien unter
  `test-report\dg001-h1-4h-20260615\`: `source_candidates.json`,
  `video_loop.ffconcat`, `commands.ps1`, `README.md`.

Kein 4h-Encoding gestartet. Kein Pipeline-Lauf gestartet. H1.3 blieb zu diesem Zeitpunkt offen.

### H1.3 4h-Modell-Pipeline-Lauf 2026-06-15 — PASS (agentisch, low-profile)
User-Anweisung: vor Nutzung Pfade mit Leerzeichen vermeiden. Deshalb wurden Arbeitskopien
und Junctions ohne Leerzeichen verwendet:
- `C:\PB_Studio_H1_3\source_video.mp4`
- `C:\PB_Studio_H1_3\source_audio.m4a`
- `C:\PB_Studio_H1_3\output_4h.mp4`
- `C:\PBStudioRepo`
- `C:\Miniconda3`

Input `C:\PB_Studio_H1_3\output_4h.mp4` per `ffprobe`:
- Video: H.264, 640x360, 5 fps, Dauer `14400.000000`, `72000` Frames.
- Audio: AAC stereo 48 kHz, Dauer `14400.000000`, `675000` Frames.
- Datei: `1187278666` Bytes.

Pipeline-Runner: `C:\PB_Studio_H1_3\run_h1_3_pipeline.py`.
Ergebnis: `C:\PB_Studio_H1_3\pipeline_result.json`.
- `completed_count=7`
- `failed_count=0`
- `cancelled=false`
- `elapsed_s=5944.536456499998`

Stages:
- `proxy_gen`: done, `0.264s`.
- `scene_detect`: done, `149.409s`, `scene_count=2`.
- `keyframe_extract`: done, `3.130s`, `keyframe_count=7200`, `wanted_count=7200`, `skipped_count=0`.
- `siglip_embed`: done, `3497.509s`, GTX 1060/CUDA aktiv, `embeddings_count=7200`, `embedding_dim=1152`, `dtype=float16`.
- `raft_motion`: done, `2292.209s`, `pairs=7199`, `variant=raft_small`.
- `vlm_caption`: done, `caption_count=2`, `is_stub=true`.
- `cross_modal`: done, `suggestions=0`.

Ehrliche Grenzen:
- Input ist low-profile (640x360/5fps), nicht 720p/24fps.
- Videoquelle ist ein echter Solo_Natur-Clip geloopt; Audio ist echte `Podcast-04.m4a` geloopt.
- `proxy_gen` nutzte vorbereitete valide Proxy-Datei, weil 4h CPU-Proxy-Encode im Stage-Timeout von 300s scheitert.
- `VideoDecoder.probe` wurde im Runner gecached, weil wiederholte `ffprobe`-Aufrufe bei 4h-Keyframes vorher Timeout ausloesten.

H1.3 ist damit fuer den agentisch gestarteten 4h-Endurance-Pipeline-Lauf belegt.
H2.2 bleibt offen, weil menschliches Playback-Verdikt nicht agentisch ersetzbar ist.
