# Gesamtaudit: Was in PB Studio nichts bewirkt (2026-08-31)

status: agent-analysis-complete-await-user-decisions
auftrag: User — "überprüfe zuerst alles und such parallel nach weiteren Elementen die nur Attrappen sind ... sammle und zeige sie mir alle"
methode: vier parallele Read-only-Analysen, jeder Kernfund vom Hauptagenten einzeln am Code oder an echten Daten gegengeprüft
grundlage: Projekt `Erstlauf_Test_2026-08-30` mit 121 Clips, 147 Szenen, alle 20 Analyseschritte `done`, Auto-Edit gelaufen — kein Fund ist mit "Analyse fehlte" erklärbar

---

## Teil 1 — Was KAPUTT ist (echte Fehlfunktion, nutzersichtbar)

### 1.1 "+ Anker" über den Chat stürzt immer ab

`services/actions/edit/anchor_actions.py:67-71` baut
`ClipAnchor(timeline_entry_id=…, anchor_time=…, scene_id=…)`.
Das Modell kennt diese Felder nicht — es hat `time_offset`, `label`, `color`
(`database/models.py:461-465`).

Selbst verifiziert:

```
TypeError: 'anchor_time' is an invalid keyword argument for ClipAnchor
echte Spalten: ['id', 'timeline_entry_id', 'time_offset', 'label', 'color']
```

Der `except Exception` verwandelt das in `{"error": …}`. **Das erklärt, warum
`clip_anchors` im Projekt 0 Zeilen hat** (selbst gezählt). Die Folgeaktion
`sync_anchors` findet deshalb nie etwas.

### 1.2 Energiekurve und Stem-SNR werden nie geschrieben

Einziger Writer für `audio_tracks.energy_curve` ist `services/audio_service.py:183`,
erreichbar nur über den alten `AnalysisWorker`. `ui/controllers/audio_analysis.py:372-378`
springt bei `audio.v2_default=True` (Default) vorher in die V2-Pipeline, deren
`DEFAULT_STAGE_ORDER` (`stages.py:906-916`) keinen Writer dafür enthält. Dasselbe
Muster bei `acoustic_metadata` (Stem-SNR, B-494).

Selbst verifiziert in der Projekt-DB:

```
energy_curve NULL: True | acoustic_metadata NULL: True | bpm: 130.4 | mood: dark
```

BPM und Mood sind da, die Kurve nicht — obwohl `waveform_analysis` als `done` gilt.
Sichtbare Folgen: Stems-Workspace zeigt "Energie-Kurve — (nicht berechnet)" mit
leerem Plot (`stems_workspace.py:244-250`), die Audio-Kachel malt keine
Mini-Wellenform (`media_grid.py:905`), die Story-Map bekommt leeres
`waveform_energy` (`legacy_sqlite.py:1689`).

### 1.3 Ollama zeigt auf einen Fantasie-Server

`%APPDATA%\PBStudio\settings.json` enthält selbst verifiziert:

```json
"ollama": {"enabled": false, "url": "http://legacy:8080", "model": "legacy-model"}
```

Das sind die Testwerte aus B-924, die bei der Migration aus der Registry in die
JSON gewandert sind — die Registry-Bereinigung vom Vormittag hat sie also nicht
erwischt. Folgen: `tab_pacing_anker.py:200` sperrt die LLM-Checkboxen,
`pacing_strategist.py:340-341` wirft "Ollama ist deaktiviert", und selbst nach
Aktivieren zeigt die URL ins Leere. Erklärt auch die Logzeile beim Start:
"[LLM] Ollama deaktiviert – Fallback aktiv."

### 1.4 Chat-Aktion "Stil-Preset anwenden" meldet Erfolg ohne Wirkung

`services/actions/edit/timeline_actions.py:617-640` liest das Preset aus der DB
und gibt `{"status": "ok", …angewendet: Cut-Rate=…}` zurück — **ohne einen
einzigen Write, ohne Signal, ohne UI-Zugriff**. Der echte Apply-Pfad ist
`edit_workspace.py:1305-1328`. Genau der Fehlertyp, der bei `save_project`
bereits behoben wurde.

