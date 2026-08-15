# Übergabe: Claude Code → Codex, 2026-08-15

> **Für Codex: lies dieses Dokument vollständig, bevor du irgendetwas anfasst.**
> Es beschreibt, was in dieser Sitzung passiert ist, was gilt, was noch offen
> ist — und welche Fehler ich gemacht habe, damit du sie nicht wiederholst.

**Stand:** Commit `d242987` auf `main`, synchron mit `origin/main`.
**Vorgänger-Checkpoint dieser Sitzung:** `dd5d228`. Insgesamt **26 Commits**.

> **Sitzungsende:** Diese Sitzung endete am 15.08.2026 nach einem
> **Bluescreen** des Rechners (gegen 12:00). Es ging nichts verloren — alle
> Änderungen wurden danach geprüft, committet und gepusht (Details in
> Abschnitt 10). Die App läuft seitdem **nicht** mehr. Der Nutzer wechselt
> jetzt zu dir.

---

## 0. Worktree-Zustand — bitte zuerst lesen

`git status --short --branch` liefert:

```
## main...origin/main
?? tests/qa_material/solo_natur_subset12/
?? tests/test_clip_children.py
?? tests/test_clip_drag_diag.py
?? tests/test_drag_multi_step.py
?? tests/test_map_and_click.py
```

**Diese fünf Pfade gehören nicht mir.** Sie stammen aus einer früheren
Sitzung (Vault-Notiz D-089) und lagen bereits vor Beginn meiner Arbeit dort.
Ich habe sie **nicht angefasst**: nicht committet, nicht gestasht, nicht
gelöscht. `tools/agent_handoff.ps1` meldet deswegen weiterhin `BLOCKED` —
das ist erwartet und kein Fehler.

**Entscheidung liegt beim Nutzer**, nicht bei dir: committen, in `.gitignore`
aufnehmen oder löschen. Frag ihn, bevor du daran etwas änderst.

Alles andere ist sauber. Keine unpushed Commits, kein Stash von mir.

Aktive Session-Claims prüfen mit `python tools\agent_session.py status`.
Meine letzten Sessions (`B-843-timeline-schwanz`, `B-844-mark-done-leer`)
darfst du auslaufen lassen — sie halten nur bereits committete Pfade. Vor
eigenen Edits selbst claimen (`claim --agent codex --task <id> --files ...`);
Exit-Code 2 heißt, eine fremde lebende Session hält die Pfade.

---

## 1. Was der Nutzer wollte (der rote Faden dieser Sitzung)

Der Nutzer hat über Tage berichtet, die Pacing- und Schnitt-Einstellungen
seien **„alles nur Attrappe"** — Regler verstellen, nichts passiert. Diese
Sitzung bestand im Kern darin, das zu belegen, zu beheben und zu beweisen.

Der Befund war berechtigt. Es waren **acht voneinander unabhängige Ursachen**,
und mehrere davon habe ich selbst erst erzeugt, während ich andere behob.

---

## 2. Was jetzt gilt — die Schnitt-Architektur

### 2.1 Der Auto-Edit schneidet nicht mehr im Beat-Raster

**Vorher:** `_select_cut_beats_advanced` legte einen festen Beat-Abstand.
**Jetzt:** `services/pacing/roter_faden.py::schnitt_anlaesse()` leitet die
Schnitte aus der Musik ab.

Geschnitten wird bei:
* **Section-Wechsel** (DROP, BREAKDOWN, CHORUS, BUILDUP)
* **Energiesprung** über `energie_schwelle` gegenüber einem gleitenden
  16-Beat-Mittel
* **Takt-Raster** je Section (`TAKTE_PRO_SECTION`) als Auffüllung

Alle Zeitpunkte werden auf den nächsten Downbeat gezogen, solange dieser
höchstens einen halben Takt entfernt liegt. Fallen zwei Gründe zusammen,
gewinnt der aussagekräftigere (`drop` schlägt `energie`).

Umgeschaltet wird in `services/pacing_service.py::_auto_edit_phase3_inner`
über `AdvancedPacingSettings.musikgetriebener_schnitt` (Default `True`).
**Der Raster-Pfad ist vollständig erhalten** und läuft bei `False` — es gibt
aber derzeit **keine UI**, die ihn setzt.

### 2.2 Die Cut-Rate-Combo ist ein Dichte-Regler, kein Raster mehr

`dichte_parameter(base_cut_rate, energy_reactivity)` übersetzt die Combo in
`max_takte` und `energie_schwelle`. Section-Wechsel und Drops sind davon
**unabhängig** und bilden die Untergrenze; die Combo bestimmt nur, wie viel
zusätzlich geschnitten wird.

