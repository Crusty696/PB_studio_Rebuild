# Phase 4 Blueprint — Pacing-Integration (Reranker + in-process BrainV3Service)

> **🔴 STATUS 2026-05-05: TODO — BUILD-FROM-SCRATCH-MODE**
>
> Vor Beginn prüfen:
> 1. `services/brain_v3/reranker.py`, `smart_sampler.py`,
>    `services/brain_v3/brain_v3_service.py` sollten **NICHT existieren**
>    (sonst → Verify-Mode statt Build).
> 2. Phase-3-Synthesis-Doc lesen für API-Subtilität (Skalen
>    Cold-Start-Default vs. Posterior-Mean):
>    `docs/superpowers/synthesis/2026-05-05-brain-v3-phase3-completion.md`
> 3. Vault-Spiegel `wiki/synthesis/brain-v3-phase3-completion-2026-05-05.md`
>    bestätigt Phase 3 = `code-fix-pending-live-verification` (112/112 Tests grün).
> 4. App-Eingriffspunkt ist **`services/pacing/pipeline.py`** Klasse
>    `PacingPipeline`, Methode **`select_best()`** (Zeile 145 Stand
>    2026-05-05) mit Signatur
>    `(self, candidates: Sequence[ClipFeatures], ctx: AudioContext,
>    predecessor: ClipFeatures | None = None,
>    recent_clip_ids: Sequence[int] | None = None) -> PipelineResult`.
>    Freigegeben durch User-Direktive 2026-05-05 (F5). Der ursprueglich
>    im Plan benannte `clip_selector.select_clip()` existiert nicht.
>
> **Architektur-Direktive (User 2026-05-05, F1):** PB Studio Rebuild ist
> reine PySide6-Desktop-App mit in-process Service-Aufrufen. **Phase 4
> baut keinen FastAPI-Server, keinen REST-Router, keinen HTTP-Endpoint.**
> Statt `routers/brain_v3_router.py` wird ein in-process
> `services/brain_v3/brain_v3_service.py` mit Klasse `BrainV3Service`
> als Fassaden-Wrapper geliefert. Die UI ruft `BrainV3Service`-Methoden
> direkt aus PySide6-Slots.

## 1. Ziel + Erfolgsdefinition

**Ziel:** Brain-V3-Reranker greift in die Pacing-Pipeline-Selektor-
Funktion ein. Der **in-process `BrainV3Service`-Fassaden-Wrapper** mit
5 Methoden (`suggest`, `feedback`, `learning_session`, `stats`, `reset`)
ist von der UI direkt aufrufbar. Pacing-Config hat `use_brain_v3` Flag.
Cut-Output enthält `brain_v3_scores` für UI.

**Erfolg = wahr wenn:** End-to-End in-process Smoke-Test (Sektion 7)
komplett grün auf User-Maschine. Pacing-Run mit `use_brain_v3=true`
liefert `brain_v3_scores` in jedem Cut. Klick erhöht Bucket-Confidence
nachweisbar via `BrainV3Service.stats()`.

**Aufwand-Schätzung:** 3–5 Tage.

---

## 2. Voraussetzungen

| Voraussetzung | Status erwartet |
|---|---|
| Phase 3 (Brain-Core) DONE | ✓ Vorbedingung |
| User-Freigabe für App-Eingriffspunkte (Pacing-Pipeline-Hook) | gegeben (User-Direktive 2026-05-04) |
| `services/pacing/pipeline.py` Klasse `PacingPipeline` Methode `select_best` existiert + ist erreichbar | bestaetigt 2026-05-05 (Zeile 145, Signatur dokumentiert in Banner) |
| Pacing-Config-Objekt ist erweiterbar | **OFFEN — Pre-Phase-4-Spike erforderlich** (siehe Sektion 2.1). Im Code-Repo wurde **kein** `PacingConfig`-Objekt im klassischen Sinne gefunden; `PacingPipeline.select_best()` Signatur (Zeile 145) hat keinen `config`-Parameter. Drei Eingriffspunkt-Optionen sind moeglich, eine muss gewaehlt werden bevor Phase-4-Code geschrieben wird. |

### 2.1 Pre-Phase-4-Spike: Pacing-Config-Eingriffspunkt (BLOCKER)

`use_brain_v3: bool` Flag muss irgendwo platziert werden, damit
`select_best()` weiss, ob es den Reranker aufrufen soll. Drei Optionen:

| # | Option | Pro | Contra |
|---|---|---|---|
| (a) | Konstruktor-Parameter auf `PacingPipeline.__init__` (z. B. `use_brain_v3: bool = False`, `brain_v3_min_confidence: float = 0.0`) | Minimal-invasiv, lokal eingegrenzt, keine neue Datei | Erfordert dass alle Pipeline-Instanziierungs-Stellen aktualisiert werden — Grep `PacingPipeline(` zeigt Konsumenten |
| (b) | Feld im durchgereichten `AudioContext`-Dataclass (existiert in `services.pacing.scorer`) | Pro-Cut konfigurierbar, durchgereicht durch Pipeline | Vermischt Audio-Daten mit App-Konfig — semantisch unsauber |
| (c) | Neues `PacingConfig`-Dataclass-Modul `services/pacing/config.py` mit allen pacing-globalen Settings | Sauberer Ort fuer wachsende Config | Groesserer Refactor, alle Pipeline-Konstruktor-Aufrufer anfassen |

**Empfehlung:** Option (a) — minimal invasiv, fertige Loesung, kann
spaeter zu (c) refactored werden falls weitere Settings dazukommen.

**Spike-Aufgabe (vor Phase-4-Code-Beginn, ~30 Min):**

1. `Grep "PacingPipeline("` ueber das Repo — alle
   Instanziierungs-Stellen auflisten
2. Pruefen wo Pacing-Settings aktuell herkommen (Profile-JSON?
   default_weights.json? Konstruktor-Args?)
3. Ergebnis als Mini-Synthesis in
   `docs/superpowers/synthesis/2026-05-XX-pacing-config-pre-phase4.md`
   ablegen
4. **Entscheidung (a/b/c) festschreiben** in einem D-XXX-Vault-
   Eintrag — User-Bestaetigung pflicht
5. Erst danach Phase-4-Code starten

---

## 3. Architektur

```text
services/brain_v3/
├── reranker.py               ←── BrainV3Reranker (Hook in Pacing-Pipeline)
├── smart_sampler.py          ←── SmartSampler (Top-15 nach Bayes-Varianz)
├── brain_v3_service.py       ←── BrainV3Service (in-process Fassaden-Wrapper)
└── storage/
    └── sql_migrations/
        └── state/001_initial.sql  ←── timelines, timeline_cuts, feedback_events

schemas/
└── brain_v3_schemas.py       ←── Pydantic Aufruf-/Rueckgabe-Dataclasses fuer
                                   die 5 BrainV3Service-Methoden (in-process,
                                   keine REST-Schemas)

services/pacing/pipeline.py   ←── HOOK: PacingPipeline.select_best()
                                   optional rerank wenn use_brain_v3=True
                                   (Zeile 145, festgelegt User-Direktive
                                    2026-05-05 F5)
<Pacing-Config-Objekt>        ←── +use_brain_v3 Field
                                   (Pfad im Code suchen — der urspruenglich
                                    benannte `backend/schemas/pacing_schemas.py`
                                    existiert nicht)
```

**Daten-Fluss bei Pacing-Run:**

```text
Pacing-Pipeline produziert Cut-Positionen + trigger_type
  │
  ▼
PacingPipeline.select_best(candidates, ctx, predecessor, recent_clip_ids):
  # Stages 1-3 laufen — UNVERAENDERT
  # Stage 4 (Soft Scoring) befuellt eine 'scored'-Liste:
  #   scored: list[tuple[ClipFeatures, float, dict[str, float]]]
  #         = [(c, soft_score, contribs), ...]
  #   ueber alle Kandidaten mit r.passed_stage2 == True
  # Code-Stelle: pipeline.py Zeile 264-274 (Stage-4-Loop), 285 (sort)

  if self.use_brain_v3 and len(scored) > 1:
    # Reranker erhaelt die scored-Liste (Stages 1-3 haben bereits
    # gefiltert: Hard-Rules + Variations-Budget + Collision-Check).
    # Brain V3 ueberstimmt das Stage-4-Soft-Scoring, NICHT die
    # vorherigen Filter.
    cut_context = build_cut_context(ctx, predecessor, recent_clip_ids)
    bv3_scored = BrainV3Reranker(scorer, weight_store).rerank(
        [c for c, _soft, _contribs in scored],   # nur die Clips
        cut_context,
    )
    best_clip = bv3_scored[0].candidate
    best_score = bv3_scored[0].final_score
    best_contribs = {**dict(scored[0][2]),       # Stage-4-contribs des
                                                  # Top-Picks behalten
                     "brain_v3_score": best_score}
    rationale["brain_v3"] = {
        "applied": True,
        "scores": bv3_scored[0].brain_v3_scores,
        "context_keys": context_keys(cut_context),
    }
  else:
    # Bisheriger Stage-4-Top-Pick — UNVERAENDERT
    scored.sort(key=lambda t: t[1], reverse=True)
    best_clip, best_score, best_contribs = scored[0]
    rationale["brain_v3"] = {"applied": False}
```