### 1.5 Vier Aktionen ohne Worker

`workers/registry.py` registriert 11 Namen. Nicht dabei, aber als Aktion
angeboten: `preview_export` (Worker-Klasse existiert nicht), `auto_ducking`
(Worker existiert, nie registriert), `convert_videos` (Worker existiert, nur der
UI-Pfad nutzt ihn), sowie der `explain_clip`-Fallback. Immerhin: seit `d175a51`
melden sie einen ehrlichen Fehler statt Erfolg. Praktische Folge: Auto-Ducking
und Preview gehen per Knopf, aber nicht per Chat; **Batch-Konvertierung ist
derzeit gar nicht auslösbar**.

### 1.6 Modell-Aufräumen schlägt immer alles vor

`model_registry.last_used_at` bleibt NULL (4 Zeilen, alle leer), weil
`touch_last_used` nur von `ensure_loaded`/`load_ollama` gerufen wird — und die
Analyse SigLIP direkt über `load_siglip()` lädt. Folge: `days_since_used = -1`
für jedes Modell, und `get_cleanup_candidates` (`:903`) behandelt `-1` wie
"lange ungenutzt". Der Spinner "seit N Tagen" ist damit wirkungslos, die Spalte
"Zuletzt benutzt" zeigt immer "Nie".

---

## Teil 2 — Oberfläche, die es gar nicht auf den Schirm schafft

### 2.1 Der CONVERT-Bereich wird nie eingehängt

`ui/controllers/workspace_setup.py:643-646` hängt vier Workspaces in den Stack:
Dashboard, Material, Schnitt, Deliver. **`_convert_ws` fehlt** (selbst
verifiziert: 0 Treffer). Aus ihm wird nur der Button reparentet
(`workflow_pages.py:412-425`). Folge: Beim Standardisieren erscheint kein
Fortschrittsbalken, Fertig- und Fehlermeldungen landen in einem nie gezeigten
Log, und "kein Video im Pool" endet ohne jede Meldung. Einzige Rückmeldung
bleibt der Eintrag im Task-Bereich.

### 2.2 Vorschau und Protokoll im Deliver-Bereich sind dauerhaft unsichtbar

Beide Tabs hängen in `make_expert_container` (`deliver_workspace.py:38-42`),
das per `setVisible(False)` **plus** `WA_DontShowOnScreen` versteckt ist
(`workflow_components.py:98-110`). Selbst verifiziert: **nirgends im Code** wird
dieser Container je sichtbar geschaltet. Folge: Der sichtbare Knopf
"Quick-Preview (10s)" rendert eine Datei, deren Abspielfläche der Nutzer nicht
erreichen kann.

### 2.3 Die Statusleiste im Deliver-Bereich lügt permanent

`StatusStrip.set_status()` (`workflow_components.py:61`) hat selbst verifiziert
**null Aufrufer**. Der sichtbare Streifen zeigt deshalb dauerhaft
"Export bereit, sobald eine Timeline vorhanden ist." — unabhängig davon, ob
gerade exportiert wird, fertig ist oder fehlgeschlagen.

### 2.4 Auflösung und FPS im Projekt-Dialog wirken nirgends

`ui/dialogs/project_dialog.py:133-141` verspricht im Tooltip "Ziel-Aufloesung
fuer Timeline, Vorschau und Export-Voreinstellungen". Die Werte landen in
`Project.resolution`/`fps` — einziger Leser ist ein Info-Dict für Agent-Aktionen
(`project_actions.py:187-188`). Der Export übernimmt sie nie. Zusätzlich passen
die Angebote nicht zusammen: Der Dialog bietet 2560×1440 und 1080×1920, die
Export-Auswahl kennt diese Formate nicht.

### 2.5 Ein guter Tooltip wird laufend überschrieben