Gemessen an den echten Projektdaten (738 Beats, 27 Sections, 337 s,
stem-gewichtete Energie):

| Combo | Schnitte | Median-Clipdauer |
|---|---|---|
| 1 Beat | 302 | 0,91 s |
| 2 Beat | 156 | 1,82 s |
| 4 Beat | **94** | **3,63 s** ← Vorgabe |
| 8 Beat | 59 | 5,47 s |
| 16 Beat | 38 | 9,08 s |

Im Livelauf am 15.08. bestätigt: 16 Beat → 64 Segmente, 1 Beat → 282 Segmente.

### 2.3 Mindestabstände

`HARD_MIN_DURATION` steht auf **1,0 s** (vorher 3,0). `SECTION_MIN_DURATION`
ist **autoritativ** und liegt bewusst darunter — die Werte sind aus
`SECTION_PACING_MAP` abgeleitet (schnellste erlaubte Stufe × Beatlänge bei
174 BPM, minus 5 % Toleranz):

```
DROP/BUILDUP 0,33 · CHORUS 0,65 · TRANSITION/VERSE 1,31 ·
WARMUP/BREAKDOWN/COOLDOWN 2,62
```

**Wichtig für dich:** Ein Segment von 0,9 s in einem BUILDUP ist **korrekt**,
kein Defekt. Zwei meiner eigenen Tests waren an dieser Stelle zu streng
formuliert und mussten korrigiert werden.

### 2.4 Der rote Faden

Vier Aspekte, alle vom Nutzer ausdrücklich gewünscht:

| Aspekt | Umsetzung | Wirkt? |
|---|---|---|
| weiche Übergänge | `w_style` 0,30, `w_collision` 0,20 im Scorer | ja |
| weniger Wiederholungen | Nutzungs-Cap (`berechne_max_uses`) + Freshness in `_compute_clip_fitness` | ja |
| Spannungsbogen | `bogen_intensitaet()`, Term in **beiden** Auswahlpfaden | ja, schwach |
| wiederkehrende Motive | `MotivGedaechtnis` (merkt `style_bucket`, nicht Clip-ID) | ja, schwach |

Der Bonus wird addiert in `_match_video_for_segment` (Legacy) **und** in
`PacingScorer.score()` (Studio-Brain). Ohne `at_track_duration_sec` bleibt der
Term exakt 0.

**Gemessene Wirkung:** mittlere Rangverschiebung 5,1 Plätze, aber der
Spitzenreiter wechselt nicht. Der Term färbt, er bestimmt nicht.

---

## 3. Alle Commits dieser Sitzung

| Commit | Inhalt |
|---|---|
| `f46d2eb` | B-820 Cancel überlebt den Status-Reconciler |
| `aa909d6` | B-822 Stem-Pfade ans aktive Projekt gebunden |
| `411c8e9` | B-821/B-823/B-824 projektrelative Stem-Pfade + Alembic-Migration |
| `b70e165` | B-825 Alembic-Downgrade an Index auf gedroppter Spalte |
| `718d77d` | B-815/B-618/B-826/B-827 |
| `a26243c` | **B-829** Default-Kurve überstimmte die Cut-Rate |
| `25e39d8` | **B-830/B-831/B-833** Style-Presets invertiert, Reaktivität gegenteilig, UI-Texte |
| `bef06d9` | **B-834** Clip-Cap ohne Reserve-Aufschlag + Wert-Logger |
| `25f1b98` | Härtung Wert-Logger (Abfrage in den Schutz gezogen) |
| `bc419a3` | **B-835/B-836/B-828/B-837** Mindestabstand, Reaktivität entkoppelt, Leer-Status, Kurven-Lebenszyklus |
| `4403ccd` | **musikgetriebener Schnitt + roter Faden** (neues Modul) |
| `a1d0cdb` | Cut-Rate als Dichte-Regler, Notbremse repariert, an echten Daten kalibriert |
| `ab33806` | **B-838/B-839** Mindestdauer überlebt Pflicht-Cuts, Bogen+Motive verdrahtet, Ollama-Fehlergrund |
| `5a31173` | **B-840/B-841** Kurve+Breakdown wirksam, Crossfade-Clamp, drei eigene Fehlbehauptungen korrigiert |
| `fd3782e` | **B-842** roter Faden im Studio-Brain-Pfad |
| `b98010a` | **B-843** Videospur endete 7,1 s vor der Musik |
| `58abd38` | Übergabe an Codex |
| `13daf78` | Brain-Bestandsaufnahme |
| `45ecaad` | **B-844** leere Ergebnisse in zwei Workern, falsche Dauermeldung |
| `d242987` | Übergabe final: Stand, B-844 als erledigt markiert |

