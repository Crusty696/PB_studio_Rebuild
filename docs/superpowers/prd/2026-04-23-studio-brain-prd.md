# Studio Brain — Product Requirements Document

**Datum:** 2026-04-23
**Projekt:** PB Studio Rebuild
**Pipeline-Phase:** 3 (PRD)
**Inputs:** Design-Doc Phase 1, Research-Doc Phase 2
**Output:** Input für Phase 4 (Machbarkeit), Phase 5 (Plan)
**Status:** Draft for User Review

---

## Problem Statement

Ich bin Creator und Solo-Editor. Mein Projekt hat eine wachsende Bibliothek von Video-Clips (bald > 500 Scenes, perspektivisch > 5000), und ich schneide Cuts zu Musik — teils einzelne Tracks, teils 1–3 Stunden lange DJ-Mixe.

Heute hilft mir PB Studio bereits bei Clip-Analyse, Beat-Erkennung, Structure-Detection, Key-/LUFS-/Genre-Klassifikation und Pacing-Vorschlägen. Aber der Pacing-Agent macht drei Fehler, die mir regelmäßig Arbeit und Material kosten:

1. **Stil-Kollisionen.** Er setzt Clips nebeneinander, die visuell/thematisch nicht zusammenpassen (Nature → Urban-Grit → Close-up Face ohne Logik). Ich muss jede Passage manuell nachkorrigieren.
2. **Rollen-Blindheit.** Er unterscheidet nicht zwischen Hero-Shot, Transition, Establishing, Detail, Filler. Alle Clips sind für ihn gleichwertig, also landen manchmal Establishing-Wide-Shots im Drop, wo ein Hero-Shot hingehört.
3. **Mood-Blindheit.** Er hat kein Gefühl dafür, ob ein Clip melancholisch, euphorisch, dunkel oder verspielt ist — und berücksichtigt das daher nicht bei der Auswahl zur Musik.

