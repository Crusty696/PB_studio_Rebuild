# TEST-SKRIPT: TEIL 3 — VIDEO-ANALYSE (~150 CLIPS)

Beachte die Dateien `00_Basis_Regeln.md` und `01_Setup_und_Parameter.md`.
**EISERNE REGEL:** Alles über die sichtbare GUI im Vordergrund. Kein Headless.

---

## ZUERST: DIE DREI FRAGEN (siehe 01)

1. „Wie lautet der vollständige Pfad zur Audio-Datei (MP3/WAV/FLAC)?" → `AUDIO_PFAD`
2. „Wie lautet der Pfad zum Ordner mit den Video-Clips (MP4/MOV)?" → `VIDEO_ORDNER`
3. „Wie soll das Test-Projekt heißen?" → `PROJEKT_NAME`

Danach Parameter prüfen und App sichtbar starten (Schritte B + C aus `01`).

---

## ZIEL

Teste ausschließlich die **Video-Analyse** über alle ca. 150 Clips:
NVENC-Proxies, Szenen-Erkennung (PySceneDetect), Motion-Scoring (RAFT),
SigLIP-Embeddings und Keyframes. Ignoriere Audio-Inhalte und Schnitt.

---

## VORBEREITUNG

1. PB Studio ist sichtbar gestartet, Projekt `PROJEKT_NAME` geöffnet, die ~150
   Clips aus `VIDEO_ORDNER` sind importiert (sonst zuerst importieren wie in `02`).
2. Halte `logs/pb_studio.log` für Beweise bereit (Proxy/SigLIP-Logs).

---

## TEST-SCHRITTE (Der Reihe nach, alles in der GUI)

1. Prüfe im Tab **MATERIAL & ANALYSE**, dass für alle Clips automatisch
   **Proxies** erzeugt werden/wurden.
   - Erwartet: Proxy-Dateien unter `storage/proxies` (je ~2–3 MB), Anzahl passt
     zur Clip-Zahl. Kein „OpenEncodeSessionEx failed".
   - Screenshot: `04_proxies.png`.

2. Starte die **Video-Analyse** für alle Clips (Szenen + Motion + Embeddings).
   - Erwartet: Fortschritt pro Clip sichtbar (z. B. „Pipeline: N Videos",
     Captioning-/Analyse-%), GUI bleibt bedienbar.
   - Erwartet (Ergebnis): pro Clip Szenen erkannt, Motion-Score vorhanden,
     SigLIP-Embedding gespeichert, Keyframe unter `storage/keyframes`.
   - Screenshot bei laufender Analyse: `04_analyse-laeuft.png`.
   - Screenshot nach Abschluss: `04_analyse-fertig.png`.

3. Öffne die **Grid-Ansicht** der Clips und blättere durch mehrere Seiten.
   - Erwartet: Thumbnails/Keyframes werden sichtbar angezeigt.

---

## BEKANNTE SCHWACHSTELLEN PRÜFEN (PFLICHT)

- **B-505 (Proxy-Parallelität):** Beim Import der ~150 Clips entstehen viele
  parallele Proxy-Tasks.
  - Erwartet (Soll): Alle Proxies werden fehlerfrei erzeugt, kein
    „OpenEncodeSessionEx failed" (NVENC-Session-Limit der GTX 1060).
  - Beweis: Datei-Anzahl in `storage/proxies` + Log-Auszug `04_proxy-log.txt`.

- **B-508 / B-NEU-4 (Thumbnail-Threads & leeres Grid):** Blättere im Grid schnell
  durch viele Seiten.
  - Erwartet (Soll): Es laufen **max. 4** Thumbnail-/ffmpeg-Threads gleichzeitig
    (`_THUMB_POOL_MAX_THREADS = 4`), und die Kacheln zeigen tatsächlich Bilder.
  - Bekannt fehlerhaft: Grid-Ansicht blieb komplett LEER (B-NEU-4). Melde genau,
    ob Thumbnails erscheinen oder das Grid leer bleibt. Screenshot:
    `04_grid-ansicht.png`.

- **B-336 (SigLIP fp16 NaN/Inf + VRAM):** Prüfe während der Embedding-Phase das
  Log.
  - Erwartet (Soll): keine NaN/Inf-Warnungen, VRAM-Peak bleibt unter dem
    6-GB-Limit der GTX 1060.
  - Beweis: Log-Auszug `04_siglip-log.txt` (VRAM-/Präzisions-Zeilen).

---

## ABSCHLUSS

Wenn Proxies, Szenen/Motion/Embeddings und Keyframes für alle ~150 Clips
erzeugt wurden und die Bug-Checks (B-505, B-508/B-NEU-4, B-336) dokumentiert
sind, gib aus:

„Teil 3 (Video-Analyse) erfolgreich getestet. Keine weiteren Aktionen nötig."

Bei Fehler stattdessen: „FEHLER in Teil 3: [Schritt + Beobachtung]" und STOPP.