Jede Commit-Message enthält Messwerte und Begründung. **Lies sie**, bevor du
an den betroffenen Stellen arbeitest — sie erklären, warum etwas so ist.

---

## 4. Fehler, die ICH gemacht habe — wiederhol sie nicht

Das ist der wichtigste Abschnitt für dich.

### 4.1 Ich habe mit konstanten Testdaten gemessen und dem Ergebnis geglaubt

Ich meldete „31 Schnitte, Median 12,7 s" als Erfolg. Gemessen hatte ich mit
**konstanter Energie 0,5** — die erzeugt per Definition keinen einzigen
Energiesprung. Mit echten stem-gewichteten Werten waren es **59 Schnitte,
Median 3,64 s**.

**Regel:** Für Pacing-Messungen immer die echten Beat-Energien laden:

```python
from services.pacing_beat_grid import _get_beat_data_combined, compute_stem_weighted_energy
beats, downbeats, energie, _ = _get_beat_data_combined(audio_id)
se = compute_stem_weighted_energy(audio_id, beats, 0.40, 0.30, 0.10, 0.20)
if se is not None and getattr(se, "weighted", None):
    energie = list(se.weighted)
```

### 4.2 Ich habe einen Term gewichtet, ohne den Wertebereich zu kennen

Ich setzte den Rote-Faden-Bonus auf 0,12 mit dem Kommentar „bewusst klein".
Eine Messung an 440 echten Clip-Embeddings ergab: die Spanne zwischen bestem
und zehntbestem Kandidaten beträgt **0,0325**. Mein Bonus war das
**7,4-fache** davon — er bestimmte die Rangfolge, statt sie zu färben.

**Regel:** Bevor du einen Score-Term hinzufügst oder gewichtest, miss die
tatsächliche Spanne zwischen den Top-Kandidaten.

### 4.3 Ich habe ein Gewicht angehoben, das gar nichts tut

`w_freshness` 0,05 → 0,15 als Mittel gegen Clip-Wiederholungen. Wirkungslos:
`staleness_penalty` (`services/pacing/scorer.py:431`) bekommt **keinen
`usage_count`**, nur ein 3er-Recency-Fenster. Simulation über 100 Cuts mit 439
echten Clips: 0,05, 0,15 und 0,60 liefern **identisch 4 verschiedene Clips**.
Zurückgenommen.

### 4.4 Ich habe eine Erfolgsmeldung geschrieben, die die Zahlen nicht deckten

Zu B-838 schrieb ich „vorher 37 von 78 Segmenten unter 3,0 s". Der Fix
entfernt in Wahrheit **genau einen Cut pro Stufe**; nach dem Fix sind es 49
von 102, anteilig sogar mehr. Die Verbesserung kam aus anderen Änderungen.

**Regel:** Eine Zahl im Commit muss zu genau der Änderung gehören, die der
Commit macht.

### 4.5 Ich habe dem Nutzer eine Gegenprobe empfohlen, die den Fix nicht ausführt

Ich bat ihn, „Timeline generieren" zu testen. `_enforce_minimum_durations`
läuft aber **nur** in `_auto_edit_phase3_inner` — der Vorschau-Knopf nutzt
`calculate_cut_points` und fasst den gefixten Code nie an.

**Merke:** Es gibt **zwei getrennte Pfade**. „Timeline generieren" zeichnet nur
Linien und schreibt nichts. Nur **Auto-Edit** erzeugt Clips.

### 4.6 Ich habe einen Regler abgehängt, während ich einen anderen reparierte

Der musikgetriebene Schnitt las `base_cut_rate` nicht mehr — ausgerechnet die
Combo, über die sich der Nutzer beschwert hatte. Dasselbe passierte mit der
Pacing-Kurve und der Breakdown-Combo (B-840).

**Regel:** Wenn du einen Codepfad ersetzt, prüfe **jede** Einstellung, die der
alte Pfad gelesen hat. Suche mit `grep -rn "settings\.<feld>"`.

### 4.7 Ich habe eine Agenten-Diagnose ungeprüft übernommen

Bei B-823 übernahm ich „fehlender RNG-Seed" als Ursache. Der Test blieb rot.
Die echte Ursache war ein modulglobaler Cache ohne Pfad im Schlüssel (B-826).
Der Vault-Eintrag B-823 trägt jetzt einen Korrektur-Block.

**Regel:** Bei „einzeln grün, zusammen rot" zuerst nach geteiltem Zustand
suchen, nicht nach Zufall.

---

## 5. Offene Punkte — nach Priorität

### 5.1 Entscheidung des Nutzers steht aus: LLM-Modellwahl

