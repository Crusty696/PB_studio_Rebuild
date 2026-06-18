# TEST-SKRIPT: TEIL 2 — AUDIO-ANALYSE (BEAT & STEMS)

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

Teste ausschließlich die **Audio-Analyse**: Rekordbox-Waveform,
Beat-Detection (`beat_this`, GPU) und Stem-Separation (Demucs `htdemucs_ft`:
Vocals/Drums/Bass/Other). Ignoriere Video und Schnitt.

---

## VORBEREITUNG

1. PB Studio ist sichtbar gestartet. Projekt `PROJEKT_NAME` ist geöffnet und die
   Audio-Datei `AUDIO_PFAD` ist importiert (sonst zuerst importieren wie in `02`).
2. Halte `logs/pb_studio.log` für Beweise bereit (Stem-Chunk-Logs).

---

## TEST-SCHRITTE (Der Reihe nach, alles in der GUI)

1. Öffne im Tab **MATERIAL & ANALYSE** die Audio-/Waveform-Ansicht des Tracks.
   - Erwartet: Rekordbox-Style-Waveform mit Frequenzbändern (Bass/Mid/High) wird
     sichtbar; Statuszeile meldet z. B. „Rekordbox-Analyse fertig".
   - Erwartet: RAM bleibt moderat (Richtwert < 1–2 GB Anstieg). Kein Absturz.
   - Screenshot: `03_waveform.png`.

2. Starte die **Beat-Detection** und warte, bis sie fertig ist.
   - Erwartet: Beatgrid + Struktur-Marker (Intro/Drop/Outro/Buildup/Breakdown)
     erscheinen über der Waveform.
   - Erwartet: GPU wird genutzt (Log nennt `cuda`), kein Fehler.
   - Screenshot: `03_beatgrid.png`.

3. Starte die **Stem-Separation** (Demucs). Beobachte die Chunk-Fortschritte.
   - Erwartet (Log): „Modell 'htdemucs_ft' geladen auf cuda", danach
     „Verarbeite Chunk x/N" der Reihe nach (je 30 s, 2 s Overlap).
   - Erwartet: 4 Stems entstehen unter
     `storage/stems/htdemucs_ft/<Track>/{vocals,drums,bass,other}.wav`.
   - Erwartet: kein MemoryError, kein Crash.
   - Screenshot nach Abschluss: `03_stems-fertig.png`.

4. Öffne den **Stems-Mixer** (im SCHNITT-Audio-Tab oder Stems-Workspace) und
   prüfe, dass die vier Spuren einzeln vorhanden und regelbar sind.
   - Erwartet: Vocals / Drums / Bass / Other getrennt vorhanden.

---

## BEKANNTE SCHWACHSTELLEN PRÜFEN (PFLICHT)

- **B-510 / B-524 / B-507 (Stem-Abbruch hängt + GPU-Lock):**
  Starte die Stem-Separation erneut und klicke nach wenigen Chunks **Abbrechen**.
  - Erwartet (Soll): Der Worker stoppt **innerhalb weniger Sekunden**; der Button
    setzt sofort auf den Ausgangszustand zurück; die GPU-Sperre wird sofort
    freigegeben (ein direkt danach gestarteter Task läuft an).
  - Bekannt fehlerhaft: Worker lief nach Abbruch ~7 Min weiter, Button blieb auf
    „Stems läuft...", Folge-Tasks (z. B. Proxies) standen auf „Running 0%".
  - Miss die Zeit von Klick „Abbrechen" bis tatsächlichem Stopp (CPU-Last sinkt /
    Log „abgebrochen"). Beweis: `03_stem-abbruch-zeit.txt` + Screenshot
    `03_abbruch-button-reset.png`.

- **B-331 (Demucs-Hang bei langem Mix):** Wenn `AUDIO_PFAD` ein langer DJ-Mix ist
  (viele Chunks), beobachte, ob die Separation um Chunk ~51 stehen bleibt.
  - Erwartet (Soll): Alle Chunks laufen durch, kein dauerhafter Hang.
  - Bei Hang: in zweiter Shell `nvidia-smi` prüfen und notieren. STOPP + melden.

---

## ABSCHLUSS

Wenn Waveform, Beatgrid und Stems erzeugt wurden und beide Bug-Checks
(B-510/B-524/B-507 und B-331) dokumentiert sind, gib aus:

„Teil 2 (Audio-Analyse) erfolgreich getestet. Keine weiteren Aktionen nötig."

Bei Fehler stattdessen: „FEHLER in Teil 2: [Schritt + Beobachtung]" und STOPP.