**Daten-Fluss bei Klick:**

```text
UI (PySide6-Slot) → BrainV3Service.feedback(cut_id, rating)
  │  (in-process Python-Methoden-Aufruf, kein HTTP)
  ▼
BrainV3Service liest cut_id aus state.db (timeline_cuts.brain_v3_scores_json)
  │
  ▼
ContextResolver baut 6 Backoff-Keys aus cut.context
  │
  ▼
FeedbackLogger.log_feedback(rating, keys) → 102 Bucket-UPSERTs
  │
  ▼
state.db: INSERT feedback_events (Audit-Trail)
  │
  ▼
Rueckgabe-Dataclass: FeedbackResponse(status="ok", n_buckets_updated=102)
```

---

## 4. Datei-für-Datei-Spezifikation

### 4.1 `services/brain_v3/storage/sql_migrations/state/001_initial.sql`

```sql
CREATE TABLE IF NOT EXISTS timelines (
    id            INTEGER PRIMARY KEY,
    name          TEXT,
    audio_clip_id INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    config_json   TEXT,
    is_current    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS timeline_cuts (
    id                   INTEGER PRIMARY KEY,
    timeline_id          INTEGER NOT NULL,
    position_idx         INTEGER NOT NULL,
    clip_id              TEXT NOT NULL,
    start_time           REAL NOT NULL,
    end_time             REAL NOT NULL,
    clip_start           REAL DEFAULT 0,
    trigger_type         TEXT,
    trigger_strength     REAL,
    segment_type         TEXT,
    brain_v3_scores_json TEXT,                      -- 17 Sub-Scores
    context_keys_json    TEXT,                      -- für Klick-Lookup
    metadata_json        TEXT,
    FOREIGN KEY (timeline_id) REFERENCES timelines(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id                INTEGER PRIMARY KEY,
    cut_id            INTEGER NOT NULL,
    rating            TEXT NOT NULL CHECK(rating IN ('perfect','fits','not_quite','no_match')),
    alpha_delta       REAL NOT NULL,
    beta_delta        REAL NOT NULL,
    context_keys_json TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    FOREIGN KEY (cut_id) REFERENCES timeline_cuts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_cuts_timeline ON timeline_cuts(timeline_id);
```

### 4.2 `services/brain_v3/reranker.py`

```python
from services.brain_v3.scorer import Scorer, ScoredCandidate
from services.brain_v3.bridge_dimensions import ClipCandidate
from services.brain_v3.context_resolver import CutContext

class BrainV3Reranker:
    def __init__(self, scorer: Scorer, min_confidence: float = 0.0):
        self.scorer = scorer
        self.min_confidence = min_confidence

    def rerank(
        self,
        candidates: list[ClipCandidate],
        cut_context: CutContext,
    ) -> list[ScoredCandidate]:
        """Returns: sortiert absteigend nach final_score.
        Filtert Kandidaten unter min_confidence raus."""
```

### 4.3 `services/brain_v3/smart_sampler.py`

```python
class SmartSampler:
    def __init__(self, weight_store: WeightStore): ...

    def select_uncertain_cuts(
        self,
        cuts: list[dict],   # mit context_keys_json + brain_v3_scores_json
        n: int = 15,
    ) -> list[dict]:
        """Top-N nach Gesamt-Bayes-Varianz absteigend.
        Variance pro Achse: α·β / ((α+β)² · (α+β+1))."""
```

### 4.4 `schemas/brain_v3_schemas.py`

In-process Aufruf-/Rueckgabe-Dataclasses (Pydantic, **keine** REST-Schemas
— nur Typsicherheit fuer den `BrainV3Service`-Aufruf):

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class BrainV3SuggestRequest(BaseModel):
    audio_clip_id: int
    video_clip_ids: list[int]
    n_top: int = 5

class BrainV3SuggestResponse(BaseModel):
    cuts: list[dict]   # mit brain_v3_scores

