# Fixplan: Schnitt / Clip-Auswahl / Thumbnails / Timeline-UI

- **Plan-ID:** PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07
- **Status:** `in_progress` — User-Freigabe 2026-07-07 („ja setzte deinen plan jetzt", autonome Abarbeitung 1–9). Registriert in PLAN_REGISTRY, aktiv via ACTIVE_PLAN.md, Decision D-063.
- **Erstellt:** 2026-07-07, Agent Claude (Fable 5), Read-only-Analyse-Session
- **Untersuchte Artefakte:**
  - Finales Render-Video: `outputs/final-check/exports/output.mp4` (675 MB)
  - Session-Logs: `outputs/app_run_2026-07-06_232559_err.log` (23:26–00:32),
    `outputs/app_run_2026-07-07_005551_err.log` (00:55–01:12), `logs/pb_studio.log(.1)`,
    Clicklogs `logs/clicklog_2026-07-07_*.log`
  - Projekt-DB: `outputs/final-check/pb_studio.db`
  - Timeline-Export: `exports/auto_edit_phase3.otio`
  - Code: `services/pacing_service.py`, `services/pacing_edit_helpers.py`,
    `services/video_analysis_service.py`, `ui/timeline.py`, `ui/timeline_thumbnail_loader.py`

---

## Teil A — Befunde (verifiziert aus Logs, DB und Code)

### A0. BLOCKER: App startet aktuell nicht mehr (dirty worktree)

`main.py` ist im Worktree uncommitted veraendert und **syntaktisch kaputt**:
in `setup_logging()` wurden 12 Zeilen entfernt, ein Fragment der
`_JsonFormatter`-Klasse blieb stehen. Folge:

```
File "main.py", line 1195
    def format(self, record: ...) -> str:
IndentationError: unexpected indent
```

Alle App-Starts seit 01:14 Uhr scheitern sofort (0-Byte-Logs `app_run_2026-07-07_011406/011618/011805`).
Zusaetzlich ist `start_pb_studio_clicklog.bat` uncommitted umgebaut (eigenstaendiger
Launcher mit `PB_LOG_LEVEL=DEBUG` statt Delegation an `start_pb_studio.bat`).
Verursacher unbekannt (nicht committed, nicht im Log dokumentiert).
`tools/agent_start.ps1` meldet dadurch `BLOCKED`.

### A1. Gesamtlaenge des Renders ist korrekt

`output.mp4`: Video 307.91 s, Audio 308.0 s — Audio-Datei
(`Krama - Wrath Of Light`, 308 s, 143 BPM, Psy-Trance) gibt die Laenge vor, und der
finale Render haelt sie ein. Das Laengen-Problem liegt **nicht** im Render, sondern
im Timeline-Zustand davor (siehe A2).

### A2. „Zu viele Clips in der Timeline"

Ablauf laut DB + Clicklog der Session 00:55–01:12:

| Zeitpunkt | Timeline-Inhalt | Quelle |
|---|---|---|
| 00:57:11 (Projekt-Open) | **98 Eintraege** (59 vom Auto-Edit der Vorsession + 39 Voll-Clips + Audio) | DB-Altbestand |
| 00:57:43 | User klickt „Alle" → „Zur Timeline hinzufuegen" → **+39 Voll-Clips** (je ~8 s, hintereinander ans Ende) → 137 Items | `add_to_timeline` haengt jeden Clip ans Ende (`edit_actions.py:607ff`) |
| 00:58:45 Auto-Edit | Pacing erzeugt korrekt **58 Segmente fuer 308 s** | `pacing_service` |
| 00:59:34 Apply | Timeline wird ersetzt: **58 Video + 1 Audio = 59** (DB verifiziert) | `ApplyAutoEditCommand` |

Der Auto-Edit selbst setzt also die richtige Anzahl (58 Segmente, Summe exakt 308 s).
Das „zu viele Clips"-Erlebnis entsteht durch den Workflow davor: Material muss
(scheinbar) erst komplett in die Timeline gelegt werden, dadurch liegen dort
39 Voll-Clips (~312 s zusaetzlich) plus Reste des letzten Auto-Edits, bis Apply
alles ersetzt. Es fehlt ein klarer Mechanismus/UI-Hinweis: Auto-Edit arbeitet auf dem
**Material-Pool**, nicht auf der Timeline — das Einfuegen aller Clips ist unnoetig
und macht die Timeline unlesbar.

### A3. „Immer die gleichen Clips" — Auswahl-Mechanik defekt

DB-Fakten (Projekt final-check, 39 analysierte Videos, 42 Szenen):

- Lauf 1 (00:14): 58 Segmente mit **1 einzigen Video** (registered_paths=1).
- Lauf 2 (00:59): 58 Segmente mit nur **17 von 39 Videos**; Top-2-Videos je **8×** verwendet.

Ursachenkette (Code-verifiziert):

1. **Motion-Scores gesaettigt:** `_raft_motion_score()` normalisiert mit
   `min(1.0, raw / 40.0)` (`video_analysis_service.py:208`). Ergebnis: **41 von 42
   Szenen haben motion_score = 1.0** (DB: `scenes.energy`). Damit ist
   `energy_match` (Gewicht 0.25–0.30) fuer alle Kandidaten identisch —
   die RAFT-Analyse-Daten werden zwar formal verwendet, tragen aber **null
   Unterscheidungskraft** bei.
2. **Deterministischer argmax:** `_match_video_for_segment()` nimmt immer den
   hoechsten Fitness-Score. Bei totem energy_match dominiert der statische
   SigLIP-Mood-Score aus der Fitness-Matrix → dieselben „besten" Clips gewinnen
   immer wieder.
3. **Freshness zu schwach:** Nur die letzten 3–5 Verwendungen zaehlen
   (`used_recently[-3:]`/`[-5:]`), Gewicht nur 0.10–0.15. Ein Top-Clip ist nach
   3 Segmenten wieder „frisch". Keine globale Nutzungs-Obergrenze, keine
   Garantie, dass der Pool durchrotiert wird.
4. **Nur 1 Szene pro Video** (36 von 39 Videos): 8-s-Clips ergeben eine Szene mit
   `source_start=0` → wiederholte Clips zeigen zusaetzlich immer denselben
   Bildausschnitt ab Sekunde 0.

### A4. Analyse-Daten teilweise unbrauchbar (Datenqualitaet)

Alle Analyse-Steps stehen in `analysis_status` auf `done` (39/39 Videos:
scene_detection, motion_scores, siglip_embeddings, ai_scene_caption, …) — aber:

- `scenes.energy` (= motion_score): 41/42 identisch 1.0 (siehe A3.1).
- `scenes.ai_caption`: enthaelt **JSON-Metadaten-Muell** statt Beschreibung, z. B.
  `{"type": "image/jpeg", "url": "file:///p...`. Das Vision-Modell (Ollama) hat
  Metadaten geechot; das Tolerant-Parsing in `analyze_scenes_with_vision()`
  (`video_analysis_service.py:858ff`) akzeptiert jedes Dict ohne Plausibilitaets-
  pruefung. `ai_mood` bleibt dadurch NULL.
- `scenes.embedding_indices`: alle NULL — Szene↔Embedding-Verknuepfung wird nie
  geschrieben (Embeddings existieren nur im Vektor-Store).
- `scene_index`: NULL in der DB.

Konsequenz: Von den 5 Fitness-Dimensionen sind Energy (konstant) und Mood
(Audio-Mood-Anteil ok, Caption-Anteil Muell) beschaedigt — „Analyse-Daten werden
verwendet" stimmt formal, aber ihre Aussagekraft ist grossteils zerstoert.

### A5. Thumbnails erscheinen nicht

`ThumbnailLoadManager` (`ui/timeline_thumbnail_loader.py`) merkt sich fertige
Pfade in `_done` **prozessweit dauerhaft**. `_on_thumb_ready()` (`ui/timeline.py:1433`)
setzt das Pixmap nur auf die **momentan registrierten** Items und cached es nicht.
Nach jedem Timeline-Rebuild (Auto-Edit-Apply, Projekt-Reload) sind alle Clip-Items
neu, `request()` wird wegen `is_done()` zum No-Op → **Platzhalter bleiben fuer immer**.

Log-Beweis (Session 00:55): vor Apply werden 39 Thumb-Worker gestartet; nach dem
Apply-Rebuild (00:59:35, 59 neue Items) ausschliesslich
`request_visible: … new_requests=0 inflight=0` — kein einziges Thumbnail wird auf
die neuen Items angewendet.

### A6. Clip-Felder zu klein

`ui/timeline.py`: `TRACK_HEIGHT = 80`, `PIXELS_PER_SECOND = 20`. Ein typisches
5-s-Segment ist damit ~100 px breit und 80 px hoch, Thumbnail max. 74 px hoch —
zu klein zum Erkennen des Inhalts. Regel B-525 gilt: vor UI-Redesign erst
recherchieren, wie Profi-Software (Premiere, Resolve, FCP) Track-Hoehen,
Zoom-Stufen und Thumbnail-Filmstreifen loest.

---

## Teil B — Plan (jeder Schritt einzeln, mit Vorgehen und Auswirkungen)

> Reihenfolge = Ausfuehrungsreihenfolge. Nach jedem Schritt: Import-/Unit-Test,
> App-Start + realer Klickpfad, Log-Auswertung, Vault-Eintrag, Commit.
> Kein Schritt beginnt ohne dein OK zum Plan; Schritt 0 braucht zusaetzlich
> deine Einzel-Entscheidung, weil er Worktree-Zustand verwirft/behaelt.

### Schritt 0 — Worktree-Blocker aufloesen (BRAUCHT DEINE ENTSCHEIDUNG)

- **Was:** Entscheidung ueber die zwei uncommitted Dateien:
  - `main.py`: kaputt (App startet nicht). Vorschlag: **verwerfen**
    (`git restore main.py`) → letzter committeter Stand ist intakt.
  - `start_pb_studio_clicklog.bat`: funktional umgebaut (DEBUG-Logging).
    Vorschlag: entweder verwerfen oder als eigener Commit sichern — deine Wahl.
- **Warum:** `agent_start.ps1` = BLOCKED; ohne lauffaehige App keine
  Live-Verifikation irgendeines Folgeschritts.
- **Auswirkung:** App startet wieder. Verlust: nur die kaputte main.py-Aenderung.
- **Risiko:** Keines bei restore (Commit-Stand war der, mit dem die Session
  00:55 lief — dort startete die App).
- **Verifikation:** `python -c "import main"` + App-Start + Log zeigt normalen Boot.

### Schritt 1 — Motion-Score-Normalisierung reparieren (Root-Cause A3.1/A4)

- **Was:** `_raft_motion_score()` so normalisieren, dass reale Differenzierung
  entsteht. Vorgehen: auf dem vorhandenen Testmaterial (39 Videos) die rohen
  RAFT-Magnituden loggen/messen, dann Skala datenbasiert festlegen
  (z. B. tanh- oder Perzentil-Skalierung statt hartem `min(1.0, raw/40)`).
  Zusaetzlich Diagnose-Log der Rohwerte (raw px) pro Szene.
- **Warum:** 41/42 Szenen = 1.0 → Energy-Matching wirkungslos; das ist die
  Kernursache dafuer, dass die Musik-Energie die Clip-Wahl nicht steuert.
- **Auswirkung:** Motion-Scores streuen wieder (0.1–0.9), Energy-Match
  unterscheidet Kandidaten. **Erfordert Re-Analyse** des Motion-Steps fuer
  bestehende Projekte (Schritt 5).
- **Risiko:** Skala falsch gewaehlt → wieder Saettigung; darum datenbasiert +
  Unit-Test mit ruhigem vs. schnellem Fixture-Video.
- **Verifikation:** Nach Re-Analyse: `SELECT DISTINCT energy FROM scenes` zeigt
  Streuung; Log zeigt Rohwerte.

### Schritt 2 — Vision-Caption-Validierung (A4)

- **Was:** In `analyze_scenes_with_vision()` Plausibilitaetspruefung vor
  `scene.ai_caption = parsed`: `description` muss natuerlichsprachlicher Text
  sein (kein Metadaten-Echo: Reject bei Keys/Mustern wie `"type": "image/…"`,
  `"url":`, leerer/zu kurzer Text). Bei Reject: Retry mit Plain-Text-Prompt,
  sonst Szene ohne Caption lassen + WARNING loggen statt Muell speichern.
- **Warum:** Muell-Captions vergiften Mood-Daten (`ai_mood` NULL, Beschreibung
  unbrauchbar) und jede kuenftige semantische Suche.
- **Auswirkung:** `scenes.ai_caption/ai_mood` enthalten nur noch validierte
  Werte; Steps melden ehrlich, wenn das Vision-Modell versagt.
- **Risiko:** Zu strikte Validierung verwirft brauchbare Captions → Grenzwerte
  konservativ, Unit-Tests mit echten Gut-/Schlecht-Beispielen aus der DB.
- **Verifikation:** Re-Analyse-Lauf: keine JSON-Metadaten-Strings mehr in
  `scenes.ai_caption` (DB-Query), Anteil captioned Szenen im Log.

### Schritt 3 — Clip-Auswahl diversifizieren (A3)

- **Was:** Drei gezielte Aenderungen in `pacing_edit_helpers.py`:
  1. **Globale Nutzungs-Obergrenze:** max. Verwendungen pro Video =
     `ceil(anzahl_segmente / anzahl_videos) + 1` (bei 58/39 → max 3). Kandidaten
     am Limit werden uebersprungen, solange Alternativen existieren.
  2. **Freshness verstaerken:** statt Fenster-3/5 eine abklingende Strafe
     proportional zur bisherigen Nutzungszahl des Videos (global, nicht nur
     letzte 5), Gewicht anheben.
  3. **Top-K-Sampling statt argmax:** aus den besten K=3–5 Kandidaten
     score-gewichtet wuerfeln (mit festem Seed pro Run fuer Reproduzierbarkeit)
     — verhindert, dass ein statischer Spitzenreiter jedes Segment gewinnt.
- **Warum:** Selbst mit reparierten Scores bleibt deterministischer argmax +
  Kurzzeit-Freshness strukturell wiederholungsanfaellig (Beweis: Lauf mit
  1 Video fuer 58 Segmente).
- **Auswirkung:** Auto-Edit nutzt den Material-Pool breit (Ziel: bei 39 Videos
  und 58 Segmenten ≥ 30 verschiedene Videos, keines > 3×). Ergebnis variiert
  kontrolliert zwischen Runs (Seed).
- **Risiko:** Zu harte Diversitaet kann Mood-Passung verschlechtern → Gewichte
  so setzen, dass Cap nur bei vorhandenen Alternativen greift; A/B-Sichtung
  durch dich als Live-Test.
- **Verifikation:** Unit-Test (Verteilungs-Assertions) + realer Auto-Edit-Lauf:
  DB-Query `SELECT media_id, COUNT(*) FROM timeline_entries … GROUP BY media_id`.

### Schritt 4 — Szenen-Vielfalt bei Ein-Szenen-Videos (A3.4)

- **Was:** Wenn dasselbe Video mehrfach gewaehlt wird, `source_start` variieren:
  pro Wiederholung anderen Startpunkt innerhalb der Video-Dauer waehlen
  (unter Beruecksichtigung der Segment-Laenge), statt immer Szene-Start 0.0.
- **Warum:** 36/39 Videos haben genau 1 Szene → Wiederholungen zeigen aktuell
  identisches Material ab 0 s.
- **Auswirkung:** Auch wiederholte Videos wirken visuell unterschiedlich.
- **Risiko:** Startpunkt kann in unguenstigen Bildbereich fallen — akzeptabel,
  da besser als identischer Frame; spaeter durch echte Sub-Szenen-Erkennung
  ersetzbar (nicht Teil dieses Plans).
- **Verifikation:** DB-Query auf `source_start`-Streuung bei mehrfach genutzten
  `media_id`s + Sichtpruefung im Preview.

### Schritt 5 — Re-Analyse-Pfad fuer bestehende Projekte

- **Was:** Motion-Step (und optional Caption-Step) fuer das Projekt final-check
  neu ausfuehrbar machen: gezieltes Zuruecksetzen der betroffenen
  `analysis_status`-Eintraege (`motion_scores`, `ai_scene_caption`) + Re-Run
  ueber die vorhandene Analyse-Pipeline (GPU: RAFT auf cuda:0, wie gehabt).
  Keine Schema-Aenderung.
- **Warum:** Schritte 1–2 wirken sonst nur fuer neu importiertes Material;
  der Testdatensatz muss korrigierte Werte bekommen, damit Schritt 3/4
  verifizierbar ist.
- **Auswirkung:** `scenes.energy` + Captions des Testprojekts werden echt.
  Dauer: Motion-Re-Analyse 39 Videos (RAFT, GTX 1060) — erwartbar Minuten,
  kein Stunden-Lauf.
- **Risiko:** GPU-Last/VRAM wie bei normaler Analyse; laeuft ueber bestehende
  Worker-Pfade (kein neuer GPU-Code).
- **Verifikation:** `analysis_status` wieder `done`, Energy-Streuung in DB.

### Schritt 6 — Thumbnail-Fix in der Timeline (A5)

- **Was:** Pixmap-Cache im `TimelineView`: `_on_thumb_ready()` legt
  `dict[path → QPixmap]` an; `_register_clip_thumbnail()` wendet gecachte
  Pixmaps sofort auf neue Items an. `is_done()`-Dedup im Loader bleibt
  (verhindert weiterhin ffmpeg-Sturm), aber „done" heisst jetzt „Pixmap im
  Cache verfuegbar", nicht „nie wieder anzeigen".
- **Warum:** Root-Cause A5 — nach jedem Rebuild verhungern neue Items, weil
  der Loader fertige Pfade nie erneut liefert.
- **Auswirkung:** Thumbnails erscheinen nach Auto-Edit-Apply, Projekt-Reload
  und Scroll zuverlaessig; kein Mehraufwand an ffmpeg-Prozessen (Cache-Hit).
  Speicher: ~59 × (220 px-Pixmap) — vernachlaessigbar.
- **Risiko:** Cache-Invalidierung bei geaenderter Quelldatei — Cache pro
  Session, bei Projekt-Switch leeren (an bestehendes `reset()` koppeln).
- **Verifikation:** Live: Auto-Edit ausfuehren → Thumbnails sichtbar auf allen
  Segmenten; Log zeigt Cache-Hits statt `new_requests=0`-Verhungern.

### Schritt 7 — Timeline-Workflow „zu viele Clips" (A2) — Variante V3 (USER-ENTSCHEIDUNG 2026-07-07)

User-Vorgabe statt V1/V2: keine Warnungen — die App gibt nur so viele Clips
weiter wie wirklich gebraucht werden, und macht Verwendung sichtbar.

- **Was:**
  1. **Auto-Edit braucht kein Timeline-Vorbefuellen:** Auto-Edit arbeitet
     (wie schon heute) auf dem Material-Pool; die Timeline erhaelt
     ausschliesslich die N benoetigten Segmente. „Zur Timeline hinzufuegen"
     ist fuer Auto-Edit nicht noetig und bleibt reine Manuell-Funktion.
  2. **Farbliche Markierung im Material-Grid:** Nach einem Auto-Edit werden
     im MATERIAL & ANALYSE-Grid die Clips markiert, die im aktuellen
     Schnitt verwendet wurden (z. B. gruener Rahmen/Badge mit
     Verwendungszahl) vs. unverwendet (neutral/gedimmt).
  3. **Auswahl-Steuerung:** Der User kann vor dem Auto-Edit per Selektion
     bestimmen, welche Clips zur Verfuegung stehen (manuelle Vorauswahl),
     oder nichts selektieren — dann entscheidet die App (ganzer Pool).
     Ein Hinweis-Label am Auto-Edit-Button erklaert genau das.
- **Warum:** Die 98/137-Clip-Zustaende entstanden aus dem Workflow
  (Alle→Hinzufuegen→Auto-Edit), nicht aus dem Pacing. Der Pacing-Output selbst
  (58 Segmente = 308 s) ist korrekt.
- **Auswirkung:** Timeline enthaelt nach Auto-Edit exakt N Segmente; User sieht
  im Grid sofort, welche Clips der Schnitt nutzt; Vorauswahl moeglich ohne
  Timeline zu fluten.
- **Risiko:** Grid-Markierung erfordert Rueckkanal Auto-Edit→Media-Grid;
  isoliert per Signal/DB-Query loesbar, kein Eingriff in Pacing-Kern.
- **Verifikation:** Realer Klickpfad: Projekt oeffnen → Auto-Edit → Timeline
  zeigt exakt N+1 Eintraege; Grid markiert verwendete Clips; Vorauswahl von
  z. B. 10 Clips fuehrt zu Auto-Edit nur aus diesen 10.

### Schritt 8 — Clip-Felder vergroessern (A6) (RECHERCHE ZUERST, DANN DEIN OK)

- **Was:** Erst Recherche gemaess Regel B-525 (wie loesen Premiere/Resolve/FCP
  Track-Hoehe, Zoom-Stufen, Filmstreifen-Thumbnails), dann konkreter Vorschlag:
  voraussichtlich `TRACK_HEIGHT` anheben (z. B. 80→110), verstellbare
  Track-Hoehe und/oder hoehere Default-`PIXELS_PER_SECOND` mit „Fit"-Zoom als
  Start-Ansicht; Thumbnail-Hoehe folgt `TRACK_HEIGHT`.
- **Warum:** 80 px Hoehe / 20 px pro Sekunde macht Segmente unlesbar klein.
- **Auswirkung:** Bessere Erkennbarkeit; beruehrt Layout-Konstanten, Waveform-
  Zeichnung und Handle-Positionen in `ui/timeline.py` — reine UI-Schicht.
- **Risiko:** Folge-Layout-Fehler (Ueberlappung Audio/Video-Track) → nach
  Recherche kleiner, isolierter Patch + Screenshot-Verify.
- **Verifikation:** GUI-Sichtpruefung/Screenshot, Klickpfad Zoom/Fit/Trim.

### Schritt 9 — End-to-End-Live-Verifikation (Abschluss-Gate)

- **Was:** Kompletter realer Durchlauf mit dem Standard-Testset: Projekt neu,
  39 Videos importieren, Analyse, Auto-Edit, Sichtpruefung Timeline
  (Thumbnails, Feldgroesse, Clip-Anzahl), finaler Render (NVENC), ffprobe.
- **Messbare Abnahme-Kriterien:**
  1. Timeline nach Auto-Edit: exakt N Segmente, Summe = Audio-Dauer ±0.1 s.
  2. Verwendete Videos ≥ 75 % des Pools; kein Video > `ceil(N/Pool)+1`-mal.
  3. `scenes.energy` streut (nicht > 50 % identische Werte).
  4. Keine Metadaten-Strings in `ai_caption`.
  5. Thumbnails auf allen sichtbaren Segmenten nach Apply + nach Reload.
  6. Render-Dauer = Audio-Dauer; Encode via h264_nvenc (Log-Beweis).
- **Status danach:** `code-fix-pending-live-verification` → `fixed` setzt nur
  der User nach eigener Sichtung.

---

## Teil C — Governance / Entscheidungen (beantwortet durch User 2026-07-07)

1. **Schritt 0:** ERLEDIGT. `main.py` per git restore verworfen (0a).
   `start_pb_studio_clicklog.bat` behalten + repariert (0b, Commit 7f46b72):
   PB_CLICK_LOG-Env-Var-Mismatch gefixt, PB_LOG_LEVEL-Support in main.py
   ergaenzt, [KEY]-Logging hinzugefuegt (User wollte Voll-Aufzeichnung).
2. **Plan-Autoritaet:** User: „ja setzte deinen plan jetzt" → registriert in
   PLAN_REGISTRY (`in_progress`), ACTIVE_PLAN.md zeigt auf diesen Plan,
   Decision D-063 + Vault-Mirror angelegt. OTK-021 pausiert.
3. **Schritt 7:** User waehlt eigene Variante **V3** (keine Warnungen; nur
   benoetigte Clips weitergeben, farbliche Verwendungs-Markierung im Grid,
   manuelle Vorauswahl ODER App entscheidet) — eingearbeitet oben.
4. **Schritt 8:** Recherche zuerst, dann Umsetzung — User: „mach direkt alles,
   aber mach zuerst die recherchen".
5. **Umfang:** Alle Schritte 1–9, autonom komplett durcharbeiten.

## Teil D — Ausdrueckliche Nicht-Ziele

- Kein Austausch von Modellen/Libraries (RAFT, SigLIP, Ollama bleiben).
- Keine GPU-Backend-Aenderung (GTX 1060 / cuda:0 / NVENC unveraendert).
- Kein Timeline-Redesign ueber Schritt 8 hinaus, keine „While-I'm-here"-Fixes.
- Keine Schema-Migrationen der DB.
