# Autonomer Erstlauf-Test — vollstaendiger Durchlauf aus dem Werkszustand (2026-08-31)

status: agent-test-complete-await-user-marker
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
tester: Claude (autonom, im Auftrag des Users)
dauer: 2026-08-30 22:53 bis 2026-08-31 00:59

## Auftrag und Aufbau

Der User hatte zuvor alle App-Daten loeschen lassen, um einen echten Erstlauf
zu sehen. Auftrag: App starten, autonom testen, alles aufzeichnen was in der
App passiert.

Bewusst **nicht** verwendet wurde `scripts/run_e2e_gui_test.py` — dieser
Harness war am selben Tag als methodisch wertlos eingestuft worden (jeder
Schritt hinter `if hasattr(...)`, feste `sleep`-Schleifen statt Warten auf
Task-Ende, keine Ergebnispruefung, private Methodenaufrufe statt Klicks).

Stattdessen dreifache Aufzeichnung:

| Datei | Inhalt | Umfang |
| --- | --- | --- |
| `test-report/erstlauf_2026-08-30.log` | Testprotokoll mit Schritten, Beobachtungen, Befunden | 414 Zeilen |
| `test-report/erstlauf_app_2026-08-30.log` | Mitschnitt des App-Logs ab Teststart | 4.159 Zeilen |
| `test-report/erstlauf_prozesse_2026-08-30.log` | neuer `scripts/process_sampler.py`: alle 5 s je Prozess PID/CPU/RSS/Threads plus GPU-Auslastung, VRAM, Temperatur, RAM | 9.437 Zeilen |

Dazu 20 Screenshots unter `tests/qa_artifacts/erstlauf-*`. Bedienung
ausschliesslich ueber echte UIA-Klicks via `tests/gui_harness.py`.

## Durchlaufener Ablauf

1. **App-Start** aus dem Werkszustand: Fenster nach 8,68 s, Statusleiste
   "System bereit | GPU: NVIDIA GeForce GTX 1060 6GB | Ollama | FFmpeg 6.1.1".
2. **Projekt anlegen** ueber den echten Dialog: `Erstlauf_Test_2026-08-30`
   mit `data/`, `exports/`, `storage/`, `pb_studio.db`.
3. **Audio importieren**: Maceo Plex - Sub-Alot, `audio_tracks = 1`.
4. **Audio-Komplettanalyse**, 22:58:42 bis 00:04:50, fehlerfrei:
   Stems (4, htdemucs auf `cuda:0`, 12 Chunks), BPM 130.4 mit 738 Beats,
   Rhythmus (Kick 974 / Snare 1201 / Hihat 1333, Groove house_offbeat),
   Tonart Am, 27 Struktursegmente, LUFS -8.57, Spektrum "Sub Bass",
   Klassifikation Progressive House / Mood dark, Waveform, AV-Pacing-Kurven.
5. **Video-Ordner importieren**: 121 von 125 MP4 (4 uebersprungen, siehe unten).
6. **Video-Komplettanalyse** aller 121 Clips, 23:14:54 bis 23:24:25
   (9 min 31 s, rund 4,7 s je Clip), Nachbearbeitung bis 00:02:42.
   Ergebnis 147 Szenen. Je Clip 7 Schritte inklusive RAFT-Motion,
   SigLIP-Embeddings (1152 Dimensionen) und `structure_enrichment`.
7. **Auto-Edit** ueber die Preset-Karte "House": 54 Segmente in 18 Sekunden,
   Summe 337,14 s = exakt die Audiodauer, 54 verschiedene Clips ohne
   Wiederholung.
8. **Vorschau** und **Export** inklusive Gegenprobe (siehe Befunde).

## Was sauber funktioniert hat

- Die gesamte Analysekette lief ohne einen einzigen Fehler durch: 0 ERROR,
  0 CRITICAL, 0 Traceback ueber beide Analysephasen.
- Die Inhalts-Deduplizierung arbeitet korrekt und begruendet jede
  Ueberspringung einzeln mit SHA und Ziel-ID (B-706/M3). Die 4 nicht
  importierten Dateien sind echte Duplikate.
- Der Export ist solide gebaut: Disk-Vorabcheck (4,2 GB noetig, 74 GB frei),
  Standardisierung der Quellen, dann Stream-Copy statt Neukodierung — deshalb
  2 Minuten statt der geschaetzten 3 Min 4 Sek.
- Die erzeugte Datei trifft die Musiklaenge auf die Millisekunde:
  337.126693 s gegen 337.1 s Audiodauer.
- Die Clip-Auswahl in der Timeline fuellt den Inspector exakt korrekt.

## GPU-Nutzung (Zusatzauftrag des Users)

Ueber 864 Messpunkte im 5-Sekunden-Takt:

- GPU-Auslastung: Maximum 100 %, Mittel 32,1 %, in 47,2 % der Messpunkte > 0 %
- VRAM: Maximum 5.025 von 6.144 MiB, Mittel 2.447 MiB

Auf der GPU (je Modell-Load im Log belegt, ausschliesslich `cuda` / `cuda:0`):
htdemucs, beat_this (nach Gebrauch entladen), SigLIP so400m (einmalig fuer den
121er-Batch vorgeladen), SigLIP2 base, RAFT Small, Ollama/gemma3:4b.