class BrainV3FeedbackRequest(BaseModel):
    cut_id: int
    rating: Literal["perfect", "fits", "not_quite", "no_match"]

class BrainV3FeedbackResponse(BaseModel):
    status: str
    n_buckets_updated: int

class BrainV3LearningSessionResponse(BaseModel):
    cuts: list[dict]   # genau 15 Cuts mit höchster Bayes-Varianz

class BrainV3StatsResponse(BaseModel):
    total_clicks: float
    confident_axes: int
    cold_start_axes: int
    top_positive_buckets: list[dict]
    top_negative_buckets: list[dict]

class BrainV3ResetTokenResponse(BaseModel):
    confirmation_token: str

class BrainV3ResetConfirmRequest(BaseModel):
    confirmation_token: str

class BrainV3ResetResponse(BaseModel):
    status: Literal["reset_complete"]
```

### 4.5 `services/brain_v3/brain_v3_service.py` (in-process Fassade)

5 Methoden in einer Klasse — **kein FastAPI, kein Router, kein HTTP**:

```python
from typing import Optional

class BrainV3Service:
    """In-process Fassaden-Wrapper fuer Brain V3.

    Wird von PySide6-Slots direkt aufgerufen. Alle Methoden sind
    synchron oder geben coroutine-aehnliche Objekte zurueck, je
    nach Bedarf. Kein Server, kein REST.
    """
    def __init__(self, weight_store=None, brain_store=None, scorer=None,
                 reranker=None, smart_sampler=None):
        ...

    def suggest(self, req: BrainV3SuggestRequest) -> BrainV3SuggestResponse:
        """Pacing-Run mit Brain V3, Top-N Cut-Vorschläge mit brain_v3_scores."""

    def feedback(self, req: BrainV3FeedbackRequest) -> BrainV3FeedbackResponse:
        """4-Klick-Event verarbeiten. Liest cut_id aus state.db,
        baut context_keys, ruft FeedbackLogger.log_feedback."""

    def learning_session(self) -> BrainV3LearningSessionResponse:
        """SmartSampler.select_uncertain_cuts(n=15)."""

    def stats(self) -> BrainV3StatsResponse:
        """WeightStore-Diagnostik."""

    def reset(self, req: Optional[BrainV3ResetConfirmRequest] = None
              ) -> BrainV3ResetTokenResponse | BrainV3ResetResponse:
        """Two-Step:
        1. Ohne Token → Token zurückgeben
        2. Mit Token → BrainStore.reset() ausführen"""
```

**Instanziierung & Konsumenten:**
- Singleton in `ui/brain_v3/brain_v3_tab.py` (Phase 5) ueber
  `_get_brain_v3_service()`-Helper.
- Pacing-Pipeline-Hook erhaelt die Instanz via Dependency-Injection
  (Konstruktor-Parameter), **nicht** via Modul-Import-Singleton.
- Tests instanziieren direkt mit Mock-Stores.

**Keine REST-Schicht:** falls spaeter ein REST-Wrapper nachgezogen
werden soll, wird er als optionale Phase 4.5 eigenstaendig geplant
und auf `BrainV3Service` aufgesetzt — ohne dass V3-Code-Pfade
veraendert werden muessen.

### 4.6 App-Eingriffspunkte (V1/V2-naher Code, freigegeben)

#### Pacing-Config (Pfad im Code suchen, **nicht** `backend/schemas/...`)

```python
# Konkrete Datei vor Edit per Grep verifizieren — der Plan hat
# "backend/schemas/pacing_schemas.py" benannt, aber dieser Pfad
# existiert nicht. Echtes Pacing-Config-Objekt ist im
# services/pacing/-Code zu finden (z. B. dataclass mit Pacing-
# Settings, das vom Pipeline-Konstruktor entgegengenommen wird).
class <PacingConfig>:
    # ... bestehende Felder ...
    use_brain_v3: bool = False
    brain_v3_min_confidence: float = 0.0