**Belegt:** `resolve_model_for_task` liefert für **alle fünf** Aufgaben
`qwen3-vl:4b`, weil B-770 (`services/model_router.py:117ff`) die explizite
Einstellung `ollama.model` über die Auto-Wahl stellt.

Folge: Ein **Vision**-Modell bearbeitet auch die **Text**-Aufgabe Pacing-EDL
und läuft dabei **jedes Mal** in den 300-Sekunden-Timeout:

```
07:01:38 Call ueberschritt Wall-Clock-Grenze von 300.0s (chat) — Abbruch
08:35:46 dasselbe im zweiten Lauf
```

Fünf verschwendete Minuten pro Auto-Edit. Installiert sind u.a. `phi3:mini`
(2,03 GB) und `gemma3:4b` (3,11 GB), die dafür besser passen.

Drei Wege wurden dem Nutzer vorgelegt, **er hat noch nicht entschieden**:
1. eigenes Modell pro Aufgabe in den Einstellungen
2. B-770 auf Vision-Pfade beschränken
3. nur den Timeout entschärfen (EDL bei Vision-Modellen überspringen)

**Bau das nicht ohne seine Antwort.**

### 5.2 Wunsch des Nutzers, noch nicht umgesetzt: Multi-Modell-Pacing

Wörtlich: *„beim Pacing müssen eigentlich gemma4, das Audio verarbeiten kann,
mit qwen3, das sehen kann und das bessere Verständnis für Videos hat,
zusammenarbeiten und miteinander reden."*

Seine Begründung ist inhaltlich richtig: Text-Ähnlichkeit zweier Begriffe sagt
nichts darüber, ob ein Clip an **dieser Stelle** zur Musik passt. Das ist ein
Feature-Entwurf, kein Bugfix — Umfang und Vorgehen sind mit ihm zu klären.

Randbedingung: GTX 1060 mit 6 GB. `keep_alive=0` wird bei <8 GB erzwungen
(`services/ollama_client.py:121-125`), die App belegt selbst ~2,8 GB. Zwei
Modelle gleichzeitig im VRAM sind damit nicht realistisch.

### 5.3 Materialgrenze: längster Clip ist 10 s

Im Projekt 123454321 gibt es **keinen einzigen Clip über 10 s**.
`finalize_cut_beats` splittet jedes längere Segment. Lange Einstellungen sind
mit diesem Material strukturell unmöglich — kein Codefehler.

### 5.4 Nicht gefixt, dokumentiert

* **B-832 Vibe-Feld** — steht hinter einem frühen `return` in
  `_match_video_for_segment`. Braucht eine Produktentscheidung: Notnagel
  (dann UI anpassen) oder ins Scoring einweben.
* **„Timeline generieren" schreibt nichts** — jetzt ehrlich beschriftet, aber
  das Verhalten ist unverändert. Entweder als Vorschau belassen (und
  umbenennen) oder den Schreibpfad von Auto-Edit geben.
* **`_enforce_minimum_durations` ist positionell redundant** — `_mindestdauer_
  durchsetzen` in `finalize_cut_beats` erledigt dasselbe. **Nicht löschen:**
  es ist der einzige Konsument von `min_multiplier_windows` (Vocal-on-Hold,
  `services/pacing_service.py:563-604`).
* **Drop-Burst reißt den Max-Segment-Split auf** —
  `services/pacing/cut_density_modulator.py:70-73` löscht Cuts im 4-Takt-Fenster
  nach jedem Drop, nach `finalize_cut_beats`. Gemessen: 7,97 s → 9,38 s bei
  einem Limit von 8,0 s.
* ~~`mark_done` ohne Leer-Prüfung in den Audio-Workern~~ — **behoben in
  `45ecaad` (B-844)**. `_leeres_ergebnis()` im V2-Worker, `_track_vorhanden()`
  im BaseAnalysisWorker. Auch die falsche Dauermeldung aus B-843 ist dort
  korrigiert: `pacing_service` leitet die Länge jetzt aus den erzeugten
  Segmenten ab statt aus der Audiodauer.
* **Preset-Felder ohne Leser:** `beat_weight`, `kick_weight`, `snare_weight`,
  `hihat_weight`, `min_clip_duration`, `max_clip_duration`.
* **`global_min_duration = 3.0`** in `services/pacing_strategist.py:115,177`
  wird geparst und getestet, aber nirgends angewandt.

---

## 6. Wie du misst und testest

### 6.1 Aufzeichnung

Die App schreibt bei `PB_CLICK_LOG=1` **jeden** Klick, Tastendruck und
Reglerwert nach `logs/pb_studio.log`:

