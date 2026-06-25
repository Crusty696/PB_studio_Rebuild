# PROPOSAL — App-Sync-Restruktur Brain V3 Plan

> **STATUS: SUPERSEDED am 2026-05-05.**
> Dieser Vorschlag wurde beantwortet und in den aktiven Plan
> eingearbeitet. Aktuelle Wahrheit:
> - Vault-Decisions: `D-034`, `D-035`, `D-036` (alle adopted) unter
>   `C:\Brain-Bug\projects\pb-studio\wiki\decisions\`
> - Aktive Plan-Dateien (gleicher Ordner wie diese Datei):
>   `README.md`, `01_ARCHITECTURE.md`, `02_DECISIONS.md`,
>   `04_DATA_MODEL.md`, `05_BRIDGE_AXES.md`, `06_PHASES.md`,
>   `07_RISKS.md`, `11_REVERIFICATION_PHASE3_2026-05-05.md`,
>   `phase_blueprints/phase_4_pacing_integration.md`,
>   `phase_blueprints/phase_5_pyside6_ui.md`,
>   `phase_blueprints/phase_6_haertung.md`,
>   `phase_blueprints/README.md`.
> - Spike-Synthesis: `../synthesis/2026-05-05-pre-phase4-spike.md`
> - Vault-Log: `[2026-05-05] refactor` in
>   `C:\Brain-Bug\projects\pb-studio\log.md`
>
> Diese Datei ist nur noch als historisches Dokument relevant — sie
> zeigt den Zustand VOR der Adoption von F1-F5 + M1-M3 + L1-O3.

> **Original-Header (historisch):** PROPOSAL — wartet auf User-Freigabe.
> Diese Datei ist KEIN Teil des aktiven Plans. Sie liegt im Plan-Ordner
> nur zur Sichtbarkeit. Bestehende Plan-Dateien (`01_…` bis `11_…`,
> `phase_blueprints/*`) sind UNVERAENDERT. Code ist UNVERAENDERT.
>
> **Datum:** 2026-05-05
> **Anlass:** User-Aussage „passe den plan so, dass immer die bestehende
> APP-Seite an die neue Entwicklung — das Hirn — angepasst wird".
> **Geltungsbereich:** Nur Plan-Restruktur und Vorschlag, was zu tun
> waere. Kein Edit am Plan, kein Edit am Code, bis User freigibt.

---

## 0. Kernbefund in einem Satz

Der bestehende Plan baut das Brain V3 strikt isoliert in Phase 1–3,
plant die App-Verdrahtung erst in Phase 4 (Pacing) und Phase 5 (UI) —
und genau diese spaete Verdrahtung ist der Punkt, an dem der Plan an
der App-Realitaet vorbeigeht. Mehrere im Plan benannte App-Datei-Pfade
und die im Plan vorausgesetzte FastAPI-Architektur existieren in der
Code-Basis nicht.

---

## 1. Stand der Verifikation (Plan-Doc gelesen + Code-Grep)

### 1.1 Was der Plan sagt

| Quelle | Aussage |
|---|---|
| `README.md` | Phase 0–3 DONE, Phase 4 ist „naechster Schritt" |
| `06_PHASES.md` Phase 1 DoD | „Mix-Import-Hook synchron im audio_router NICHT geliefert (V1/V2-Touch noetig, blockiert bis explizite Freigabe)" |
| `06_PHASES.md` Phase 2 DoD | „Mix-Import-Hook synchron NICHT geliefert (V1/V2-Touch noetig, blockiert)" |
| `01_ARCHITECTURE.md` | UI ↔ FastAPI ↔ Core, REST + SSE auf `localhost:8765` |
| `phase_4_pacing_integration.md` | Hook in `services/pacing/clip_selector.py` Funktion `select_clip()`. 5 REST-Endpoints unter `/brain_v3/*`. Erweiterung von `backend/schemas/pacing_schemas.py` und `backend/main.py` |
| `phase_5_pyside6_ui.md` | UI ruft Backend ueber `BrainV3ApiClient` (HTTP, `localhost:8765`) |
| Vault-Spiegel (laut `11_REVERIFICATION_PHASE3_2026-05-05.md`) | Phasen 1, 2, 3 stehen mit Status `code-fix-pending-live-verification` (nicht `fixed`) |

### 1.2 Was der Code wirklich enthaelt (Grep-Verifikation)

| Plan-Annahme | Real im Repo |
|---|---|
| `backend/main.py`, `backend/schemas/pacing_schemas.py` | **kein `backend/`-Ordner vorhanden** |
| `routers/brain_v3_router.py` | **kein `routers/`-Top-Level-Ordner** |
| `services/pacing/clip_selector.py` mit `select_clip()` | **existiert nicht** |
| FastAPI-App / Uvicorn-Server / `localhost:8765` | **`from fastapi` / `import fastapi` taucht NUR in Plan-Docs auf, in keinem `.py` der Code-Basis** |
| Pacing-Selektion-Funktion | **`services/pacing/pipeline.py` mit Klasse `PacingPipeline.select_best()`** |
| Mix-Import-Pfad | **`ui/controllers/import_media.py` `_import_audio()` → `FolderImportWorker` (QThread, in-process)** |
| Brain-V3-Aufruf irgendwo in `ui/` oder `services/pacing/` | **Grep „brain_v3" in `ui/` → 0 Treffer; in `services/pacing/` → 0 Treffer** |
| `services/brain_v3/__init__.py` Phasenstatus-Doku | sagt: „Phase 1: IN PROGRESS, Phase 2: TODO, Phase 3: TODO" — widerspricht der Plan-`README.md`, die alle drei als DONE markiert |

### 1.3 Was daraus eindeutig folgt

PB Studio Rebuild ist eine reine PySide6-In-Process-Anwendung. Der
ueber zwei Plan-Dokumente verteilte FastAPI-Layer existiert nicht.
Der `clip_selector.select_clip()`-Hook, an dem Phase 4 ansetzen soll,
existiert nicht. Brain V3 wurde gemaess Plan in Phase 1–3 implementiert
und mit 112 Pytests live gegruent — aber von der App wird kein
einziger V3-Codepfad aufgerufen. Hashing, Embeddings, Brain-Core sind
fertig, aber tot in dem Sinne, dass beim echten Mix-Import in der App
nichts davon angefasst wird. Genau das ist der von dir benannte
Planungs­schmerz, in Plan-Sprache uebersetzt.

---

## 2. Konkrete Planungsprobleme (mit Beleg)

### P1 — Plan baut auf einer FastAPI-Architektur, die im Code nicht existiert
- **Beleg:** siehe 1.2.
- **Konsequenz:** Phase 4 ist in der jetzigen Form nicht implementierbar
  ohne **vorher** zu entscheiden, ob a) eine FastAPI-Schicht neu
  aufgebaut wird, oder b) der Plan auf in-process direkten
  Funktionsaufruf umgestellt wird.

### P2 — Plan benennt nicht-existierende Datei-Pfade
- **Beleg:** `clip_selector.py.select_clip` taucht ausschliesslich in
  Plan-Docs und in `services/brain_v3/__init__.py` (Doku-Kommentar) auf.
  Echte Funktion: `pipeline.py.PacingPipeline.select_best()`.
- **Konsequenz:** Phase-4-Blueprint Sektion 3 + 4.6 sind unausfuehrbar
  ohne Rename-Mapping.

### P3 — App-Sync-Luecke seit Phase 1, niemals geschlossen
- **Beleg:** Phase 1 + Phase 2 fuehren beide den gleichen Punkt als
  „NICHT geliefert" auf: „Mix-Import-Hook synchron, blockiert bis
  explizite Freigabe". Phase 3-Synthesis hat das nicht aufgegriffen.
- **Konsequenz:** Auch wenn Phase 4 morgen Code-fertig waere, wuerde
  beim echten Mix-Import in `import_media.py` immer noch nichts
  passieren, weil die App die V3-Pipeline nicht ruft. Phase 5 setzt
  vorraus, dass „Realer Mix + 500 Clips" Embeddings hat — die werden
  aber nirgendwo erzeugt, weil der Hook fehlt.

### P4 — Drei Phasen auf `code-fix-pending-live-verification`
- **Beleg:** Vault-Spiegel laut `11_REVERIFICATION_PHASE3_2026-05-05.md`
  Sektion B.3.
- **Konsequenz:** Phase 0 ist die einzige Phase mit Status `fixed`.
  Alle Code-Pfade von Phase 1, 2, 3 sind nur in pytest gegruent, niemals
  unter realer App-Last. Die 112 Pytests testen die V3-Module
  intern, aber nicht das Zusammenspiel mit dem Pacing-Code, der
  Background-Queue der App, dem QThread-Lifecycle, dem GpuSerializer
  unter NVENC-Coexistenz oder dem realen Mix-Import-Flow.

### P5 — Plan-Doc-Drift gegen Code-Doku
- **Beleg:** `README.md` markiert Phase 0–3 als DONE,
  `services/brain_v3/__init__.py` sagt „Phase 1: IN PROGRESS".
- **Konsequenz:** Bei naechster Session-Wiederaufnahme muss der Agent
  raten, welche Quelle die Wahrheit ist. AGENTS.md verbietet Raten.

### P6 — App-Anpassung konzentriert in Phase 4 + Phase 5
- **Beleg:** `06_PHASES.md` Phase 1–3 enthalten reine Service-Tasks.
  App-Eingriffspunkte tauchen erst in Phase 4 und Phase 5 auf.
- **Konsequenz:** Architektur-Annahmen aus Phase 1–3 (z. B.
  Background-Queue-Subscription-Modell, GpuSerializer-Lock-Strategie,
  17-Achsen-Schema) werden erst in Phase 4 gegen die App-Realitaet
  geprueft. Falls eine Annahme bricht, ist der Refactor teuer, weil
  dann schon 30 Files in `services/brain_v3/` darauf basieren.

### P7 — „V1/V2 unangetastet" laesst sich auf zwei Arten lesen
- Der Plan sagt mehrfach: V1/V2 bleibt UNTOUCHED (`02_DECISIONS.md` #24,
  `phase_5_pyside6_ui.md`).
- Lesart A: V1-Brain-Code (`services/brain_service.py`) und V2-Brain-Code
  (`services/brain_v2/`, `ui/studio_brain/brain_v2_tab.py`) bleiben
  unveraendert.
- Lesart B: die ganze App bleibt unveraendert, also auch
  `import_media.py`, `pipeline.py`, `main_window.py`.
- Die Phase-4- und Phase-5-Blueprints zeigen, dass Lesart A gemeint
  ist (sie planen ja explizite App-Eingriffe). Aber der Plan sagt es
  nicht so klar, dass es nicht missverstanden werden koennte.
- **Konsequenz:** Genau dieser Missverstaendnis-Spielraum hat in
  Phase 1 dazu gefuehrt, dass der Mix-Import-Hook „blockiert bis
  explizite Freigabe" stehengeblieben ist.

---

## 3. Restruktur-Vorschlag — Hirn waechst, App waechst mit

### 3.1 Leitprinzip
Jede Phase, die ein Hirn-Stueck baut, traegt zusaetzlich einen
**App-Sync-Block** mit folgenden Pflicht-Tasks:

1. **App-Hook setzen:** der bestehende App-Pfad ruft das neue
   Hirn-Stueck mindestens einmal in seinem natuerlichen Ablauf auf.
2. **Live-Smoke in der App:** nicht nur Pytest, sondern mindestens
   ein User-Workflow (Klick im Echtbetrieb), der den neuen Code
   anlaeuft. Logs werden ausgewertet.
3. **Status-Discipline:** erst nach Live-Smoke darf der Phase-Status
   von `code-fix-pending-live-verification` auf `fixed` ruecken — und
   das setzt ohnehin User der Marker, nicht Agent.

### 3.2 Konkrete Map (Vorschlag, nicht Beschluss)

| Phase | Hirn-Stueck (bereits geplant / vorhanden) | App-Sync (neu, oder nachgeholt) |
|---|---|---|
| **1** (DONE laut Plan) | `hashing.py`, `paths.py`, `schemas/audio.py`, `schemas/video.py`, `subtrack_detector.py`, `visual_curves.py` | NACHHOLEN: Hook in `ui/controllers/import_media.py` `_import_audio()` ruft `services.brain_v3.hashing.compute_media_hash` und legt das Hash-Result in V3-Schema-DB ab. Live-Smoke: real einen Mix importieren, Hash in DB pruefen. |
| **2** (DONE laut Plan) | `audio_embedder.py`, `video_embedder.py`, `embedding_cache.py`, `embedding_repository.py`, `background_queue.py`, `gpu_serializer.py` | NACHHOLEN: nach Hash-Set in Phase 1 fuegt `import_media._process_imports` den Clip in die `BackgroundQueue` als Embedding-Job ein. UI zeigt Worker-Progress (kann erstmal Konsole sein). Live-Smoke: 5 echte Clips importieren, Embeddings auf Disk pruefen, Re-Import → Cache-Hit-Pfad. |
| **3** (DONE laut Plan) | `brain_store.py`, `weight_store.py`, `feedback_logger.py`, `bridge_dimensions.py`, `context_resolver.py`, `cold_start.py`, `scorer.py` | NACHHOLEN: minimaler in-process Diagnose-Pfad — App startet, beim Boot wird `brain_store.health_check()` ausgefuehrt, Result loggen. Live-Smoke: App starten, Log auf Hirn-Store-Pfade pruefen, manuell ein Mock-Klick-Event durch `feedback_logger.log_feedback` jagen, anschliessend `weight_store.lookup` darauf reagiert. |
| **4** | `reranker.py`, `smart_sampler.py`, `state_store` (Migration `state/001_initial.sql`) | UMGESCHRIEBEN: Hook NICHT in `clip_selector.select_clip` (existiert nicht), sondern in **`services/pacing/pipeline.py` `PacingPipeline.select_best()`** als optionaler Reranker-Aufruf hinter einem `use_brain_v3`-Flag, das aus der Pipeline-Config kommt (nicht aus einer FastAPI-Schema-Datei). Feedback-Empfang ist eine **direkte Python-Funktion** (`brain_v3.feedback.handle_rating(cut_id, rating)`), aufgerufen aus dem PySide6-Slot — keine REST-Schicht in dieser Iteration. |
| **5** | UI: `cut_feedback_popup`, `stats_panel`, `learning_session_dialog`, `reset_dialog`, `confidence_overlay`, `brain_v3_tab` | App-Sync ist hier ohnehin der Phasen-Inhalt. Statt `BrainV3ApiClient` (HTTP) wird ein in-process **`BrainV3Service`-Wrapper** verwendet, der die Service-Methoden direkt ruft. Hotkeys 1–4 + Right-Click-Hook am echten Timeline-Cut-Item (`ui/timeline.py` oder `ui/widgets/...` — Dateipfad wird vor Edit verifiziert). |
| **6** | Backup, Recovery-Test, NVENC-Konflikt, Lizenz | App-Sync: Recovery-Test laeuft am realen App-Boot (nicht nur Pytest). NVENC-Konflikt-Test wird waehrend einer realen Render-Session gemessen. |

### 3.3 Was das fuer die Plan-Dateien bedeutet (Diff-Skizze)

| Plan-Datei | Aenderung (Skizze, NICHT durchgefuehrt) |
|---|---|
| `06_PHASES.md` | Pro Phase 1–6 einen neuen Abschnitt **„App-Sync"** unter „Aufgaben" einfuegen, mit den Tasks aus 3.2. DoD pro Phase um **„App-Live-Smoke gruen, Logs ausgewertet"** erweitern. |
| `01_ARCHITECTURE.md` | Den UI-↔-FastAPI-Pfeil ersetzen durch UI-↔-`BrainV3Service`-Direkt-Aufruf. FastAPI-Schicht wird in der Architektur ausdruecklich als **„nicht in V3-Scope"** markiert. (Falls FastAPI doch gewollt: separate Phase 4.5 als Option.) |
| `phase_4_pacing_integration.md` | Sektion 3 + 4.6 grundlegend anpassen: `clip_selector.select_clip` → `pipeline.py.PacingPipeline.select_best`. Sektion 4.5 (`brain_v3_router`) entfaellt oder wird als optionaler Folge-Spike markiert. Sektion 4.6 (`backend/schemas/pacing_schemas.py`) durch realen Pfad ersetzen — der Pacing-Config-Dataclass-Pfad ist im Code zu suchen, **vor** Edit. |
| `phase_5_pyside6_ui.md` | `BrainV3ApiClient` → `BrainV3Service` (in-process). Dependencies auf REST-Endpoints durch direkte Service-Aufrufe ersetzen. UI-isoliert in `ui/brain_v3/` bleibt erhalten. |
| `03_TECH_STACK.md` | Pruefen ob FastAPI / uvicorn als Pflicht-Dep gelistet — falls ja, klarstellen dass nicht in V3-Scope. |
| `README.md` | Nach Beschluss: Phase-3-Status auf `services/brain_v3/__init__.py` synchronisieren (oder umgekehrt). Aktueller Drift muss vom User aufgeloest werden, nicht vom Agent. |

Phase-blueprints-Tabelle muss ein **State-Banner** „App-Sync nachgeholt
fuer Phase X — `pending` / `done`" zusaetzlich tragen, damit der
Phasen-Status nicht mehr nur „Pytest gruen" reflektiert.

---

## 4. Risiken dieses Vorschlags

| Risiko | Mitigation |
|---|---|
| Hook in `pipeline.py.select_best` ist Pacing-kritisch — falsch eingesetzt bricht Pacing fuer Nicht-V3-User | `use_brain_v3` Default auf `False`, Regression-Test gegen byte-identischen Pacing-Output ohne Flag |
| App-Sync nachgeholt fuer Phase 1–3 reisst die als DONE markierten Phasen wieder auf | Status der Phasen wird auf `code-complete-app-sync-pending` geaendert (neuer Status, NICHT `fixed`); User entscheidet pro Phase, ob Re-Markierung gewollt |
| In-process statt REST verbaut spaeter externen Brain-Aufruf (Web-UI, CLI-Tool) | Akzeptiert. V3-API bleibt eine reine Python-Schicht; ein REST-Wrapper kann in einer separaten Phase 4.5 nachgezogen werden, **wenn** Bedarf entsteht |
| `import_media.py`-Hook in Phase 1 nachgeholt ist „App anfassen" — kollidiert mit „V1/V2 untouched"-Lesart | Klarstellung Lesart A (siehe P7): `import_media.py` ist V0-App-Code, kein V1/V2-Brain-Code. Hook ist additiv, nicht ersetzend. |
| Brain-Store-Health-Check beim App-Boot kann Boot-Zeit verlaengern | Health-Check non-blocking in QThread, Boot blockiert nicht |

---

## 5. Offene Fragen — User-Entscheidung erforderlich

> Eine Frage pro Themenblock. Ich erwarte nicht alles auf einmal —
> Reihenfolge wie unten ist mein Vorschlag.

### F1 — Architektur-Grundsatzfrage (BLOCKER fuer alles weitere)
Bleibt Brain V3 in-process (PySide6-Direktaufruf), oder bauen wir eine
FastAPI-Schicht? Antwort entscheidet, wie die Phasen 4 + 5 umgeschrieben
werden. Mein Vorschlag: in-process (kuerzester Pfad zur lauffaehigen
App-Integration; REST kann spaeter als optionaler Wrapper).

### F2 — Lesart von „V1/V2 untouched"
Bestaetigst du Lesart A: V1-Brain-Code und V2-Brain-Code bleiben
unveraendert, aber V0-App-Code (`import_media.py`, `pipeline.py`,
`timeline.py`, `main_window.py`) darf an klar markierten Stellen mit
zusaetzlichen V3-Hooks erweitert werden? Mein Vorschlag: ja, Lesart A.

### F3 — Wie mit den als DONE markierten Phasen 1–3 umgehen?
Drei Optionen:
- (a) Phase-Marker bleibt DONE (Pytest-Wahrheit), App-Sync wird als
  separater Block „Phase X.5 — App-Sync nachgeholt" eingeschoben.
- (b) Phase-Marker wird auf `code-complete-app-sync-pending`
  zurueckgesetzt, App-Sync ist Teil der jeweiligen Phase, Phase
  geht erst auf DONE wenn App-Sync gruen.
- (c) Sofort vor Phase 4 ein „Phase 0.5"-Block: Mix-Import-Hook,
  Embedding-on-Import, Brain-Store-Health-Check werden gebuendelt
  abgearbeitet, dann erst Phase 4.

Mein Vorschlag: (b), weil es die Status-Discipline-Linie aus AGENTS.md
am ehrlichsten umsetzt. Aber das ist deine Entscheidung.

### F4 — Plan-vs-Code-Drift-Aufloesung
`README.md` sagt Phase 3 DONE, `services/brain_v3/__init__.py` sagt
Phase 1 IN PROGRESS. Welche Quelle stimmt? Ohne diese Antwort schlage
ich keine Aenderung an einer der beiden Quellen vor.

### F5 — `pipeline.py.select_best` als Hook akzeptabel?
Falls ja, schreibe ich `phase_4_pacing_integration.md` so um, dass es
auf den realen Funktionsnamen referenziert. Falls nein: bitte den
gewuenschten Eingriffspunkt benennen.

---

## 6. Empfehlung (mit Begruendung)

1. **F1 → in-process**, weil es den kuerzesten Pfad zur live verifizierten
   App-Integration ergibt und die V3-Module bereits Python-API-tauglich
   sind. REST kann jederzeit als duenner Wrapper nachgezogen werden,
   wenn echter Bedarf entsteht.
2. **F2 → Lesart A bestaetigen**, weil das die einzige Lesart ist, mit
   der „App passt sich an das Hirn an" ueberhaupt umsetzbar ist, ohne
   den V1/V2-Schutz aufzugeben.
3. **F3 → Option (b)**, weil sie der AGENTS.md-Definition von
   `fixed` (Live-verifiziert mit realem User-Workflow) am naechsten
   kommt. Die als DONE markierten Phasen sind nach dieser Definition
   genauer gesagt code-complete plus pytest, aber NICHT
   live-app-verifiziert.
4. **F4 → User entscheidet**, ich kann das nicht selbst.
5. **F5 → User bestaetigt nach Code-Inspektion** (Datei `pipeline.py`
   Zeile 145 zeigt die `select_best`-Signatur).

Wenn du F1, F2, F3, F5 in dieser Reihenfolge entscheidest, kann ich auf
dieser Basis einen konkreten **Plan-Edit-Patch-Vorschlag** schreiben:
welche Zeilen in welcher Plan-Datei wie geaendert werden, ohne dass
ich am Plan editiere bevor du den Patch siehst.

---

## 7. Was ICH NICHT entscheide

- ob Phase-Marker zurueckgesetzt werden (`fixed` → was anderes)
- ob FastAPI-Schicht doch gewollt ist
- ob `import_media.py` und `pipeline.py` als anfassbar gelten
- ob Phase 4.5 als FastAPI-Wrapper-Phase eingeschoben wird
- ob die existierenden Synthesis-Files in `docs/superpowers/synthesis/`
  und im Vault rueckwirkend nachgezogen werden muessen
- ob Skills neu gebaut werden — siehe Sektion 8

---

## 8. Skill-Einsatz (User-Direktive: „setze die passenden skills ein oder bau sie wenn sie fehlen")

### 8.1 Bestehende Skills, die zur Implementation passen wuerden

- `pb-master` — Cross-Module-Verdrahtung, Multi-Schicht-Bugs (UI ↔
  Service ↔ GPU). Genau richtig fuer den App-Sync-Hook in Phase 1–4.
- `pyqt6-threading` — Mix-Import-Hook in Phase 1 + Embedding-Job-Push
  in Phase 2 sind QThread-/Signal-Slot-Faelle. Pflicht-Skill fuer
  Phase 1+2 nachgeholt.
- `nvidia-cuda-vram` — relevant fuer Phase 6 NVENC-Coexistenz und beim
  realen 500-Clip-Lauf in Phase 5.
- `chromadb-vectors` — NICHT relevant, V3 nutzt sqlite-vec; Skill nur
  zum Vergleich.
- `audio-ml-pipeline` — relevant fuer CLAP-Embedder-Sanity in Phase 2.
- `video-ai-analysis` — relevant fuer SigLIP-2-Embedder in Phase 2.
- `gui-test-agent` / `auto-qa-loop` — relevant fuer den Live-Smoke pro
  App-Sync-Block.

### 8.2 Skill, der fehlen koennte und sich lohnen wuerde

**`brain-v3-app-sync-loop`** — ein Skill, der pro Phase folgende Schritte
automatisiert: (1) App-Hook-Stelle finden, (2) Hook-Code-Stub einsetzen,
(3) Live-Smoke-Anleitung an User generieren, (4) Log-Auswertung
durchfuehren, (5) Vault-Synthesis-Eintrag schreiben mit korrektem
Status-Marker. Kann gebaut werden, sobald F1–F3 geklaert sind und der
Plan-Edit-Patch steht. Ich baue ihn nicht jetzt, weil sein Innenleben
von den User-Entscheidungen abhaengt.

### 8.3 Wie ich es jetzt halte

Ich fuehre fuer diese Vorschlag-Erstellung **keinen Skill** aus, weil
der Vorschlag selbst ein Plan-Dokument ist und kein Code-Edit. Die
Skills oben werden bei der Implementation eingesetzt, nicht bei der
Plan-Restruktur.

---

## 9. Vault-Pflicht

Sobald der User auf F1–F5 antwortet und einen Patch freigibt, gehoert
folgender Vault-Eintrag dazu (gemaess AGENTS.md, „No vault entry =
task not completed"):

- `wiki/decisions/D-XXX-app-sync-restruktur.md` — Architektur-
  Entscheidung in-process vs. FastAPI, Lesart-A-Bestaetigung,
  Phasen-Status-Re-Markierung. ID = naechste freie.
- `wiki/synthesis/2026-05-05-plan-app-sync-proposal.md` — Verweis auf
  diese Datei, plus User-Entscheidungs-Protokoll, plus Patch-Hash.

Diese Vault-Eintraege werden **nicht** vom Agent gesetzt, bis User
freigibt.

---

## 10. Zusammenfassung in drei Saetzen

Der Plan ist intern konsistent mit sich selbst, aber inkonsistent mit
der Code-Realitaet — vor allem in der Annahme einer FastAPI-Schicht,
die im Repo nicht existiert, und in der spaeten Verdrahtung, die
genau der Punkt ist, an dem deine Aussage „App muss mitwachsen"
ansetzt. Der Vorschlag ist, jeder Phase ab sofort einen App-Sync-Block
mitzugeben, fuer Phase 1–3 nachzuholen, was bei „NICHT geliefert"
stehengeblieben ist, und in Phase 4 + 5 die FastAPI-Annahme durch
in-process-Aufrufe zu ersetzen. Welche dieser Punkte tatsaechlich so
in den Plan einfliessen, entscheidest du — ich liefere den
Plan-Edit-Patch erst nach deiner Antwort auf F1–F5.