```

#### `services/pacing/pipeline.py` (Hook in `PacingPipeline.select_best`)

Konkrete Signatur (Zeile 145, festgelegt User-Direktive 2026-05-05 F5):

```python
def select_best(
    self,
    candidates: Sequence[ClipFeatures],
    ctx: AudioContext,
    predecessor: ClipFeatures | None = None,
    recent_clip_ids: Sequence[int] | None = None,
) -> PipelineResult:
    """Run all 4 stages and return (chosen, rationale).

    Hook (Brain V3, Phase 4): nach Stage 4, vor Auswahl von 'chosen',
    optionaler Reranker-Aufruf hinter use_brain_v3-Flag.
    """
    if not candidates:
        return PipelineResult(chosen=None, rationale={...})

    # ... bisherige Stages 1-4 — UNVERAENDERT ...

    # NEUER Pfad: Brain-V3-Reranker uebernimmt Stage-4-Sortierung.
    # 'scored' ist die in Stage 4 (pipeline.py Z. 264-274) befuellte
    # Liste: [(clip, soft_score, contribs), ...].
    # use_brain_v3 / brain_v3_min_confidence kommen aus dem in
    # Sektion 2.1 entschiedenen Pacing-Config-Eingriffspunkt
    # (Default-Empfehlung: Konstruktor-Parameter auf PacingPipeline).
    if self.use_brain_v3 and len(scored) > 1:
        from services.brain_v3.reranker import BrainV3Reranker
        from services.brain_v3.scorer import Scorer
        from services.brain_v3.bridge_dimensions import BridgeDimensions
        from services.brain_v3.weight_store import WeightStore
        from services.brain_v3 import paths

        weights = WeightStore(paths.weights_db_path())
        scorer = Scorer(BridgeDimensions(), weights)
        reranker = BrainV3Reranker(scorer, self.brain_v3_min_confidence)

        cut_context = build_cut_context(ctx, predecessor, recent_clip_ids)
        clips_only = [c for c, _soft, _contribs in scored]
        bv3_scored = reranker.rerank(clips_only, cut_context)
        best_clip = bv3_scored[0].candidate
        best_score = bv3_scored[0].final_score
        # Stage-4-Soft-Score-contribs des urspruenglich Top-Picks
        # behalten, plus brain_v3_score addieren — fuer Audit
        best_contribs = {
            **dict(scored[0][2]),
            "brain_v3_score": best_score,
        }
        rationale["brain_v3"] = {
            "applied": True,
            "scores": bv3_scored[0].brain_v3_scores,
            "context_keys": context_keys(cut_context),
        }
    else:
        # Bisheriger Pfad — UNVERAENDERT
        scored.sort(key=lambda t: t[1], reverse=True)
        best_clip, best_score, best_contribs = scored[0]
        rationale["brain_v3"] = {"applied": False}

    return PipelineResult(chosen=chosen, rationale=rationale)