```
[CLICK] jeder Maus-Press/Release mit Widget, Text, Position
[KEY]   Tastendruck mit Key-Name (Passwortfelder ausgenommen)
[VALUE] Combo (Index + Text), Slider, Spin, Textfeld, Tab, Checkbox
```

Starten (PowerShell, **nicht** Git-Bash — dort fehlen die conda-DLL-Pfade):

```powershell
$env:PB_CLICK_LOG="1"; $env:PB_LOG_LEVEL="DEBUG"
$env:CUDA_MODULE_LOADING="LAZY"; $env:KMP_DUPLICATE_LIB_OK="TRUE"
Start-Process "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" `
  -ArgumentList "main.py" -WorkingDirectory "<repo>"
```

**Nicht** `start_pb_studio_clicklog.bat` verwenden, wenn der Nutzer sein echtes
Projekt braucht — das Skript biegt `APPDATA`/`LOCALAPPDATA` auf ein isoliertes
Verzeichnis um und startet mit leerem Projekt.

### 6.2 Tests

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services -q -k "faden or pacing or auto_edit" -p no:cacheprovider
```

Der volle Lauf über `tests/` braucht >10 Minuten und läuft in Timeouts —
immer mit `-k` filtern.

### 6.3 Testdaten des Nutzers

* Projekt: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\projects\123454321`
* Audio: „Maceo Plex – Sub-Alot", `audio_id=1`, 337,14 s, 132 BPM, 738 Beats,
  27 Sections
* 121 Videoclips, längster 10,0 s
* Renders in `projects/123454321/exports/`

---

## 7. Bugs dieser Sitzung im Vault

Pfad: `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\bugs\`

Neu: B-826, B-827, B-828 (behoben), B-829 bis B-844 — jeder mit eigenem File.
`log.md` enthält für jeden Schritt einen datierten Eintrag mit Messwerten.

**`status: fixed` setzt ausschließlich der Nutzer** — nie du, nie ich.
Alle meine Einträge stehen auf `code-fix-pending-live-verification`.

Drei Karteileichen habe ich korrigiert (Korrektur-Block oben im File, alter
Text bleibt als Beleg stehen): **B-823** (falsche Ursache), **B-090** (nennt 14
`lazy="joined"`, es ist noch eines), **B-235** (die als fehlend genannten
Spalten existieren).

---

## 8. Was noch nicht live verifiziert ist

**Kein einziger meiner Fixes ist im echten Betrieb abgenommen.** Der Nutzer
hat am 15.08. zwei Auto-Edits gefahren (16 Beat und 1 Beat), die den
Dichte-Regler bestätigen. Alles danach — B-840 bis B-843 — ist nur an den
Kernfunktionen gemessen.

Insbesondere ungeprüft:
* ob Kurve und Breakdown-Combo im echten Lauf sichtbar wirken (B-840)
* ob der Crossfade-Clamp greift (B-841) — der Nutzer schneidet mit „cut"
* ob die Videospur jetzt bis ans Audio-Ende reicht (B-843)
* ob der rote Faden im Studio-Brain-Pfad sichtbar etwas ändert (B-842)

**Die App läuft NICHT mehr** — der Bluescreen hat sie beendet. Für die
Verifikation mit Aufzeichnung neu starten (Anleitung in 6.1), dann ein
Auto-Edit plus Render: das klärt alle vier Punkte in einem Durchgang. B-844
kommt als fünfter ungeprüfter Punkt dazu (leere Analyse-Schritte melden jetzt
`degraded` statt `done`).

---

## 9. Das Brain — Bestandsaufnahme vom 15.08.2026

Der Nutzer verstand das Brain-Fenster nicht und fragte, warum es „Brain" und
„Brain V3" gibt und ob beide je gewirkt haben. Zwei Prüfagenten, danach von mir
an den echten Datenbanken nachgemessen.

### 9.1 Es gibt DREI Dinge, die „Brain" heißen

| Name | Ort | Was es ist |
|---|---|---|
| **Studio Brain** (Knopf oben, Ctrl+B) | `ui/studio_brain_window.py`, 6 Tabs | Protokoll- und Steuerfenster. Liest `mem_*` und `struct_*` aus der Projekt-DB |
| **Brain V3** (Tab in der Seitenleiste) | `ui/widgets/brain_v3_stats_panel.py` | Lern-Mechanismus mit **eigener** Datenbank unter `%APPDATA%\PB_Studio\brain_v3\` |
| **Brain im Chat** (`brain_recall`, `brain_note`) | `services/actions/brain_actions.py` | Notiz-Gedächtnis des Assistenten, drittes System |

**V3 ist kein Nachfolger.** Wörtlich im Architekturplan
(`docs/superpowers/archive/2026-05-04-brain-v3-nvidia-plan/01_ARCHITECTURE.md:5-6`):
*„Brain V3 ist ein Layer ÜBER dem bestehenden Pacing-Code — kein Ersatz."*

Die Trennung war eine ausdrückliche Nutzer-Anweisung (Entscheidung #24,
`02_DECISIONS.md:249-254`): *„UI: neuer Tab/Window in Phase 5 (NICHT
studio_brain_window.py umbauen)"*.

Die Namensgebung ist trotzdem irreführend — „V3" klingt nach Generation, ist
aber ein paralleler Zusatz. Die Verwirrung des Nutzers ist berechtigt.

### 9.2 Haben sie gewirkt? Ja — auf die Timeline, nicht aufs Rendering

Gemessen an `projects/123454321/pb_studio.db`:

```
struct_clip_tags       147      mem_pacing_run           6
struct_style_bucket    129      mem_decision           899
struct_compat_edge     282      mem_learned_pattern      0
                                mem_user_feedback_event  0
