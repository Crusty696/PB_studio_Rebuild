---
title: ComfyUI-Studio Pipeline — Analyse + Uebertragbarkeit auf PB Studio
date: 2026-07-15
type: synthesis
status: offen
tags: [comfyui, edl, pacing, recherche, fremd-pipeline, uebertragbarkeit]
---

# ComfyUI-Studio Pipeline — was wir uns abschauen koennen

**Auftrag (User 2026-07-15):** "ich habe in ComfyUI einen Workflow der auch musikvideos erstellt.
schau dir mal diese files an und untersuche sie genau, ich glaube es hat einiges das wir uns
davon abschauen und fuer unsere app nutzen koennen."

**Quelle:** `C:\Users\David_Lochmann\Documents\Vaults\ComfyUI-Studio-FULL-backup\30_Workflows\stages\`
11 MD-Dateien (INDEX + Stage 00-09), ~168 KB, alle einzeln gelesen.

**Fremd-System in Kurz:** 745 stumme AI-Clips + ein 62-Min-DJ-Mix (Crusty Progressive Psy).
Stages: ffprobe/BPM/Mood-Heuristik -> Florence-2-Captions (3 Frames) -> Farben/Motion/OD/OCR ->
OpenCLIP ViT-L/14 + KMeans k=20 -> librosa Audio-Analyse -> EDL-Builder v1..v6 -> ffmpeg
3-Phasen-Render -> Dashboards. Produktiv: EDL v6 "Thematic Director" (415 Cuts, 14 Kapitel).

## Faktischer Abgleich (Explore-Agent, Datei:Zeile-belegt)

| # | Konzept (ComfyUI) | Status in PB Studio | Beleg |
|---|---|---|---|
| 1 | Lokale BPM-Map (30s-Fenster, Sektionen) | **FEHLT** | AudioTrack.bpm (models.py:162) + Beatgrid.bpm (:287) = EIN globaler Skalar. beat_positions/energy_per_beat (:289-292) existieren als Zeitreihe, aber keine tempo_curve/bpm_sections |
| 2 | Thematische Style-Gruppen (20 Cluster -> 4 Themen) | **FEHLT** | style_bucket_clusterer.py:151-262 liefert nur flache UMAP+HDBSCAN-Cluster (labels/centroids), keine zweite Ebene |
| 3 | Transition-Matrix (erlaubte Themen-Uebergaenge) | **FEHLT** | nur _ROLE_PREFERRED (scorer.py:81-92) = Section x Role, nicht Stil/Thema |
| 4 | Narrative Kapitel (14 x ~240s mit Leit-Thema) | **FEHLT** | nur StructureSegment (models.py:495-513) INTRO/BUILDUP/DROP/... = Sekunden bis wenige Minuten |
| 5 | Hero-Cluster (visueller roter Faden) | **FEHLT** | role="hero" (scorer.py:82) ist eine Rolle pro Einzelclip, kein platzierter Leitmotiv-Cluster |
| 6 | Cluster-Signaturen (avg_motion/dominant_mood/color_temp/energy_score) | **FEHLT** | ClusterResult (style_bucket_clusterer.py:151-165) hat nur labels + centroids |
| 7 | Visual-Flow / Neighbor-Chain | **TEILWEISE** | style_compat() (scorer.py:118-157) = Cosinus-Bonus als EIN Scoring-Term (w_style). KEINE Nachbarschaftssuche, die Kandidaten einschraenkt oder Ketten baut |
| 8 | Full-Length-Cuts ("Clip ganz spielen") | **FEHLT** | pacing_service.py:1493/1527 nutzt vid_duration nur als Sicherheits-Clamp; seg_duration kommt aus Beat/Phrase-Logik |
| 9 | Audio-State-Detector (Drop/Break -> Cut-Laenge) | **VORHANDEN** | cut_density_modulator.py:21 apply_drop_burst (3-Cut-Burst + Hold-Bars), Section "drop" 0.5x-Spacing (:90-154). Break ueber StructureSegment-Label BREAKDOWN |
| 10 | Farb-Analyse | **TEILWEISE** | visual_curves.py:34-140 liefert brightness/saturation/color_temperature (log(R/B)) als Kurve. KEINE dominante-Farben-Palette (Hex/KMeans) |
| 11 | Watermark-Erkennung (OCR -> sora/runway/pika filtern) | **FEHLT** | keine Treffer fuer watermark/ocr im gesamten Python-Code |
| 12 | Segment-Render-Cache (nur geaenderte Cuts neu encoden) | **FEHLT** | export_service.py hat nur In-Memory-Caches INNERHALB eines Laufs (_probe_cache :134-174, _std_cache :762-817). Keine Persistenz ueber Laeufe |

**Bilanz: 8 fehlen, 3 teilweise, 1 vorhanden.**

## Die drei staerksten Ideen (inhaltlich)

### A. Full-Length-Cuts — eine gekippte Grundannahme (Stage 5, v6)

v1-v5 schnitten starr alle 8 Beats -> 1088 Cuts a 3.45s. v6 erkennt: "Clip-Material wird
wertvoller, wenn man es GANZ spielt statt es nach 3 Sekunden zu zerschneiden" -> **415 Cuts**
mit 7-10s. Logik: naechsten Beat suchen, der noch in die Clip-Dauer passt; bei audio_state=drop
target_dur <= 4s erzwingen; vor manuellem Anker kappen.

Bei uns bestimmt die Beat/Phrase-Logik die Laenge, die Clip-Dauer ist nur ein Clamp.

### B. Narrative Dramaturgie ueber die ganze Stunde (Stage 5, v6)

20 Cluster -> 4 deutbare Themen (gothic_demonic / neon_cyber_rave / mystic_nature /
ethereal_water). Zugehoerigkeit ueber Cluster-ID ODER Caption-Keyword. Eine
TRANSITION_COMPATIBILITY-Matrix legt fest, welches Thema auf welches folgen darf (gothic->neon
erlaubt, gothic->ethereal nicht). Kapitel werden an Energy-Milestones (RMS-Spruenge > 0.14)
geschnitten, Ziel ~240s. Ergebnis: 14 Kapitel ueber 62 Min.

Uns fehlen alle drei Ebenen (Themen, Matrix, Kapitel). Wir haben nur Struktur-Segmente.

### C. Visual-Flow als Kette, nicht als Bonus (Stage 3+5)

Top-5-CLIP-Nachbarn pro Clip vorberechnet (`siehe_auch`). Der Builder geht vom aktuellen Clip
zu dessen Top-Nachbarn -> Ketten von 3-6 Cuts. v6 meldet 100% Chain-Coherence.
Score: +150 fuer direkten Nachbarn, +50 fuer Distanz-2, +400 fuer Bridge-In/Out an Ankern.

Wir haben style_compat als weichen Cosinus-Bonus. Der Unterschied ist strukturell: Ein Bonus
beeinflusst das Ranking, eine Kette bestimmt die Kandidatenmenge.

## Weitere uebertragbare Details

- **Lokale BPM-Map (Stage 4):** 30s-Fenster ueber den Mix, Nachbarfenster mit +/-3 BPM zu
  Sektionen gefaltet. Ihr Mix: 92..145 BPM ueber die Laenge, 26 Sektionen. Ein globales BPM
  waere schlicht falsch. WIR HABEN NUR EIN GLOBALES BPM — und analysieren DJ-Sets (is_dj_mix).
  Guenstig: aus unseren vorhandenen beat_positions laesst sich lokales Tempo ableiten
  (Beat-Abstaende ueber ein Fenster), ohne neue Audio-Analyse.
- **Watermark-Filter (Stage 2):** OCR gegen Liste bekannter AI-Tool-Marken (sora/runway/pika/
  kaiber/luma/midjourney/haiper). 87 von 745 Clips betroffen. Billig, praktisch bei AI-Material.
- **Segment-Render-Cache (Stage 6):** Aendern sich 50 von 1088 Cuts -> nur diese 50 neu
  encodiert, Rest per File-Existence-Check "gerendert" (0.001s). Cold 3.1 min, warm 30 s.
- **Cluster-Signaturen (Stage 5):** Aggregat pro Cluster (avg_motion, motion_distribution,
  dominant_mood, avg_hue ringfoermig gemittelt, color_temperature, energy_score =
  0.6*motion + 0.25*brightness + 0.15*saturation). Voraussetzung fuer Themen-Bildung.
- **Golden-Angle-Farbpalette (Stage 7):** `hsl((cid * 137.5) % 360, 60%, 55%)` — maximale
  visuelle Trennung benachbarter Cluster-IDs. Netter Trick fuer unsere UI.
- **Kamera-Klassifikation (Stage 8):** Qwen2.5-VL liefert `camera`: push-in/dolly/pan/static/
  handheld. Waere fuer Schnitt-Entscheidungen nutzbar (nicht zwei push-ins hintereinander).

## Wo PB Studio STAERKER ist (ehrlich)

- **Motion:** deren motion_score = mittlere Pixel-Differenz erster vs. letzter Frame
  (analyze_visual.py). Wir: RAFT-Optical-Flow.
- **Mood:** deren stimmung = Keyword-First-Match auf Dateiname/Caption (8 feste Vokabeln).
  Wir: SigLIP-Embeddings + Brain-V3-Reranker mit lernenden Gewichten + Feedback.
- **Clustering:** deren KMeans k=20 fix (Doku raeumt ein: k=10 zu grob, k=30 zu fein,
  20 = "pragmatischer Sweet Spot"). Wir: UMAP+HDBSCAN, Clusterzahl datengetrieben.
- **Cut-Platzierung:** wir haben cut_snapper + cut_density_modulator + Stem-SNR-Gewichtung +
  Memory/Feedback-Term. Deren Score ist eine handgeschriebene Punkte-Formel.
- **Ihr Render-Cache hat einen echten Bug:** index-basiert (`seg_00042.mp4`), darum warnt die
  Doku selbst, man muesse vor jedem Lauf `seg_*.mp4` manuell loeschen — sonst landen alte Clips
  an neuen Positionen. Ein Content-Hash (Clip-Pfad+Trim+Preset) statt Index loest das.
  Falls wir das uebernehmen: NICHT den Index-Ansatz kopieren.

## Status

Reine ANALYSE. Kein Code geaendert. Keine Empfehlung umgesetzt.
Naechster Schritt: User entscheidet, welche Punkte gebaut werden.