`media_workspace.py:434-439` setzt einen ausführlichen Erklärtext für
"Videos standardisieren". `workspace_setup.py:974-982` überschreibt ihn bei
jeder Gate-Auswertung durch einen generischen Sammeltext — der zudem
"Clip-Effekte anwenden" nennt, was zum nie eingehängten Convert-Bereich gehört.

---

## Teil 3 — Irreführend: tut etwas anderes als angekündigt

### 3.1 Neun Einzelschritt-Knöpfe starten immer den ganzen Durchlauf

`media_workspace.py:1623-1665`: `_dispatch_video_analysis` bekommt `step_key`
und liest ihn nie. Der Code sagt es selbst — selbst verifiziert:
"For now, we trigger the full pipeline for any video step."
Ein "Wiederholen" auf einem einzelnen fehlgeschlagenen Schritt rechnet also
alle neun neu. Beim Audio-Pendant ist die Zuordnung dagegen sauber.

### 3.2 Stil-Presets: 6 von 11 Spalten ohne Wirkung

`min_clip_duration`, `max_clip_duration`, `beat_weight`, `kick_weight`,
`snare_weight`, `hihat_weight` haben keinen Leser. Angewandt werden nur
`cut_rate`, `energy_reactivity`, `breakdown_behavior`. "Ambient" (4–15 s) und
"Cinematic" (3–12 s) erzeugen deshalb **identische Clip-Längen**. Der Nutzer
sieht die Regler springen und hält das Preset für wirksam.

### 3.3 Mood und Genre erreichen die Audio-Kachel nie

`media_grid.py:921-928` konstruiert die Karte ohne `mood=`/`genre=`, obwohl die
Daten vorliegen (`ingest_service.py:441-442`) und Filter/Sortierung sie nutzen.
Die Mood-Anzeige (`:568-569`) ist damit unerreichbar.

### 3.4 Die Liste "Letzte RL-Events" bleibt immer leer

`tab_rl_notes.py:61-67`: kein einziger Schreibzugriff im ganzen Repo.

### 3.5 Anker auf Clips ohne Szenen fallen still heraus

"+ Anker" vergibt für solche Clips die Form `clip_<id>`
(`edit_workspace.py:1060`). Der Auto-Edit macht `int(sid)`, bekommt einen
Fehler und verwirft den Anker mit einer reinen Log-Warnung
(`pacing_service.py:1451-1459`) — während die Konsole vorher meldet, mit wie
vielen Ankern gerechnet wird. Der Sync-Pfad kann dieselbe Form korrekt auflösen.

### 3.6 Ungesyncte Anker verschwinden beim nächsten Timeline-Neuladen

"+ Anker" schreibt nur in die Liste; persistiert wird erst per "Sync". Jedes
`load_from_db()` — Undo, Snapshot-Restore, Projektwechsel, Chat-Aktion — leert
die Liste ohne Hinweis.

---

## Teil 4 — Widerlegt: Behauptungen aus älteren Analysen, die NICHT mehr stimmen

Diese standen in der Statusaufnahme vom 2026-07-26 und wurden ungeprüft
weitergereicht. Die zugehörigen Fixes kamen **danach**:

| Behauptung | Wahrheit |
| --- | --- |
| `save_project` meldet Erfolg ohne zu speichern | Seit `d175a51` (2026-07-27) ruft die Aktion real `controller._save_project()`. Historisch war die Kritik korrekt. |
| Gezeichnete Pacing-Kurve ist tot | Seit B-829 (`a26243c`, 2026-08-14) liefert `get_manual_override()` `None`, solange nichts gezeichnet wurde. **Eine gezeichnete Kurve wirkt** — in allen drei Pfaden. Offen bleibt nur, dass sie nicht gespeichert wird (B-837). |
| `embedding_cache.lookup` hat 0 Aufrufer, 554 Embeddings liegen brach | Seit B-707 (`37b840e`) verdrahtet, vier Aufrufer. Real sind es **122** Einträge, alle zugehörigen Dateien vorhanden. Die Zahl 554 ist nicht belegbar. |
| Drei Chat-Aktionen melden fälschlich "Task in Warteschlange" | Die Worker fehlen wirklich, aber seit `d175a51` kommt ein ehrlicher Fehler statt einer Erfolgsmeldung. |