```

**Der Studio-Brain hat die Timeline real geformt:** Run 6 zeigt 280 von 280
`chosen_clip_id` exakt deckungsgleich mit `timeline_entries.media_id` bei
identischer `start_time`, null Abweichungen. 280 der 282 Segmente der aktuellen
Timeline sind Brain-gewählt.

**Der Brain-V3-Reranker lief mit:** 13 Aktivierungen im Log, Blending-Anteil
30 % gegen 70 % klassisches Pacing (`services/pacing/pipeline.py:51`),
`brain_v3_scores` in 280 von 280 Rationales.

**Aufs Rendering wirkt keiner von beiden.** `services/export_service.py:341-424`
liest ausschließlich `timeline_entries`-Spalten; ein Grep über zwölf
Export-Dateien nach `reranker|weight_store|brain_v3|mem_decision|select_best`
liefert null Treffer. Der Einfluss endet bei der Clip-Auswahl.

### 9.3 Das Lernen ist mathematisch wirkungslos — selbst nachgemessen

`%APPDATA%\PB_Studio\brain_v3\weights.db`, Tabelle `axis_weights`, Ebene 0:

```
beat_weight              198 / 282
brightness_match_weight  198 / 282
color_temp_match_weight  198 / 282
energy_threshold         198 / 282
...  (17 Achsen exakt gleich)  ...
role_match_weight          2 /   1   <- einzige Ausnahme
```

**18 Achsen, davon 2 verschiedene Wertepaare.** Ursache:
`services/brain/feedback_logger.py:70-85` schreibt bei jedem Klick allen Achsen
dieselbe Gutschrift (`mode=uniform`). Gleiche Gewichte über alle Achsen heißt:
der gewichtete Mittelwert wird zum einfachen Durchschnitt
(`services/brain/scorer.py:52`) — **Nutzerklicks können die Clip-Reihenfolge
nicht verändern.**

Dazu kommt: Es existieren genau **drei** Feedback-Events überhaupt (alle
2026-08-14, 03:26–03:27). `user_verdict`, `user_rating` und `reward` sind in
**allen 899** Entscheidungen NULL. `mem_learned_pattern` hat 0 Zeilen.

Die einzige achsen-spezifische Schreib-API `WeightStore.update()`
(`services/brain/weight_store.py:135`) hat **null Aufrufer**.

**Zusammengefasst: das Brain wirkt, aber es lernt nicht.**

### 9.4 Was im Brain-Fenster wirkt und was Attrappe ist

Das Fenster hat sechs Tabs: Struktur, Gedächtnis, Audit, Steer,
Pacing-Explorer, Graph-Cockpit.

**Wirkt:**

* **Boost / Exclude** im Struktur-Tab. `services/steer_override_queue.py:79` →
  `services/pacing_service.py:1692-1702` (Exclude wirft den Clip raus) und
  `services/pacing/pipeline.py:571-575` (Boost, +0,5 Punkte). **Nur im
  Arbeitsspeicher** — geht bei App-Ende, Projektwechsel und nach einem Lauf
  verloren.
* **„Mit diesen Einstellungen starten"** im Steer-Tab → echter Auto-Edit,
  überschreibt die Timeline.
* **Daumen** im Pacing-Explorer → `mem_decision.user_verdict` →
  `services/pacing/pattern_lookup.py:65-102` → Scorer.
* **„Gelerntes zurücksetzen"** im Gedächtnis-Tab.

**Attrappe:**

* Steer-Tab: **Gewichtsprofil-Auswahl** (die Pipeline setzt hart
  `weights_profile="default"`, `pacing_service.py:1424`) und **Pins** (gehen
  nur ins Log, `main.py:797`).
* Gedächtnis-Tab: **Sterne-Bewertung** — `mem_pacing_run.user_rating` wird
  nirgends im Produktivpfad geschrieben.
* Audit-Tab und Graph-Cockpit: reine Leseansichten ohne Schreibpfad.

**Toter Code:**

* `mem_user_feedback_event` — beschrieben, nie gelesen
* `services/pacing/rl_memory_v2.py` — beschrieben, nie gelesen
* Brain-V3-Embedding-Cache — 554 Dateien auf Platte, `embedding_cache.py:44,150`
  ohne Aufrufer; der Scheduler belegt trotzdem bei jedem Start GPU
  (`main.py:859-873`)
* `WeightStore.update()`, `GraphView.set_active_scene`, Signale
  `verdictChanged` und `statsRefreshed`

**Der Daumen umgeht den offiziellen Feedback-Dienst**
(`services/feedback_service.py:153-228`): kein `mem_user_feedback_event`, kein
Brain-V3-Lernsignal, und ein hier gesetztes Urteil blockiert späteres
Timeline-Feedback zur selben Entscheidung (`feedback_service.py:216`).

### 9.5 Wichtige Warnung für dich

Einer der beiden Prüfagenten hat die **falsche Datenbank** gelesen — die
Repo-Root-`pb_studio.db` statt der Projekt-DB — und daraus geschlossen, alle
`struct_*`-Tabellen seien leer. **Sie sind es nicht:**

```
Repo-Root:  struct_clip_tags   0   mem_decision    5
Projekt:    struct_clip_tags 147   mem_decision  899
```

**Immer gegen `projects/<id>/pb_studio.db` messen**, nicht gegen die Datei im
Repository-Wurzelverzeichnis.

### 9.6 Offen — Entscheidungen des Nutzers

Der Nutzer hält die Aufteilung für unlogisch und versteht die Funktionen nicht.
Das ist nach dieser Bestandsaufnahme nachvollziehbar. Zu klären, **bevor**
jemand daran baut:

1. Sollen Studio Brain und Brain V3 zusammengeführt werden? Die Trennung geht
   auf seine eigene frühere Anweisung zurück (Entscheidung #24).
2. Soll das Lernen repariert werden? Der Kern ist `mode=uniform` in
   `feedback_logger.py:70-85` — ohne Credit-Assignment auf einzelne Achsen
   bleibt jedes Feedback richtungsloses Rauschen.
3. Sollen die Attrappen (Gewichtsprofil, Pins, Sterne) verdrahtet oder entfernt
   werden?
4. Soll der tote Code raus?

---

## 10. Schlusszustand und erste Schritte für dich

### 10.1 Wie die Sitzung endete

Am 15.08. gegen 12:00 gab es einen **Bluescreen** des Rechners, mitten in der
Arbeit an B-844 (uncommittet). Nach dem Neustart wurde geprüft und nichts ging
verloren:

* alle vier geänderten Dateien syntaktisch intakt (`py_compile` OK)
* Tests neu gefahren: 23/23, danach Regression 608 passed
* committet als `45ecaad`, Übergabe als `d242987`
* der erste Push scheiterte an fehlendem DNS (Netz nach Neustart noch nicht
  da) — nachgeholt, beide Repos synchron

**Die Bluescreen-Ursache ist unbekannt und wurde nicht untersucht.** Zeitlich
fiel er in eine Phase ohne laufende App und ohne GPU-Last durch uns. Falls es
wieder passiert: Windows-Ereignisanzeige und Minidump prüfen, bevor jemand die
App verdächtigt.

### 10.2 Zustand beim Wechsel

| Was | Zustand |
|---|---|
| `main` | `d242987`, synchron mit `origin/main`, 0 unpushed |
| Vault | sauber, gepusht; `log.md` lückenlos bis 12:10 |
| Bugfiles | B-826 bis B-844 vollständig, alle `code-fix-pending-live-verification` |
| App | **läuft nicht** (Bluescreen) |
| Worktree | nur die fünf fremden D-089-Pfade untrackt (nicht anfassen, Nutzer entscheidet) |
| Session-Claims | meine dürfen auslaufen; vor Edits selbst claimen |
| Ollama | 0.21.2 muss laufen (Port 11434). Achtung: startet der alte Tray (0.32.6) zuerst, ist der PTX-Fehler zurück |

### 10.3 Alle offenen Entscheidungen des Nutzers — an einem Ort

**Nichts davon ohne seine Antwort bauen.** Er kennt jede dieser Fragen bereits.

1. **LLM-Modellwahl (dringlichster Punkt):** B-770 erzwingt `qwen3-vl:4b` für
   ALLE Aufgaben. Das Vision-Modell läuft im Text-Pacing-EDL **jedes Mal** in
   den 300-s-Timeout — fünf verlorene Minuten pro Auto-Edit, Ergebnis kommt
   nie an. Drei vorgelegte Wege: (a) Modell pro Aufgabe in den Einstellungen,
   (b) B-770 auf Vision-Pfade beschränken, (c) nur EDL bei Vision-Modellen
   überspringen.
2. **Multi-Modell-Pacing (sein Wunsch, wörtlich):** „gemma4, das Audio
   verarbeiten kann, mit qwen3, das sehen kann, zusammenarbeiten und
   miteinander reden." Inhaltlich berechtigt — Text-Ähnlichkeit sagt nichts
   darüber, ob ein Clip an dieser Stelle zur Musik passt. Randbedingung: 6 GB
   VRAM, App belegt ~2,8 GB, `gemma4:e4b` allein ist 8,95 GB. Zwei Modelle
   gleichzeitig sind unrealistisch; sequentiell kostet jeder Wechsel ~20 s
   (`keep_alive=0`). Feature-Entwurf mit ihm klären, bevor Code entsteht.
3. **Brain zusammenführen?** Er hält Studio Brain + Brain V3 + Chat-Brain für
   unverständlich. Die Trennung war seine eigene frühere Anweisung
   (Entscheidung #24) — das muss er auflösen, nicht du.
4. **Brain-Lernen reparieren?** `mode=uniform` in `feedback_logger.py:70-85`
   macht jedes Feedback zu richtungslosem Rauschen (17 von 18 Achsen
   identisch). Ohne Credit-Assignment lernt nichts.
5. **Brain-Attrappen:** Gewichtsprofil, Pins, Sterne — verdrahten oder
   entfernen?
6. **B-832 Vibe-Feld:** Notnagel (dann UI ehrlich machen) oder ins Scoring?
7. **„Timeline generieren":** Vorschau belassen (und umbenennen) oder echten
   Schreibpfad geben?
8. **D-089-Dateien:** die fünf untrackten Test-Pfade — committen, ignorieren
   oder löschen?
9. **Raster-Pfad-UI:** `musikgetriebener_schnitt=False` existiert, aber keine
   UI setzt es. Schalter anbieten oder Altpfad irgendwann entfernen?
10. **Toter Code** (Embedding-Cache belegt GPU bei jedem Start,
    `rl_memory_v2`, `mem_user_feedback_event`, `global_min_duration`):
    aufräumen ja/nein?

### 10.4 Sinnvoller Einstieg (Vorschlag, keine Pflicht)

1. `AGENTS.md` vollständig lesen, dann dieses Dokument, dann
   `tools\agent_start.ps1` laufen lassen (meldet BLOCKED wegen D-089 — bekannt).
2. Den Nutzer nach der **LLM-Entscheidung** (10.3 Punkt 1) fragen — das ist
   der größte sofort behebbare Zeitfresser.
3. App mit Aufzeichnung starten (6.1) und die **Live-Verifikation** fahren:
   ein Auto-Edit (klärt B-840/B-842/B-843/B-844) plus ein Render (klärt
   B-843 endgültig: Videodauer == 337,1 s?). Ergebnisse in die Bugfiles,
   `status: fixed` setzt der Nutzer.
4. Erst danach neue Baustellen.

### 10.5 Arbeitsregeln, die hier wirklich gelten

Kurzfassung der Regeln, an denen diese Sitzung gemessen wurde — Details in
`AGENTS.md` und `CLAUDE.md`:

* **Nur explizit Beauftragtes.** Keine While-I'm-here-Fixes. Befunde melden,
  auf Auftrag warten.
* **Vault nach jedem Sub-Schritt** (`log.md` mit Zeitstempel, Bugs als eigene
  Files). Max. 1 Turn ungeloggt.
* **`status: fixed` setzt nur der Nutzer.** „Verified"/„fixed"/„works" sind
  reservierte Wörter — Code-Edit ist kein Fix, erst der Live-Beleg zählt.
* **GPU: ausschließlich die GTX 1060** (`cuda:0`, NVENC). Keine iGPU, kein
  anderes Backend, sonst CPU.
* **Nie `git add -A`.** Nur eigene, beanspruchte Pfade stagen.
* **Deutsch antworten.** Caveman-Kompression ist Stilvorgabe des Nutzers.
* **Messungen mit echten Projektdaten** (Abschnitt 4.1 und 6.3) — synthetische
  Eingaben haben diese Sitzung zweimal in die Irre geführt.

Damit ist alles übergeben, was ich weiß. Viel Erfolg.