Und er **lernt nicht.** Dieselben Fehler passieren bei jedem Projekt neu. Meine ästhetischen Präferenzen („bei BPM 140 in Dark-Psytrance bevorzuge ich Hero-Close-ups") existieren nur in meinem Kopf — sie fließen nie automatisch in seine Entscheidungen.

Zusätzlich fehlt mir ein **Überblick über meine eigene Library.** Ich weiß nicht, wie viele Clips ich welcher Stilrichtung habe, welche oft im Bestand untergehen, welche Moods ich gar nicht abdecke. Bei 500+ Clips wird das ohne strukturierte Sicht schnell chaotisch.

Ich will **nicht** manuell jeden Clip labeln. Bei 500 Clips × 5 Min = 40 Stunden Arbeit, bevor irgendwas besser funktioniert. Das ist kein realistischer Workflow. Das System muss sich Wissen selbst erarbeiten.

Und ich will **nicht** in eine andere App wechseln. Ich will alles in PB Studio, ein zusätzliches Fenster bei Bedarf ist in Ordnung.

---

## Solution

PB Studio bekommt ein **Studio Brain** — ein in-App Wissens- und Lern-System, das dem Pacing-Agent zwei Dinge gibt, die ihm heute fehlen: **Wissen** darüber, was meine Clips sind, und **Erinnerung** daran, wie sie in der Vergangenheit funktioniert haben.

**Die Struktur-Schicht** läuft automatisch, sobald ein Clip analysiert wurde. Sie weist jeder Scene eine Rolle zu (Hero, Action, Transition, Detail, Establishing, Filler), eine verfeinerte Mood-Klasse (10 Werte statt der bisherigen 4), einen Style-Bucket (automatisch geclustert aus den Bild-Embeddings), und sie baut einen Kompatibilitäts-Graphen („welche Clips passen stilistisch zu welchen"). Keine manuelle Arbeit meinerseits.

**Die Gedächtnis-Schicht** zeichnet jede Pacing-Entscheidung mit vollem Audio-/Video-Kontext auf: BPM, Key, Harmonic-Tension, Genre, Mood, Spectral-Profil, Groove, LUFS, Clip-Role, Clip-Mood, Style-Bucket, Motion. Sobald ich während des Reviews einen Cut akzeptiere, verwerfe oder bewerte (per Shortcut direkt in der Timeline), lernt das System daraus. Über Zeit entstehen Muster wie „bei Dark-Psytrance im Drop bei BPM 140 bevorzuge ich Hero-Role + Style=Urban-Industrial mit 83 %iger Akzeptanz". Der Agent nutzt diese Muster als zusätzlichen Scoring-Term bei zukünftigen Runs.

**Das Studio Brain-Fenster** ist ein separates Fenster, das ich per Button oder Shortcut öffne. Es hat vier Tabs und einen on-demand Dialog:

- **Struktur** — Graph- oder Grid-View meiner ganzen Library, mit Filtern nach Role/Mood/Style, Stats-Panel (was habe ich? was fehlt?), und einem Inspector pro Clip, der auch historische Nutzung zeigt.
- **Gedächtnis** — Timeline aller vergangenen Pacing-Runs, Liste der gelernten Muster, Drill-Down in die zugrundeliegenden Entscheidungen.
- **Audit** — nach einem Run sehe ich cut für cut, warum der Agent das gewählt hat (term-by-term Aufschlüsselung), welche Alternativen er hatte, wo er Regeln weichen musste. Für DJ-Mixe ein horizontaler Segment-Strip zum Springen.
- **Steer** — vor dem nächsten Run kann ich Clips an Sections pinnen, Clips aus diesem Run ausschließen, Style-Buckets boosten — ohne das Gedächtnis zu verfälschen.
- **Story-Map** — on-demand pro Song: die visuelle Reise durch den Song, Tension-Kurve, Mood-Verlauf, klickbare Clip-Thumbnails.

**Feedback passiert direkt in der Timeline**, nicht im Studio Brain. Während ich den Cut review, drücke ich `A` (accept), `R` (reject), `S` (skip), `1-5` (rating). Das speist das Gedächtnis, der Agent wird beim nächsten Run besser. Der Keystroke wird unter 100 ms persistiert, damit der Flow nicht bricht.

Der Pacing-Agent selbst wird von heute „Motion + Energy" auf **4-stufige Entscheidungs-Pipeline** aufgewertet: Hard-Rules (Section × Role), Variations-Budget (keine Wiederholungen), Kollisions-Check (via Compat-Graph), und ein gewichtetes Scoring mit 10+ Termen, die Struktur, Gedächtnis und Audio-Kontext gleichzeitig berücksichtigen. Alle Terme sind ab Tag 1 verdrahtet — Patterns, die noch nicht gelernt sind, bleiben durch Wilson-Lower-Bound-Confidence automatisch dezent, bis sie Daten haben.

---

## User Stories

### Pacing-Agent wird klüger

1. Als Editor will ich, dass der Pacing-Agent Rollen kennt, damit Hero-Shots im Drop und Establishing-Wide-Shots im Intro landen — nicht umgekehrt.
2. Als Editor will ich, dass der Agent stilistische Kollisionen zwischen Nachbar-Clips vermeidet, damit ich weniger manuell nachkorrigiere.
3. Als Editor will ich, dass der Agent Wiederholungen vermeidet, damit nicht dieselben 5 Clips immer wiederkommen, obwohl 100 passende da wären.
4. Als Editor will ich, dass der Agent die Mood meiner Clips berücksichtigt, damit ein dreamy-Clip nicht auf einem Tension-Peak landet.
5. Als Editor will ich, dass der Agent den Musik-Key kennt und bei Modulations-Peaks oder hoher Harmonic-Tension keine „falschen" Moods wählt.
6. Als Editor will ich pro Genre (Psytrance, House, DnB …) andere Scoring-Gewichte, damit der Agent Genre-spezifisch passend schneidet.
7. Als Editor will ich, dass DJ-Mixe mit 1–3 h Länge verarbeitet werden, weil ich tatsächlich so lange Mixe cutte.
8. Als Editor will ich, dass innerhalb eines DJ-Mix-Segments andere Budgets gelten als im ganzen Mix, damit jedes Segment wieder „frisch" startet.

### Gedächtnis lernt

9. Als Editor will ich, dass jeder Cut mit vollem Kontext gespeichert wird, damit später nachvollzogen werden kann, warum der Agent gewählt hat.
10. Als Editor will ich, dass meine Accept/Reject-Entscheidungen in das Muster-Lernen einfließen, damit der Agent meine Ästhetik übernimmt.
11. Als Editor will ich, dass das System mich nicht nach jedem Cut stört — Feedback ist optional, Keine Rückmeldung heißt „hat nicht gestört".
12. Als Editor will ich einen Shortcut für Akzeptieren (A), Verwerfen (R), Überspringen (S) und Bewerten (1-5) direkt in der Timeline, damit Feedback im Flow passiert.
13. Als Editor will ich ein globales Rating für den ganzen Run (Shift+1-5), damit ich schnell „gefühlt gut / schlecht" markieren kann.
14. Als Editor will ich, dass frische Patterns (wenige Samples) den Agent nicht sofort dominieren, damit einzelne Zufalls-Entscheidungen nicht über-interpretiert werden.
15. Als Editor will ich, dass das System nach zehn Runs tatsächlich messbar besser schneidet, nicht nur theoretisch.

### Library verstehen

16. Als Editor will ich einen Graph meiner Clips mit Kanten für Ähnlichkeit, damit ich auf einen Blick sehe, welche Clips als Cluster zusammen gehören.
17. Als Editor will ich eine Grid-Ansicht nach Style-Bucket gruppiert, damit ich schnell scrollen kann und nicht in Force-Directed-Graphen navigiere, wenn ich nur suche.
18. Als Editor will ich Filter nach Role, Mood, Style, Confidence und Usage-Status („ungenutzt", „≥5 mal verwendet"), damit ich gezielt neues oder altes Material identifiziere.
19. Als Editor will ich sehen, welche Moods in meiner Library unterrepräsentiert sind, damit ich weiß, wo ich nachschießen muss.
20. Als Editor will ich einen Inspector pro Clip, der mir alle Analyse-Daten (Role, Mood, Style, Motion, Caption, Nachbarn) UND die historische Nutzung (Akzeptanz-Rate) zeigt.
21. Als Editor will ich per Klick auf einen Nachbarn im Inspector zu diesem Clip springen, damit ich den Compat-Graph explorieren kann.

### Agent-Entscheidungen auditieren

22. Als Editor will ich nach einem Run sehen, welche Clips der Agent wo gewählt hat, damit ich seine Logik nachvollziehen kann.
23. Als Editor will ich für jeden Cut die aufgeschlüsselte Score-Berechnung sehen — welcher Term wie viel beigetragen hat — damit ich verstehe, warum.
24. Als Editor will ich die Top-3-Alternativen pro Cut sehen, damit ich bei einem Reject nicht raten muss, was er hätte nehmen sollen.
25. Als Editor will ich einen horizontalen Segment-Strip bei DJ-Mixen, damit ich in 3-Stunden-Mixen schnell zu einem Segment springen kann.
26. Als Editor will ich die Cut-Tabelle filtern können („nur rejected", „nur fallback", „nur hohe Tension"), damit ich Problemfälle isoliert analysiere.
27. Als Editor will ich den aktuellen Budget-State pro Cut sehen, damit ich verstehe, welche Variations-Budgets angeschlagen waren.

### Nächsten Run steuern

28. Als Editor will ich einzelne Clips an Sections pinnen („dieser Clip muss in den Drop"), damit ich gezielte Einflüsse nehmen kann.
29. Als Editor will ich Clips oder ganze Style-Buckets aus einem Run ausschließen, damit ich Störer temporär raushalten kann.
30. Als Editor will ich Style-Buckets oder Moods boosten (+X %), damit ich Richtung beeinflusse, ohne hart zu steuern.
31. Als Editor will ich, dass meine Steer-Einstellungen pro Run archiviert werden, damit ich später reproduzieren kann, warum ein Run anders lief.
32. Als Editor will ich, dass Steer das Gedächtnis NICHT verändert — Steer ist bewusste Intervention, kein Lernsignal.

### Story-Map

33. Als Editor will ich per Button aus dem Audit-Tab eine Story-Map für einen Song öffnen, damit ich die visuelle Reise sehe.
34. Als Editor will ich die Story-Map mit Audio-Waveform, Structure-Segmenten, Clip-Thumbnails, Tension-Kurve und Mood-Verlauf, damit ich die Gesamt-Narrativ-Qualität beurteilen kann.
35. Als Editor will ich Klick auf ein Clip-Thumbnail zur Timeline-Position springen, damit ich sofort nachsehen kann.
36. Als Editor will ich die Story-Map als PNG/SVG exportieren, damit ich sie im Team teilen oder archivieren kann.
37. Als Editor will ich NICHT, dass Story-Maps in meinen Brain-Bug-Vault exportiert werden — das Studio Brain ist App-intern.

### Qualität und Robustheit

38. Als Editor will ich, dass Enrichment CPU-only läuft, damit ich die GPU für Analyse-Jobs frei habe.
39. Als Editor will ich, dass Enrichment einer 5000-Scenes-Library unter 80 Sekunden fertig ist.
40. Als Editor will ich, dass ein 3-Stunden-DJ-Mix in Pacing und Enrichment unter 2 GB Peak-RAM verarbeitet wird.
41. Als Editor will ich, dass jeder Keystroke-Feedback in weniger als 100 ms persistiert ist, damit der Flow nicht bricht.
42. Als Editor will ich, dass ein teilweise ungeeignetes Analyse-Ergebnis (fehlender ai_caption, kein Embedding) den Rest der Library nicht blockiert.
43. Als Editor will ich, dass der Agent niemals einen leeren Cut liefert — selbst wenn alle Regeln hart sind, gibt es einen Fallback mit klarer Warnung.
44. Als Editor will ich, dass gelöschte Clips die historischen `mem_decision`-Einträge nicht löschen (nur Placeholder in UI).
45. Als Editor will ich, dass vor jeder destruktiven Aktion (Pattern-Reset, Enricher-Version-Wechsel) automatisch ein DB-Backup gemacht wird.
46. Als Editor will ich, dass täglich bei App-Start ein Backup gemacht wird (wenn das letzte > 24 h her ist), damit ich immer einen Rollback-Punkt habe.
47. Als Editor will ich, dass maximal 14 Backups behalten werden (rolling), damit mein Disk nicht zumüllt.

### Nicht-funktionale Erwartungen

48. Als Editor will ich, dass das Studio-Brain-Fenster non-modal ist und parallel zum Main-Window offen bleiben kann.
49. Als Editor will ich, dass Fenstergröße und letzter Tab gemerkt werden, damit ich beim nächsten Öffnen direkt weiterarbeiten kann.
50. Als Editor will ich, dass keine externen Netzwerkcalls für Studio-Brain-Kern-Funktionen nötig sind — alles offline.
51. Als Editor will ich, dass neue Dependencies (umap-learn, pyqtgraph, networkx) klein und lizenzkompatibel sind (MIT/BSD).
52. Als Editor will ich, dass die bestehende GPU-basierte Analyse-Pipeline (SigLIP/RAFT/Gemma/DEMUCS/beat_this) unverändert weiterläuft — Studio Brain fügt hinzu, ersetzt nicht.

---

## Implementation Decisions

### Schichten-Architektur

Das Studio Brain besteht aus drei strikt getrennten Schichten und einem separaten UI-Fenster:

- **Struktur-Layer** — statisch, aus Pipeline-Outputs abgeleitet (Role, Mood-refined, Style-Bucket, Compat-Graph). Read-only für den Agent, wird nur vom Enrichment-Worker geschrieben.
- **Gedächtnis-Layer** — temporal, append-only. Jede Pacing-Entscheidung + User-Feedback wird mit vollem Kontext-Snapshot gespeichert. Patterns werden periodisch aggregiert.
- **Agent-Layer** — liest Struktur + Gedächtnis. Schreibt ausschließlich ins Gedächtnis.

### Deep Modules (isoliert testbar)

- **RoleClassifier** — regelbasierter Zuordner, Input-Features → `(role, confidence)`. Regeln aus YAML.
- **MoodAnchorMatcher** — Cosine-Similarity gegen 10 vorberechnete SigLIP-Text-Anker; mischt bestehende `ai_mood` als Prior.
- **StyleBucketClusterer** — UMAP (n_components=10, n_neighbors=30, min_dist=0.0, metric=cosine) als Preprocessing → HDBSCAN (min_cluster_size=8, min_samples=5). Persistiert einen versionierten Reducer.
- **CompatGraphBuilder** — Top-K Cosine-Nearest-Neighbors auf SigLIP-Embeddings (via bestehendem `vector_db_service`-Cache).
- **PacingScorer** — vektorisierte NumPy-Matrix-Berechnung über 10+ Scoring-Terme, gewichtet aus YAML-Profil. Output: `(score, term_contributions)`.
- **VariationsBudget** — Sliding-Window-Zähler pro Bucket-Key, mit Segment-basiertem Reset bei DJ-Mixen.
- **PatternAggregator** — berechnet `mem_learned_pattern`-Zeilen aus `mem_decision` + User-Feedback mit Wilson-Lower-Bound-Confidence (z=1.96).
- **DecisionRecorder** — persistiert `mem_decision` mit vollem Audio-/Video-Kontext-Snapshot.
- **WilsonLowerBound** — reine Funktion `(accepts, total, z) → lower_bound`, mit Spezialfall `0/0 → 0.5`.

### Neue Services und Worker

- **`services/brain_service.py`** — aggregierte Read-Views für UI, gecacht, invalidiert bei Enrichment-/Run-Events.
- **`services/backup_service.py`** — triggert DB-Snapshots vor destruktiven Aktionen und täglich; Rolling-Window letzter 14.
- **`workers/structure_enrichment.py`** — orchestriert die vier Enrichment-Schritte; registriert als neuer `AnalysisStatus.VIDEO_STEPS`-Eintrag `structure_enrichment`.
- **`workers/memory_updater.py`** — asynchrone Pattern-Re-Aggregation; Trigger: nach Run-Ende oder nach 20 neuen Feedback-Events.

### Neue UI-Module

- **`ui/studio_brain_window.py`** — `QMainWindow`-Singleton mit 4 Tabs (Struktur / Gedächtnis / Audit / Steer). Non-modal, Schließen versteckt. Eigene QSettings-Section.
- **`ui/story_map_dialog.py`** — on-demand `QDialog`, nicht modal, zoomable, PNG/SVG-Export.
- **Feedback-Shortcuts** — Integration in bestehenden Timeline-Controller (kein neues Modul).

### Modifikationen bestehender Module

- **`agents/pacing_agent.py`** — Ersetzung der bisherigen Scoring-Logik durch 4-stufige Entscheidungs-Pipeline (Hard-Rules → Budget → Kollision → Soft-Scoring).
- **`services/onset_rhythm_service.py`** — Erweiterung um Per-Structure-Segment-Chunking; 2 s Overlap, Backtracking an Segment-Grenzen, 100 ms Fade-in-Discard. Output-Schema bleibt identisch.
- **`services/analysis_status_service.py`** — Registry-Erweiterung um `structure_enrichment`.

### Datenmodell

**Struktur-Layer-Tabellen** (fachliche Haltung: 1:1 pro Scene, aus Pipeline):
- `struct_clip_tags` (PK = scene_id, Role/Mood/Style/Confidences/Version)
- `struct_style_bucket` (Cluster-Zentrum + Beschreibung, inkl. 1152-dim Centroid-BLOB)
- `struct_compat_edge` (ungerichtete Speicherung, aber beide Richtungen als Rows für Query-Einfachheit)

**Gedächtnis-Layer-Tabellen** (temporal, append-only):
- `mem_pacing_run` — ein Eintrag pro Run, inkl. archivierter Steer-Snapshot und Weights-Profile-Name
- `mem_decision` — ein Eintrag pro Cut, mit vollem Audio-/Video-Kontext-Snapshot und Agent-Rationale als JSON
- `mem_learned_pattern` — aggregierte Patterns (Typen: `context_preference`, `clip_blacklist`, `clip_whitelist`, `style_affinity`)
- `mem_user_feedback_event` — jeder Feedback-Event (accept/reject/skip/rate/replace)

**Design-Entscheidung — Denormalisierung:** `mem_decision` speichert Audio-Kontext als Snapshot (nicht per Foreign-Key zu `beatgrid`/`structure_segment`), weil Re-Analysen sonst historische Entscheidungen rückwirkend verändern. Snapshot = immutable truth.

### Pipeline-Design

Die Enrichment-Pipeline besteht aus vier Schritten, alle CPU-basiert, ausgelöst nach `scene_db_storage=done`:

1. `RoleClassifier` — pro Scene, schnell (~2 ms).
2. `MoodAnchorMatcher` — pro Scene, schnell (~0.5 ms).
3. `StyleBucketClusterer` — library-weit, UMAP+HDBSCAN. Initial ~3–20 s; Re-Fit bei ≥ 50 neuen Clips oder manuell.
4. `CompatGraphBuilder` — pro Clip, Top-20 Nearest-Neighbors.

### Agent-Scoring

Formel:

```
score(clip, context) =
    w_role        × role_fit(section, clip.role)
  + w_style       × style_compat(predecessor, clip)
  + w_mood_video  × mood_match(audio.mood, clip.mood_refined)
  + w_mood_audio  × mood_match(audio.mood_audio, clip.mood_refined)
  + w_genre       × genre_prior(audio.genre, clip.style_bucket)
  + w_key         × key_prior(audio.key, clip.mood_refined)
  + w_tension     × tension_fit(audio.harmonic_tension, clip.role)
  + w_energy      × energy_match(audio.energy, clip.motion_score)
  + w_spectral    × spectral_fit(audio.spectral_hash, clip)
  + w_groove      × groove_fit(audio.groove_template, clip.motion_score)
  + w_memory      × historical_accept_rate(context_fingerprint, clip)
  - w_collision   × collision_penalty(predecessor, clip)
  - w_freshness   × staleness_penalty(clip, window)
```

Alle Gewichte YAML-konfigurierbar, pro Genre ein Profil (`config/pacing_weights/{default|psytrance|house|dj_mix_auto}.yaml`). DJ-Mix-Erkennung wechselt Profil mid-run pro Structure-Segment.

### Quantifizierte Success-Metrics

- **Enrichment-Latenz:** ≤ 80 s für 5000 Scenes auf CPU.
- **Agent-Scoring-Latenz:** ≤ 20 ms pro Cut-Entscheidung bei 500 Kandidaten.
- **Feedback-Keystroke-to-Persist:** ≤ 100 ms.
- **DJ-Mix-Kapazität:** 3 h Mix verarbeitbar bei ≤ 2 GB Peak-RAM.
- **Lernkurve:** ab Run #10 muss die Accept-Rate messbar über Baseline-Run liegen (konkret: mind. 15 % relative Verbesserung der Accept-Rate auf vergleichbaren Context-Fingerprints). Die genaue Schwelle wird in Phase 4 (Machbarkeit) kalibriert.
- **Mood-Anchor-Orthogonalität:** paarweise Cosine-Similarity der 10 Anchors < 0.5.
- **Golden-Run-Reproduzierbarkeit:** `mem_decision`-Snapshot byte-identisch über PRs (modulo Timestamps).

### Neue Dependencies

- `umap-learn>=0.5` (MIT) — für Style-Bucket-Preprocessing.
- `pyqtgraph>=0.13` (MIT) — für Plots (Tension-Kurve, Segment-Strip, Story-Map).
- `networkx>=3.0` (BSD) — für Force-Directed-Graph-Layout (offline berechnet, Positionen gecacht).

Bereits installiert und nutzbar: `scikit-learn==1.8.0` (inkl. `sklearn.cluster.HDBSCAN`), `alembic==1.15.1`, PySide6-Stack, NumPy, SQLAlchemy.

### Migrationsstrategie

Drei neue Alembic-Migrationen in `database/alembic/versions/`:

1. `add_struct_layer_tables` — Struktur-Tabellen und Indizes.
2. `add_memory_layer_tables` — Gedächtnis-Tabellen und Indizes.
3. `extend_analysis_status_enum` — Registry-Erweiterung um `structure_enrichment`, Data-Migration für bestehende Zeilen.

Jede Migration mit funktionierender Up- und Down-Richtung.

Bezüglich der bestehenden `AIPacingMemory`-Tabelle: Fachlich ist sie ein Vorläufer von `mem_learned_pattern`. Das PRD lässt offen, ob migriert, dual-betrieben oder deprecated wird — das ist Entscheidung in Phase 5 (Plan).

### Konfigurations-Dateien (neu)

- `config/enrichment_rules.yaml` — Role-Classifier-Regeln, Mood-Anchor-Mixing-Prior.
- `config/pacing_rules.yaml` — Section × Role Matrix, Key × Mood Gate.
- `config/pacing_weights/default.yaml` + `psytrance.yaml` + `house.yaml` + `dj_mix_auto.yaml`.
- `config/mood_anchors.npz` (generiert) + `config/mood_anchors_v1.yaml` (Prompt-Katalog).

---

## Testing Decisions

### Prinzip

Wir testen **externes Verhalten** der deep modules, nicht Implementation-Details. Jedes deep module ist durch sein Interface prüfbar, ohne auf interne Zustände zurückzugreifen. Die Test-Pyramide orientiert sich an bestehenden Patterns in `tests/` (Unit in `tests/<domain>/`, Integration in `tests/integration/`, UI in `tests/ui/` mit `QT_QPA_PLATFORM=offscreen`).

### Was getestet wird

**Alle deep modules einzeln:**
- `RoleClassifier`: Coverage aller if/elif-Zweige über 30+ Fixture-Szenarien mit (motion, duration, tags)-Tupeln und erwarteten Outputs.
- `MoodAnchorMatcher`: 10 synthetische Embeddings nah an jedem Anchor; Prior-Mixing-Gewicht validiert.
- `StyleBucketClusterer`: drei synthetische Cluster → HDBSCAN muss sie finden; UMAP-Reducer pickle-roundtrip-bar.
- `CompatGraphBuilder`: Top-K-Korrektheit + Symmetrie-Handling.
- `PacingScorer`: Term-Contributions summieren sich zum Gesamt-Score; Gewichts-0-Test (Term liefert 0 Beitrag); Negativ-Score-Handling.
- `VariationsBudget`: Zähler-Korrektheit über Sliding-Window; DJ-Mix-Segment-Reset.
- `PatternAggregator`: Wilson-Lower-Bound-Formel-Verifikation; Edge-Cases `0/0`, `1/1`, `100/100`.
- `DecisionRecorder`: alle Kontext-Felder korrekt gespeichert, JSON-Rationale parsebar.
- `WilsonLowerBound`: Pure-Function-Tests, inkl. Extremwerten und `0/0 → 0.5`-Fallback.

**Integrations-Tests:**
- `test_full_enrichment.py` — lade 20-Clip-Fixture, führe gesamten Enrichment-Worker aus, assert alle Zieltabellen gefüllt.
- `test_pacing_with_memory.py` — zwei Runs hintereinander, zweiter Run zeigt messbare Beeinflussung durch erstes Feedback.
- `test_dj_mix_3h.py` — synthetischer 3 h Audio mit bekannten Structure-Grenzen; Assertion: RAM-Peak ≤ 2 GB, Laufzeit finit.
- `test_alembic_migrations.py` — alle drei neuen Migrations up-down-roundtrip gegen leere und gefüllte DB.

**Test-Pyramide-Zusatz aus Research-Findings:**
- `test_umap_hdbscan_pipeline.py` — pickle-Reproduzierbarkeit des Reducers; Dim-Consistency; neue Embeddings sind transformable ohne Re-Fit.
- `test_mood_anchor_orthogonality.py` — paarweise Cosine-Similarity der 10 Anchors < 0.5.
- `test_onset_chunked_boundary.py` — synthetischer Onset genau an Segment-Grenze darf nicht doppelt erkannt werden; Chunk-Fade-in-Artefakte verworfen.

**UI-Tests (headless):**
- `test_studio_brain_window.py` — Fenster öffnet, alle 4 Tabs rendern ohne Crash mit Test-Daten.
- `test_feedback_shortcuts.py` — A/R/S/1-5 in Timeline-Focus erzeugt `mem_user_feedback_event` mit korrekter Payload.

**Golden-Run-Snapshot-Test:**
- Kuratierter Test-Mix (~ 5 min, bekannte Structure) + 20-Clip-Library. `mem_decision`-Tabelle muss byte-identisch (modulo Timestamps) über PRs reproduzierbar sein. Fangt Scoring-Regressionen.

### Definition of Done pro Sub-Komponente

- `mypy --strict` clean auf neuen Modulen.
- Black-formatiert.
- ≥ 80 % Test-Coverage auf neuen Dateien (pytest-cov).
- Jede Alembic-Migration up + down grün auf leerer und gefüllter Test-DB.
- UI-Offscreen-Test grün.
- README-Abschnitt oder `docs/`-Kurz-Anleitung vorhanden.

### Prior Art / Referenz-Patterns

- Bestehende Test-Struktur in `tests/` (Unit pro Domain, Integration separat).
- SQLite-WAL-Mode bereits aktiv (`database/session.py:129`) — konkurrente Reads + ein Writer safe.
- AnalysisStatus-Registry in `services/analysis_status_service.py` — bewährtes Pattern für Pipeline-Schritt-Tracking; wir erweitern sie, statt Parallel-Struktur aufzubauen.

---

## Out of Scope

Die folgenden Ideen sind bewusst **nicht** Teil dieses PRDs. Sie sind als Phase-2-Follow-ups dokumentiert.

### Phase-2-Features (ausdrücklich später)

- **ML-basierter Role-Classifier.** Phase 1 nutzt Regel-Baum aus YAML. Ein gelernter Classifier (z. B. trainiert auf dem akkumulierten User-Feedback) wird erst wertvoll, wenn das Gedächtnis genug Daten hat, und ist dann eigenständige Feature-Iteration.
- **LLM-basierte Style-Bucket-Namensgebung.** Cluster-Namen kommen in Phase 1 aus häufigsten `ai_caption.tags` der Mitglieder. Eine Gemma-/Qwen-generierte Prägnanz-Benennung ist Nice-to-have, aber nicht blockierend.
- **Cross-Projekt-Pattern-Sharing / Transfer-Learning.** Das Gedächtnis eines Projekts wird in Phase 1 nicht in andere Projekte portiert. Erst wenn Pattern-Formate stabil sind.
- **Export des Gedächtnisses als anonymisierter Datensatz.** Für Training zukünftiger Modelle; Phase-2.

### Explizit ausgeschlossene Design-Entscheidungen

- **Externe Obsidian-Integration.** Das Studio Brain ist App-intern und nicht Teil des Brain-Bug-Vaults. Kein Markdown-Export in einen externen Vault. Brain-Bug bleibt Entwicklungs-Wiki.
- **App-Wechsel für Library-Ansicht.** Alles passiert in PB Studio; das Studio-Brain-Fenster ist separat, aber Teil derselben Anwendung.
- **Manuelles Labeling von Clips durch den User.** Source-of-Truth ist die Auto-Pipeline. Steer-Overrides pro Run sind erlaubt, aber das sind Run-scoped Interventionen, keine permanenten Labels.
- **Audio-Analyse-Neuentwicklung.** Bestehende Analyse-Services (`BeatAnalysisService`, `KeyDetectionService`, `StructureDetectionService`, `OnsetRhythmService` etc.) werden konsumiert, nicht ersetzt. Nur `OnsetRhythmService` wird für DJ-Mix-Chunking minimal erweitert.
- **Graph-Visualisierung via externem Node-Editor** (NodeGraphQt und ähnliche). Wurde in Research verworfen (nicht geeignet für Similarity-Graphen). Eigener `QGraphicsScene`-Renderer.

---

## Further Notes

### Aus Research abgeleitete Warnungen (behalte im Auge)

- **Onset-Chunking ist Eigenbau.** `librosa` bietet keine offizielle Streaming-Strategie. Unser Per-Segment-Pattern muss durch drei explizite Tests abgesichert werden (Boundary-Overlap, 3h-Regression, Memory-Peak).
- **Mood-Anchor-Prompts sind unbenchmarked.** Die vorgeschlagenen Prompts für die 10 Mood-Klassen sind aus der Literatur abgeleitet, aber nicht publiziert-evaluiert. Erst-Release braucht eine Kalibrierungs-Runde auf einem annotierten Mini-Set (30–50 Clips), und die Orthogonalitäts-Prüfung (< 0.5 paarweise) ist Akzeptanz-Kriterium.
- **UMAP-Reducer strikt versionieren.** Der persistierte `UMAP`-Reducer ist Teil der Enrichment-Version. Bei Version-Wechsel müssen bestehende `mem_decision`-Einträge (Snapshot) unverändert bleiben, aber `struct_clip_tags` neu berechnet werden. Disziplin beim Enricher-Version-Pinning ist nicht-trivial und muss in den Plan als explizite Regel.
- **Wilson bei 0/0 darf nicht 0 liefern.** Neue Clips ohne Feedback-Historie bekommen `historical_accept_rate = 0.5` (neutral „weiß nichts"), nicht `0` (würde heißen „schlecht, vermeiden"). Code-Detail, aber kritisch.

### Offene Entscheidungen für Phase 4 (Machbarkeit)

- **UMAP-Reducer-Re-Fit-Häufigkeit** — konkrete Schwelle ist in der Literatur nicht etabliert; Vorschlag Phase 1: ≥ 50 neue Clips triggert Re-Fit. Machbarkeit prüft, ob das bei realistischen Libraries zu häufig/zu selten ist.
- **Force-Directed-Layout-Performance** bei > 2000 Knoten. Falls reale Library größer wird, Fallback auf Grid-Only automatisch.
- **SigLIP-2-Migration** (Feb 2025 Release). Drop-in bei gleicher Dim (1152), aber erfordert Re-Encoding aller Scenes (geschätzt 4 min bei 5000 Scenes). Machbarkeit entscheidet: jetzt oder in v1.1.
- **Accept-Rate-Lernkurven-Messung** — was ist die faire „Baseline-Accept-Rate", gegen die wir die Verbesserung messen? Vorschlag: erste 3 Runs ohne `w_memory` im Scoring (Patterns haben noch keine Confidence), ab Run 4 mit Memory-Term. Machbarkeit prüft, ob das methodisch sauber ist.

### Success-Messung in Produktion

Nach der ersten Release-Welle (Phase 5 abgeschlossen) schlägt das PRD folgende laufende Messungen vor:

- **Per-Run:** Accept-Rate (User-Verdict-Anteil `accept` an allen reviewten Cuts), Fallback-Rate (wie oft Stufe 1 weichen musste), Budget-Auslöse-Rate.
- **Rollierend über N letzte Runs:** Lernkurve der Accept-Rate; soll monoton steigend bei konstantem Library-Umfang.
- **Per-Library:** Mood-Coverage (Lücken in den 10 Mood-Klassen), Style-Bucket-Verteilung (Noise-Anteil als Indikator für heterogene Library).

Diese Metriken sind nicht-blockierend und nicht Teil der Akzeptanz-Kriterien dieses PRDs, aber als Telemetrie-Dashboard im Studio-Brain-Fenster (Gedächtnis-Tab Stats-Panel) sichtbar.

### Entscheidungsprotokoll

Die folgenden Design-Entscheidungen wurden explizit mit dem User getroffen und sind der Spec/dem Research dokumentiert:

- Ansatz **H** (Struktur + Gedächtnis) statt A (nur Struktur) oder M (nur Gedächtnis) — deckt alle drei Ziele zu 100 %.
- **Auto-Only** (keine manuellen Labels) — Skalierbarkeit bei 500+ Clips.
- **In-App** (kein Brain-Bug-Sync, kein Obsidian-Export) — App-interne Intelligenz, Brain-Bug bleibt Entwicklungs-Vault.
- **Alle 10+ Scoring-Terme in Phase 1** verdrahtet — konsistenter Decision-Context-Snapshot ab Run #1.
- **CPU-only Enrichment** — GPU bleibt für bestehende Analyse-Pipeline frei.
- **Feedback-UI in Timeline**, nicht im Studio Brain — Feedback im Review-Flow.
- **Pyqtgraph als neue Dependency** — Verifikation: weder pyqtgraph noch matplotlib derzeit installiert; pyqtgraph ist die saubere Wahl.
- **sklearn.cluster.HDBSCAN** (in scikit-learn 1.3+) statt separater `hdbscan`-Dependency.

---

**Ende PRD.**