```

**Wichtig:** der Reranker arbeitet auf Stage-4-**Soft-Scoring-Liste**
(`scored` in `pipeline.py` Z. 274 — alle Kandidaten mit
`r.passed_stage2 == True`), nicht auf rohen Kandidaten. Das ist der
minimal-invasive Eingriff: Brain V3 darf nicht Stage-1-Hard-Rejects
oder Stage-2-Budget-Rejects ueberstimmen.

### 4.7 Mapping-Tabelle: 6 Brain-V3-Kontext-Slots ↔ Pacing-State

> **Status 2026-05-05: RESOLVED via Konfiguration** (D-036 adopted).
> Mapping wird **nicht hardcoded**, sondern als Defaults in
> `services/brain_v3/context_mapping.py` mit optionalem YAML-Override
> via `config/brain_v3_context_mapping.yaml` implementiert. Die unten
> stehenden Default-Werte sind die Spike-Empfehlung 2026-05-05 — User
> kann ohne Code-Edit umkonfigurieren.

`build_cut_context(ctx, predecessor, recent_clip_ids, cfg)` baut die
6 Backoff-Kontext-Slots aus dem Pacing-State unter Verwendung einer
`ContextMappingConfig`-Instanz (`cfg`). Die 6 Ziel-Slots des Brain V3
sind in `services/brain_v3/context_resolver.py:36` `class CutContext`
definiert:

| Brain-V3-Slot | Quelle | Mapping/Quantisierung (Default) | Override-Schalter |
|---|---|---|---|
| `audio_section_type` | `ctx.at_section_type` (9 AudioContext-Werte) | `cfg.section_mapping[at_section_type]` — Defaults: `chorus→drop`, `bridge→transition`, `buildup→build`, `breakdown→break`, alle anderen 1:1 | `section_mapping` in YAML |
| `audio_subtrack_position` | `ctx.at_timestamp_sec` + Sub-Track-Boundaries (Phase-1 SubtrackDetector) | `quantize_subtrack_position()` — Helper existiert in `context_resolver.py:99` | n/a (algorithmisch fix) |
| `audio_energy_level` | `ctx.at_energy` (0..1) | `quantize_tertile(at_energy, *cfg.energy_tertile)` — Default Schwellwerte `(0.33, 0.66)` | `energy_tertile` in YAML |
| `audio_mood` | `ctx.at_mood_audio` (4 AudioContext-Werte) | `cfg.mood_mapping[at_mood_audio]` — Defaults: `energetic→uplifting`, `calm→neutral`, `dramatic→dark`, `ambient→neutral` | `mood_mapping` in YAML |
| `video_motion_class` | `predecessor.motion_score` (0..1, aus `ClipFeatures`) | 4-Klassen-Quantisierung mit `cfg.motion_quartile` — Default `(0.25, 0.50, 0.75)` | `motion_quartile` in YAML |
| `video_pace_class` | abhaengig von `cfg.pace_source` — Default `"recent_cuts"` (Cuts pro 10 s aus `recent_clip_ids`); alternative: `"cut_density"` oder `"bpm"` | `derive_pace_class()` in `context_mapping.py` — Default Schwellwerte `(2.0, 5.0)` cuts/10s | `pace_source` + `pace_recent_thresholds` in YAML |

**Pflicht in Phase 4 zu implementieren:**

- `services/brain_v3/context_mapping.py` mit `ContextMappingConfig`
  Dataclass + `DEFAULT_*` Konstanten + `from_yaml()` Loader +
  `map_section()` / `map_mood()` / `derive_pace_class()` pure-Functions
- Optional `config/brain_v3_context_mapping.yaml` (Beispiel-Datei mit
  Default-Werten und Kommentaren — wenn nicht vorhanden, gelten
  Defaults)
- 4-Klassen-Quantisierer `quantize_quartile()` ergaenzen in
  `services/brain_v3/context_resolver.py` (analog `quantize_tertile`)
- `build_cut_context(ctx, predecessor, recent_clip_ids, cfg)` Helper,
  der die 6 Slots zusammenbaut und eine `CutContext`-Instanz liefert
- Validation: `from_yaml()` prueft alle Keys gegen `VALID_SECTIONS`,
  `VALID_MOOD` etc. aus `context_resolver.py` — bei Konflikt
  `ValueError` beim Boot, kein silent-default

**Tests pflicht:**

- `test_map_section_default_values` (alle 9 AudioContext-Werte)
- `test_map_section_yaml_override` (kompletter Override)
- `test_map_mood_default_values` (alle 4)
- `test_map_mood_yaml_override`
- `test_derive_pace_class_recent_cuts` / `_cut_density` / `_bpm`
- `test_from_yaml_missing_file_uses_defaults`
- `test_from_yaml_invalid_section_value_raises`
- `test_build_cut_context_full_loop` (echte AudioContext → valide CutContext)

**Wichtig:** Hook muss minimal-invasiv sein. Wenn `use_brain_v3=False`,
darf KEINE Performance-Veränderung am bisherigen Pfad passieren.
Regression-Test gegen byte-identischen Pacing-Output ohne Flag ist
Pflicht.

---

## 5. SQL-Migrations

Pfad: `services/brain_v3/storage/sql_migrations/state/001_initial.sql`
Anwendung: in `BrainV3StateStore` (neuer Helper analog `BrainStore`),
geöffnet mit `paths.project_state_db_path(project_root)`.

---

## 6. App-Eingriffspunkte — Audit-Trail

| Datei | Was geändert | Risk |
|---|---|---|
| Pacing-Config-Objekt (Pfad vor Edit per Grep verifizieren) | +2 Felder (use_brain_v3, brain_v3_min_confidence) mit Defaults | niedrig (additiv) |
| `services/pacing/pipeline.py` `PacingPipeline.select_best()` (Zeile 145) | if-Branch ersetzt das `scored.sort(...)` (Z. 285) durch Reranker-Sortierung | mittel (Pacing-kritisch) |
| `services/brain_v3/brain_v3_service.py` (NEU) | +`BrainV3Service`-Klasse, in-process Fassade | niedrig (additiv) |
| Cut-Output-Schema | optional `brain_v3_scores`, `context_keys` Felder | niedrig |

**Default: KEINE Änderungen** an `services/brain_service.py` (V1) oder
`services/brain_v2/*` (V2). Refactor von V1/V2 ist freigegeben (User-
Direktive 2026-05-05, F2), aber Phase 4 selbst tastet V1/V2 nicht an —
ausser ein konkreter Refactor wird vor Phase-4-Beginn explizit
beauftragt mit Live-Verifikation der V1/V2-Funktion.

**Kein FastAPI-Server, kein REST-Router, kein `localhost:8765`** —
gestrichen per User-Direktive 2026-05-05 (F1). Alle UI-↔-Brain-Aufrufe
laufen in-process ueber `BrainV3Service`.

---

## 7. Test-Spezifikation

### Unit-Tests `tests/test_services/test_brain_v3_reranker_smart_sampler.py`

- `test_reranker_sorts_by_final_score`
- `test_reranker_filters_below_min_confidence`
- `test_smart_sampler_returns_exactly_15`
- `test_smart_sampler_picks_high_variance` (Mock-Daten mit bekannter Varianz)
- `test_smart_sampler_handles_empty_input` → leere Liste

### Unit-Tests `tests/test_services/test_brain_v3_state_store.py`

- `test_state_db_migration_runs`
- `test_timeline_cuts_round_trip` (insert + select brain_v3_scores_json)
- `test_feedback_events_constraint_rating` (CHECK greift)
- `test_cascade_delete_timeline_drops_cuts`

### Service-Tests `tests/test_services/test_brain_v3_service.py` (in-process, kein TestClient)

- `test_suggest_returns_cuts_with_brain_v3_scores`
- `test_feedback_increments_bucket_confidence`
- `test_feedback_invalid_rating_raises_validation_error` (Pydantic-Validation)
- `test_learning_session_returns_15_cuts`
- `test_stats_after_clicks_shows_total_clicks_growing`
- `test_reset_two_step_flow` (1. ruft Token ab, 2. confirmiert mit Token, 3. status=reset_complete)
- `test_reset_with_invalid_token_rejected`

### Integration-Test (in-process Vollschleife)

```python
def test_full_brain_v3_loop(sample_project):
    from services.brain_v3.brain_v3_service import BrainV3Service
    from services.brain_v3 import schemas

    svc = BrainV3Service()  # mit echten Stores aus sample_project

    # 1. Pacing mit Brain V3 (direkt durch Pipeline mit use_brain_v3=True)
    suggest_req = schemas.BrainV3SuggestRequest(
        audio_clip_id=1, video_clip_ids=[1,2,3], n_top=5,
    )
    r1 = svc.suggest(suggest_req)
    cut_id = r1.cuts[0]["id"]
    assert "brain_v3_scores" in r1.cuts[0]["metadata"]

    # 2. Klick
    r2 = svc.feedback(schemas.BrainV3FeedbackRequest(
        cut_id=cut_id, rating="perfect",
    ))
    assert r2.n_buckets_updated == 102

    # 3. Stats wachsen
    r3 = svc.stats()
    assert r3.total_clicks > 0
```

### Manueller in-process Smoke (statt cURL)

```python
# scripts/spike_brain_v3_pacing_smoke.py
from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3 import schemas

svc = BrainV3Service()

# 1. Suggest
suggest_req = schemas.BrainV3SuggestRequest(
    audio_clip_id=1, video_clip_ids=[1, 2, 3], n_top=5,
)
print(svc.suggest(suggest_req).model_dump_json(indent=2))

# 2. Feedback
print(svc.feedback(
    schemas.BrainV3FeedbackRequest(cut_id=42, rating="perfect")
).model_dump_json(indent=2))

# 3. Stats
print(svc.stats().model_dump_json(indent=2))

# 4. Learning Session
print(len(svc.learning_session().cuts))
```

---

## 8. Definition of Done

```text
☐ state.db Schema-Migration läuft idempotent
☐ Reranker greift in PacingPipeline.select_best() ein wenn use_brain_v3=true
☐ Wenn use_brain_v3=false → bisheriger Pfad UNVERÄNDERT (Regression-Test)
☐ 5 BrainV3Service-Methoden aufrufbar in-process (suggest, feedback,
  learning_session, stats, reset) mit korrekten Pydantic-Typen
☐ BrainV3Service.feedback() erhöht Bucket-Confidence (verifiziert via Folge-stats())
☐ BrainV3Service.learning_session() liefert genau 15 Cuts in <2 s
☐ Pacing-Overhead mit Brain V3 <800 ms (Plan-DoD)
☐ Cut-Output enthält brain_v3_scores für UI-Konsumenten (Phase 5)
☐ V1/V2 unverändert lauffähig (Regression-Smoke)
☐ ~25+ Tests grün auf GTX 1060
☐ Synthesis-Doc unter docs/superpowers/synthesis/
```

---

## 9. Risiken + Mitigationen

| Risiko | Mitigation |
|---|---|
| Hook in clip_selector bricht V1-Pacing | use_brain_v3=false default, Regression-Test mit altem Pfad |
| Cut-Context-Bau aus Pacing-State unvollständig (was sind die echten Slots?) | Phase-4-Spike: laufender Pacing-Test, beobachten welche Felder im PacingState vorhanden sind, mappen auf 6 Slots |
| Pacing-Overhead >800 ms wegen 17×6 SELECTs pro Cut | WeightStore-Connection cachen pro Pacing-Run (nicht pro Cut neu öffnen) |
| brain_v3_scores_json wird zu groß in state.db | Bei 17 Achsen × float = ~200 Byte JSON pro Cut. Bei 1000 Cuts = 200 KB. Akzeptabel. |
| Reset während Pacing-Run läuft → inkonsistente Reads | WAL-Mode + Isolation-Level handhaben das |

---

## 10. Verifikations-Strategie

- **Unit-Tests:** ~25 in 3 Test-Files (reranker_smart_sampler, state_store, brain_v3_service)
- **Integration-Test:** vollständiger in-process Loop ueber `BrainV3Service`
- **Manueller Smoke:** wirklicher Pacing-Run auf User-Maschine, Stats verfolgen
- **Regression:** bisheriger Pacing-Run (use_brain_v3=false) muss unveränderten Output liefern
- **Performance-Spike:** `scripts/spike_brain_v3_pacing_latency.py` — misst Pacing-Latenz mit/ohne Brain V3 bei 100 Cuts

---

## 11. Reihenfolge der Implementation

```text
1. state-Migration + StateStore-Helper + Test (30 Min)
2. brain_v3_schemas.py (Pydantic-Models, in-process Aufruf-Typen) (15 Min)
0. **Pre-Phase-4-Spike (BLOCKER)**: Pacing-Config-Eingriffspunkt
   waehlen (Sektion 2.1 Optionen a/b/c) + 6 Kontext-Slots-Mapping
   fixieren (Sektion 4.7 Tabelle) — User-Bestaetigung pflicht (~1.5 h)
3. reranker.py + Test (30 Min)
4. smart_sampler.py + Test (30 Min)
5. brain_v3_service.py + Service-Tests (1.5 h) — fünf Methoden
6. Pacing-Config gemaess Spike-Beschluss (a/b/c) erweitern +
   Default-Test (15 Min)
7. pipeline.py `select_best()` Hook (Zeile 145) + Regression-Test
   (1 h) — Reranker uebernimmt Stage-4-Sortierung (auf `scored`-Liste,
   nicht auf rohen Kandidaten)
8. (entfaellt — kein Router zu registrieren, keine FastAPI-App)
9. Integration-Test (in-process full loop) (45 Min)
10. Manueller in-process Smoke + Pacing-Latenz-Spike (1 h)
11. Synthesis-Doc

Total: ~6-7 Stunden + Verifikation.
```

---

## Hinweis für Claude Code

**KRITISCH:** Phase 4 berührt App-Code (`services/pacing/pipeline.py`
und das Pacing-Config-Objekt). Vor jedem Edit:
1. Datei vollständig lesen
2. `PacingPipeline.select_best()` Signatur erneut verifizieren
   (sollte unveraendert sein gegenueber 2026-05-05 Stand: Zeile 145)
3. Edit minimal-invasiv (Reranker-Branch nach Stage 4, bestehende
   Stages 1-4 NICHT umbauen)
4. Regression-Test: bisheriger Pacing-Run mit `use_brain_v3=False`
   muss byte-identisch funktionieren

**V1/V2 wird in Phase 4 nicht modifiziert.** Default: `services/brain_service.py`
und `services/brain_v2/` bleiben in Phase 4 unangetastet. Refactor ist
freigegeben (User-Direktive 2026-05-05, F2), gehoert aber in eine
separate, klar deklarierte Refactor-Phase mit Live-Verifikation der
V1/V2-Funktion — nicht in Phase 4 nebenbei.

**Kein FastAPI, kein REST.** Phase 4 baut **keinen** Server, **keinen**
Router, **keinen** HTTP-Endpoint. Wenn der Code-Vorschlag eines Agenten
einen Router-Aufruf, ein `from fastapi import ...` oder einen `cURL`-
Test enthaelt, ist das Plan-Verstoss — sofort stoppen, korrigieren.
