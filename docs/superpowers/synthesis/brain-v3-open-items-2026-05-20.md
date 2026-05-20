# Brain V3 Open Items 2026-05-20

Status: `audited-read-only`

## Dirty-Tree Befund

Diese Dateien waren im Working Tree als geaendert markiert:

- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/02_DECISIONS.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/03_TECH_STACK.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/05_BRIDGE_AXES.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/07_RISKS.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/08_VERIFICATION.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/09_REVERIFICATION_2026-05-04.md`
- `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/phase_blueprints/phase_6_haertung.md`

`git diff`, `git diff --ignore-cr-at-eol`, `git diff --ignore-space-at-eol`, `git diff --numstat` und `git diff --summary` zeigten keinen Inhaltsdiff. Git meldete nur LF/CRLF-Warnungen. Bewertung: kein belegbarer neuer Planinhalt in diesen Dirty-Dateien.

## Offene Punkte aus dem bestehenden Brain-V3-Plan

### 1. Phase 1-3 App-Sync fehlt

Quelle: `README.md` Status-Tabelle und `PROPOSAL_APP_SYNC_2026-05-05.md`.

Fakten:
- Phase 1 ist code-complete, aber App-Sync pending.
- Phase 2 ist code-complete, aber App-Sync pending.
- Phase 3 ist code-complete, aber App-Sync pending.
- Beim echten App-Import wird Brain V3 nicht sicher aufgerufen.

Konkrete offene Arbeit:
- Mix-Import-Hook fuer Brain-V3-Hashing/Schema-Anlage.
- Embedding-on-Import Hook.
- Brain-Store-Health-Check beim App-Boot.
- Live-Smoke mit echtem App-Workflow und Log-Auswertung.

Status: offen, vor Phase 4.

### 2. Phase 4 nicht starten vor Pre-Phase-4-Spike

Quelle: `phase_blueprints/phase_4_pacing_integration.md`.

Blocker:
- `PacingPipeline.select_best()` existiert, aber kein klassisches `PacingConfig`-Objekt.
- Entscheidung noetig, wo `use_brain_v3` und Brain-V3-Reranker-Konfiguration sitzen.

Plan nennt drei Optionen:
- Konstruktor-Parameter auf `PacingPipeline.__init__`.
- Feld im `AudioContext`.
- Neues `services/pacing/config.py`.

Empfehlung im Plan: Konstruktor-Parameter als minimaler erster Schritt.

Status: offen, Decision noetig.

### 3. NVENC + Brain parallel bleibt offen

Quelle: `10_OPEN_POINTS_VALIDATION.md`.

Fakten:
- NVENC-Hardware ist vorhanden.
- Alter Test hatte Skript-Bug.
- Kein gueltiger Parallel-Test Brain-Inferenz + NVENC ist belegt.

Status: offen, Phase 6.

### 4. Echter DJ-Mix mit Real-Annotation bleibt offen

Quelle: `10_OPEN_POINTS_VALIDATION.md`.

Fakten:
- Synth-Mix F1=0.75 validiert.
- Echter DJ-Mix mit Real-Annotation ist nicht erledigt.

Status: offen, Validierungs-/Haertungsarbeit.

### 5. HNSW <50 ms ist nicht offen, sondern ersetzt

Quelle: `10_OPEN_POINTS_VALIDATION.md`.

Fakten:
- sqlite-vec 0.1.9 hat kein HNSW.
- <50 ms HNSW-DoD ist nicht realistisch mit diesem Stack.
- Workaround: SQL-Pre-Filter und relaxter DoD.

Status: nicht als offene Arbeit aufnehmen; als Architekturentscheidung/DoD-Korrektur behandeln.

## Reihenfolge fuer spaetere Brain-V3-Arbeit

1. Phase 1-3 App-Sync nachholen.
2. Live-Smoke fuer echte App-Pfade.
3. Pre-Phase-4-Spike PacingConfig/`use_brain_v3`.
4. Decision fuer Phase-4-Eingriffspunkt.
5. Erst dann Phase 4 Pacing-Integration.
6. Phase 5 UI.
7. Phase 6: NVENC-Paralleltest, echter DJ-Mix, Backup/Recovery/Lizenzen.

## Governance

Brain V3 wird nicht aktiver Plan, solange `ACTIVE_PLAN.md` Audio-V2-Reconcile auswaehlt. Diese Datei nimmt nur die offenen Brain-V3-Punkte auf, damit sie nicht durch die Audio-V2-Arbeit verloren gehen.