**Konsequenz:** Ältere Analysedokumente in diesem Projekt sind nicht als
Tatsachen zu übernehmen. Was zählt, ist der heutige Code.

---

## Teil 5 — Interner Ballast (kein Nutzer merkt es, kostet aber Pflege)

- **Nie geschrieben und nie gelesen:** `video_clips.video_pipeline_status`,
  `.video_pipeline_checkpoint_path`, `.proxy_status`;
  `ai_pacing_memory.siglip_tags/.bass_energy/.drum_energy`;
  `analysis_jobs.coverage_percent/.started_at/.duration_seconds`;
  `struct_style_bucket.description`
- **Ganze Tabellen ohne Writer:** `hotcues`, `pacing_blueprints`, `step_deps`
- **Leser ohne Writer:** `audio_tracks.spectral_hash` — damit ist der
  Scorer-Term `spectral_fit` strukturell tot, unabhängig vom Studio-Brain-Flag
- **Berechnet und verworfen:** die komplette Sättigungs-Kette (HSV pro
  Keyframe → `avg_saturation` → keine der 18 Achsen liest sie, der Code sagt es
  in `reranker.py:447-449` selbst); `harmonic_tension` im Reranker;
  `JobProgress.result`; `axis_credits` im Feedback-Logger
- **Stub, der etwas anderes behauptet:** `_recover_gpu_error47()`
  (`startup_checks.py:376`) gibt seit D-022 nur `True` zurück, beide Aufrufer
  behaupten in Kommentaren weiter, GPU-Recovery zu machen
- **`agent_feedback`-Lernschleife:** `record_feedback` hat null Aufrufer, der
  Leser bekommt deshalb nie Daten
- **Kleinkram:** toter `accepted`-Connect am Close-Button
  (`ab_compare_dialog.py:77-79`); `media_table` als nie befüllter Legacy-Proxy;
  `preview_time_label` ohne Schreiber; `_stub()`; `_ThumbWorker`

---

## Einordnung: warum es so viel davon gibt

Drei wiederkehrende Ursachen, jede belegbar:

1. **Umbauten ohne Rückbau.** Der Convert-Bereich, die Format-Auswahl (B-929)
   und der Experten-Container sind Reste von Oberflächen-Umbauten, bei denen die
   alte Fassung stehen blieb.
2. **Zwei Pfade, einer wird nicht mitgezogen.** Die V2-Audio-Pipeline schreibt
   `energy_curve` und `acoustic_metadata` nicht mehr, obwohl die Anzeigen sie
   weiter erwarten. Dasselbe Muster beim RL-Feedback (Altpfad statt Brain V3).
3. **Oberfläche vor Datenweg.** Die Studio-Brain-Tabs wurden gebaut, bevor das
   Gate freigeschaltet war — die Freischaltung steht seit April aus.

Was auffällt: Fast nirgends ist der Code *falsch*. Er ist unerreichbar,
abgeschaltet oder redet über etwas, das woanders passiert.

---

## Was zuerst?

Nach Wirkung auf die tägliche Arbeit:

1. **Ollama-Einstellung korrigieren** (1.3) — ein Wert in einer Datei, macht die
   LLM-Funktionen überhaupt erst erreichbar
2. **`add_anchor` reparieren** (1.1) — drei Feldnamen, danach funktionieren
   Anker über den Chat
3. **Energiekurve/SNR in die V2-Pipeline aufnehmen** (1.2) — beseitigt drei
   leere Anzeigen auf einmal
4. **Convert-Bereich einhängen oder Knopf entfernen** (2.1)
5. **Einzelschritt-Knöpfe** (3.1) — entweder je Schritt starten oder ehrlich
   "Alles neu berechnen" beschriften

Nichts davon wurde umgesetzt — alle Punkte sind Produktentscheidungen.
