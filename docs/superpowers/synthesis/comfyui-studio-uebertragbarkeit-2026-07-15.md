---
title: ComfyUI-Studio-Pipeline — Uebertragbarkeit auf PB Studio
date: 2026-07-15
type: synthesis
status: offen
tags: [comfyui, edl, pacing, uebertragbarkeit, analyse, fremdsystem]
---

# ComfyUI-Studio → PB Studio: was ist uebertragbar?

**Auftrag (User 2026-07-15):** "ich habe in ComfyUI einen Workflow der auch musikvideos
erstellt. schau dir mal diese files an und untersuche sie genau, ich glaube es hat einiges
das wir uns davon abschauen und fuer unsere app nutzen koennen. eventuell braucht es ein
paar anpassungen."

**Quelle:** `C:\Users\David_Lochmann\Documents\Vaults\ComfyUI-Studio-FULL-backup\30_Workflows\stages\`
— 11 MD-Dateien (INDEX + Stage 00-09), alle einzeln gelesen.

**Methode:** Fremdsystem vollstaendig gelesen, danach jedes Konzept per Explore-Agent
faktenbasiert gegen den PB-Studio-Code geprueft (Datei:Zeile-Belege). KEIN Code geaendert.

---

## Das Fremdsystem in einem Absatz

ComfyUI-Studio ist eine Sammlung von PowerShell- und Python-Skripten ueber einem
Obsidian-Vault. 745 stumme AI-Clips + EIN 62-min-DJ-Mix -> Musikvideo. Zehn Stages:
Tech-Metadaten (ffprobe) -> Florence-2-Captions (3 Frames) -> Farben/Motion/Objekte/OCR ->
CLIP-Embeddings (ViT-L/14) + KMeans k=20 -> Audio-Analyse (Beats/Energie/Struktur) ->
EDL-Builder (v1..v6) -> ffmpeg-Render -> Dashboards. Zustand liegt im YAML-Frontmatter
der Notes, nicht in einer DB. Strukturell ist das FAST DECKUNGSGLEICH mit PB Studio —
darum ist der Vergleich ueberhaupt sinnvoll.

**Das Wertvollste ist Stage 5:** Der EDL-Builder existiert in SECHS dokumentierten
Generationen. Die Evolution v1->v6 ist ein Erfahrungsbericht darueber, was beim
automatischen Schneiden funktioniert — genau unsere Domaene (pacing/scorer).

---

## Abgleich — 12 Konzepte (alle Belege verifiziert)

| # | Konzept | PB Studio | Beleg |
|---|---|---|---|
| 1 | Watermark-Erkennung (OCR) | **FEHLT** | kein ocr/watermark/tesseract im Code, kein DB-Feld |
| 2 | Lokale BPM-Map (Tempo ueber Zeit) | **FEHLT** | AudioTrack.bpm (models.py:162) + Beatgrid.bpm (:287) = je EIN globaler Skalar |
| 3 | Visual-Flow als Kette | **TEILWEISE** | style_compat() scorer.py:118-157 (Cosinus prev vs. Kandidat, w_style) — aber keine Top-K-Nachbarschaft, keine Kette |
| 4 | Cluster-Signaturen | **FEHLT** | StyleBucketClusterer.fit() liefert nur labels/centroids(UMAP-Raum, nicht interpretierbar)/probabilities |
| 5 | Hero-Cluster (roter Faden) | **FEHLT** | role="hero" ist Einzelclip-Kategorie, kein wiederkehrender Cluster |
| 6 | Kapitel/Themen + Transition-Matrix | **FEHLT** | nur StructureSegment (models.py:495-513), keine Themen-Ebene |
| 7 | Segment-Cache ueber Laeufe | **FEHLT** | export_service.py: nur In-Memory _probe_cache (:134) + _std_cache (:762), pro Lauf |
| 8 | Parallel-Encoding | **FEHLT — BEWUSST** | _run_ffmpeg() :1590-1606 serialisiert NVENC via gpu_serializer.acquire() |
| 9 | Quellen-Tracking (manual-Schutz) | **FEHLT** | kein mood_source/bpm_source; nur TimelineEntry.locked (:652) schuetzt Platzierung |
| 10 | Variable Cut-Laenge | **TEILWEISE** | cut_density_modulator.py:86-100 diskrete Section-Multiplikatoren (Buildup x2.0, Drop x0.5) |
| 11 | Volle Clip-Laenge spielen | **FEHLT** | pacing_service.py:1484-1493 nutzt vid_duration nur als Sicherheits-Clamp |
| 12 | Drop/Break-Erkennung | **VORHANDEN — besser als Fremdsystem** | onset_rhythm_service.py:578-696 |

---

## WICHTIG: Was NICHT uebernommen werden darf

**Parallel-Encoding (deren PARALLEL=4).** Das Fremdsystem encodiert 4 Segmente gleichzeitig
— auf einer AMD RX 7800 XT mit h264_amf. Auf der GTX 1060 (Pascal) limitiert NVIDIA die
Zahl gleichzeitiger NVENC-Sessions auf ~2-3. PB Studio weiss das bereits und serialisiert
bewusst: `export_service.py:1590-1606` haelt `gpu_serializer.acquire()` mit dem Kommentar
"GTX 1060 (Pascal, ~2-3 NVENC-Sessions) ... sonst OpenEncodeSessionEx failed".
-> Blindes Uebernehmen wuerde die Exporte zum Absturz bringen. Unsere Loesung ist korrekt.
Falls Parallelitaet gewuenscht: hoechstens 2 Worker UND die Serialisierung entsprechend
umbauen — nicht einfach den Lock entfernen.

**Drop/Break-Erkennung (#12).** Hier ist PB Studio dem Fremdsystem VORAUS. Die haben
Schwellwert-Heuristiken auf low_energy (>0.58 = drop, <0.22 = break). Wir haben echte
Section-Erkennung (WARMUP/BUILDUP/DROP/BREAKDOWN/TRANSITION/COOLDOWN,
onset_rhythm_service.py:578-696) und sie ist tiefer verdrahtet: Drop-Burst (3 Cuts/800ms +
4 Bars Hold), Drop-Spacing x0.5, erzwungener Hard-Cut bei Drops (pacing_service.py:1498-1503),
Section->Crossfade-Mapping (:868-870). Nichts zu holen.

---

## Priorisierte Kandidaten (Vorschlaege — KEINE Entscheidung getroffen)

### A — Hoher Nutzen, klarer Umfang

**A1. Lokale BPM-Map (#2)** — strukturell relevant fuer den echten Use-Case.
Der Test-Datensatz ist ein 62-min-Psy-Mix; das Fremdsystem misst dort real 92..145 BPM ueber
26 Sektionen. PB Studio behandelt so einen Mix mit EINEM globalen BPM -> Beat-Raster und
Cut-Platzierung driften ueber die Laufzeit. Rohdaten sind bereits da (beat_positions,
pacing_beat_grid.py:289-292). Fremdsystem-Ansatz: 30s-Fenster, beat_track pro Fenster,
Faltung benachbarter Fenster mit +/-3 BPM zu Sektionen.
NUTZEN: hoch (betrifft die gesamte Pacing-Kette). AUFWAND: mittel (neue Spalte/Tabelle +
Analyse-Schritt + Consumer).

**A2. Quellen-Tracking fuer manuelle Overrides (#9)** — Datenverlust-Risiko.
Das Fremdsystem hat drei Marker (`bpm_source`, `stimmung_source`, `manual`) und JEDES Skript
respektiert sie. PB Studio hat nichts Vergleichbares fuer analytische Werte: Setzt der User
Mood/BPM/Genre von Hand, ueberschreibt die naechste Analyse ihn stillschweigend.
TimelineEntry.locked schuetzt nur die Timeline-Platzierung.
NUTZEN: hoch (verhindert stillen Datenverlust). AUFWAND: klein-mittel (Spalten + Guards in
den Persist-Pfaden).

**A3. Segment-Cache beim Export (#7)** — Zeitgewinn bei Iteration.
Fremdsystem: jeder Cut wird als eigene seg_NNNNN.mp4 vorgerendert und bei Re-Run
wiederverwendet (Cache-Check: Datei existiert UND >1000 Bytes gegen halb-geschriebene
Files). Aendern sich 50 von 1088 Cuts, werden nur 50 neu encodiert.
NUTZEN: hoch beim Tuning (Export dauert bei uns lange). AUFWAND: mittel (Content-Hash pro
Cut + Cache-Verzeichnis + Invalidierung). PASST ZU: unserer bereits vorhandenen
_std_cache-Idee, die aber nur innerhalb EINES Laufs greift.

**A4. Watermark-Erkennung (#1)** — bei AI-Material real.
Fremdsystem fand 87 von 745 Clips (12%) mit Sora/Runway/Pika/Kaiber/Midjourney/Luma/
Haiper-Wasserzeichen und filtert sie aus der Auswahl. Der User arbeitet mit AI-generierten
Clips -> betrifft uns direkt. Ein Wasserzeichen im fertigen Musikvideo ist ein harter Fehler.
NUTZEN: hoch (Qualitaet des Endprodukts). AUFWAND: mittel (OCR-Modell + Feld + Filter).
ACHTUNG: deren OCR laeuft ueber Florence-2 auf einer 16-GB-GPU. Bei uns muesste geklaert
werden, womit (Florence-2? EasyOCR? Tesseract?) und ob es auf die GTX 1060 passt.

### B — Groesserer Bau, hoher kreativer Hebel

**B1. Cluster-Signaturen (#4)** — Voraussetzung fuer B2.
Fremdsystem aggregiert pro Cluster: avg_motion + std, motion_distribution, mood_distribution
+ dominant_mood, avg_hue (RINGFOERMIG gemittelt — RGB->HSV->Circular Mean, wichtig weil Hue
zyklisch ist), avg_saturation/brightness, color_temperature (warm/cool/neutral),
energy_score = 0.6*motion + 0.25*brightness + 0.15*saturation.
Unsere centroids liegen im UMAP-Raum und sind NICHT interpretierbar — genau die Luecke.

**B2. Kapitel + Themen + Transition-Matrix (#6)** — die eigentliche Dramaturgie.
Fremdsystem v6: 20 Cluster -> 4 narrative Themen (gothic_demonic / neon_cyber_rave /
mystic_nature / ethereal_water), Kapitel von 240s Ziellaenge an Energie-Meilensteinen
ausgerichtet, Transition-Matrix regelt erlaubte Themen-Folgen. Ergebnis: 14 Kapitel ueber
62 min. Das ist der Unterschied zwischen "Clips passen zur Musik" und "das Video erzaehlt
etwas".
NUTZEN: hoch (Dramaturgie ueber die volle Laenge). AUFWAND: gross. BRAUCHT: B1.

**B3. Visual-Flow als Kette (#3)** — wir haben den Bonus, nicht die Kette.
style_compat() bewertet bereits Aehnlichkeit zum Vorgaenger (w_style). Fremdsystem geht
weiter: 60% Chance dass der naechste Clip AUS DEN NACHBARN des vorherigen kommt (v3), bzw.
Score +150 fuer direkte Nachbarn / +50 fuer Distanz-2 (v6). Zusaetzlich Bridge-In/Out:
+300..400 fuer Nachbarn eines manuellen Ankers -> Uebergaenge in Anker rein/raus sind
visuell verbunden. Deren Coherence-Metrik: % Cuts in einer Kette (v6: 100%).
PASST ZU: unseren AudioVideoAnchor (Bridge-Idee direkt uebertragbar).

**B4. Volle Clip-Laenge (#11)** — gekippte Grundannahme.
v6-Einsicht: "Clip-Material wird wertvoller, wenn man es GANZ spielt statt es nach 3
Sekunden zu zerschneiden." Ergebnis: 415 statt 1088 Cuts. Bei uns kommt seg_duration
ausschliesslich aus der Beat-Logik; vid_duration ist nur ein Sicherheits-Clamp.
NUTZEN: mittel-hoch (Charakter des Videos). AUFWAND: mittel. RISIKO: aendert das
Schnittbild grundlegend -> als OPTION bauen, nicht als Default.

**B5. Hero-Cluster (#5)** — visueller roter Faden.
Ein designierter Cluster erscheint deterministisch: Opening, alle 8 Phrasen, an
Struktur-Grenzen, bei Drops. Wir haben role="hero" nur als Einzelclip-Kategorie.
NUTZEN: mittel. AUFWAND: klein-mittel (wenn B1 existiert).

### C — Interessant, aber geringerer Hebel

- **3-Frame-Captions (first/mid/last)** statt nur Mitte — deren inhalt_first/inhalt_last
  dienen Stimmungs-Refinement und Continuation-Anknuepfung.
- **Personen-Zaehlung** aus Objekt-Liste (grobe Heuristik, 0..10).
- **Goldener Winkel fuer Cluster-Farben**: `hsl((cid * 137.5) % 360, 60%, 55%)` — maximale
  visuelle Trennung benachbarter IDs. Kleiner, huebscher Trick fuer unsere UI.
- **Coherence-Metrik** als Qualitaets-Kennzahl eines Schnitts.

---

## Nicht relevant fuer uns

- **Stage 8 (Qwen + WAN-i2v Continuation)** — Video-GENERIERUNG, nicht Schnitt. Zudem im
  Fremdsystem selbst als "experimentell, kein produktiver Teil" markiert, mit
  Identity-Drift-Problem und 2h/Clip ohne Lightning-LoRA. Deren VRAM-Bedarf (13 GB) sprengt
  die GTX 1060 (6 GB) ohnehin.
- **Stage 9 (Frontmatter-Utilities)** — loest Probleme, die es nur gibt, weil der Zustand in
  YAML-Dateien liegt. Wir haben eine DB.
- **Stage 7 (Canvas-Storyboard)** — deren Ersatz fuer eine fehlende GUI. Wir haben eine
  echte Timeline mit AudioVideoAnchor.
- **ffmpeg-Pipe statt librosa.load** — deren Workaround fuer Windows+Python 3.14. Wir sind
  auf Python 3.10, librosa laeuft.

---

## Status

Analyse abgeschlossen, KEIN Code geaendert. Alle Kandidaten sind Vorschlaege — Auswahl und
Reihenfolge entscheidet der User. Nichts davon ist beauftragt.