Video-Encoding: NVENC real getestet (echter 1-Frame-Encode, nicht nur
Encoder-Liste): `h264_nvenc` True, `hevc_nvenc` True, `cuda_hwaccel` True.
Die Proxy-Presets (`services/convert_service.py:82-94`) und der
Timeline-Export (`services/export/ffmpeg_runner.py:100-130`) nutzen
`h264_nvenc`; libx264 ist nur Fallback, wenn NVENC fehlt.

Auf der CPU: Szenen-Erkennung (PySceneDetect), Onset/Rhythmus, LUFS,
Spektralanalyse, Songstruktur. Fuer diese Bibliotheken existiert kein
CUDA-Backend; laut GPU-Hartregel ist CPU dort der vorgeschriebene Weg.

**Es wurde kein Fall gefunden, in dem GPU moeglich gewesen waere und die CPU
gerechnet hat.** Null CPU-Fallbacks in diesem Lauf.

## Befunde

| ID | Schwere | Kurz |
| --- | --- | --- |
| B-921 | high | Der gefuehrte Erstlauf-Weg erzeugt ein stummes Video ohne Warnung |
| B-922 | medium | Play-Button der Vorschau ist ein stiller No-Op |
| B-923 | medium | Vorschau zeigt den Einzelclip statt der fertigen Timeline |
| B-924 | medium | Tests schreiben in den produktiven QSettings-Registry-Zweig |
| B-925 | low | "Medien-DB laden" wird nach jedem Einzelschritt neu gestartet |
| B-926 | low | Ollama-Desktop-Anwendung startet sich waehrend des Laufs selbst |

### Der zentrale Befund B-921

Beide Exporte enthielten nur einen Video-Stream (`nb_streams=1`). Ursache: eine
Audiospur entsteht nur ueber `Zur Timeline hinzufuegen` im MATERIAL-Tab; der
Auto-Edit legt ausschliesslich Video-Segmente an. Der Weg ueber die
Preset-Karte fuehrt nirgends an diesem Button vorbei.

Gegenprobe durchgefuehrt: nach dem Hinzufuegen der Audiospur meldet der
EXPORT-Tab `Audio-Tracks: 1`, und der erneute Export enthaelt
`nb_streams=2` (h264 + aac 48 kHz stereo) samt LUFS-Normalisierung auf
-14,0. Die Export-Funktion ist also intakt — die Luecke liegt im gefuehrten
Ablauf, und die App warnt nicht, obwohl sie den Zustand kennt und anzeigt.

### Weitere Beobachtungen ohne eigene Bug-ID

- **Segmentspreizung:** 7 der 54 Segmente liegen unter dem gemeldeten
  Ruhe-Floor von 3,68 s, das kuerzeste bei 1,343 s. Das widerspricht dem
  B-912-Vertrag nicht (Section-Pflichtpunkte duerfen den Floor
  unterschreiten), aber 1,3-Sekunden-Schnitte direkt neben
  9,6-Sekunden-Einstellungen sind eine Produktfrage.
- **Erstlauf braucht Internet:** Der ClapAudioEmbedder fand
  `laion/larger_clap_music` nicht im lokalen Cache und lud aus dem Netz nach.
  Ohne Verbindung faellt dieser Analyseteil beim ersten Start aus.
- **Aufzeichnung:** Der Log-Mitschnitt riss bei der 5-MB-Rotation ab
  (`tail -f` folgte der alten Inode). Nichts ging verloren, die Rotationsdatei
  enthaelt den Abschnitt; der Mitschnitt laeuft seither mit `tail -F`.
- **Power-Events:** Zweimal meldete die App B-433/B-435
  Power-Source-Change mit anschliessendem CUDA-Context-Probe. Beide Male ohne
  erkennbaren Schaden.
- **GUI-Harness:** `click-element --name "Erstellen"` traf das Fenster
  "Neues Projekt erstellen" statt des Buttons (Substring-Match auf den
  Fenstertitel). Gleiche Klasse wie die doppelte `auto_id` im SCHNITT-Header.

## Registry-Bereinigung (User-Freigabe 2026-08-31)

Vor der Loeschung gesichert nach `test-report/registry_backup_2026-08-31/`
(vier `.reg`-Exporte). Die App wurde zuvor beendet, damit sie die Werte nicht
zurueckschreibt. Entfernt: `HKCU\Software\PBStudio`,
`HKCU\Software\PB Studio`, `HKCU\Software\PBStudioTest`,
`HKCU\Software\PBStudioLiveTest`. Kontrolle danach: keine PB-Zweige mehr unter
`HKCU\Software`.

Damit ist der Werkszustand jetzt tatsaechlich vollstaendig — beim naechsten
Start sollten SetupWizard und Onboarding erscheinen. Die Ursache (B-924) ist
damit nicht behoben, nur ihre Folge beseitigt.

## Grenzen dieses Tests

- Kein Usermarker: alle Statuswerte bleiben agentseitig.
- Die exportierten Videos wurden technisch per `ffprobe` geprueft, aber nicht
  angesehen. Ob der Schnitt musikalisch ueberzeugt, ist damit offen.
- Der Export lief mit Stream-Copy; ein Lauf mit echter Neukodierung
  (abweichende Aufloesung/FPS) wurde nicht getestet.
- Cancel-, Retry- und Fehlerpfade wurden nicht provoziert.
