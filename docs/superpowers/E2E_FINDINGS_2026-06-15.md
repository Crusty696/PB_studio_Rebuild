# E2E Live-Abnahme — Funde 2026-06-15

Aufgetreten beim headless Service-E2E-Lauf (Import → Analyse → Auto-Edit → Export)
auf GTX 1060 / conda-env `pb-studio` (Python 3.10). Vollergebnis:
`test-report/e2e-live-acceptance-20260615/RESULT.md`.

## Fund 1 — Pacing-Strategist: Fence-Parse-Crash falsch als Ollama-Ausfall gelabelt
**Status: FIXED** (Commit `dd90d87`).
`_parse_response` nutzte `raw.index("```", start)`; bei offenem (truncatem) Code-Fence
warf `.index` `ValueError: substring not found` vor dem Brace-Fallback. `generate_pacing_plan`
labelte das als `ollama_unavailable`, obwohl Ollama erreichbar war.
Fix: `.find` + Guard (Fallback greift); Verbindungs- vs. Parse-Fehler getrennt
(`unparseable_response`). 3 Tests grün. **Offen: Vault-Bug-ID vergeben.**

## Fund 2 — Diag-E2E-Skripte: kaputte Repo-Root-Auflösung nach CRF-020-Move
**Status: FIXED** (Commit `2fb7f4d`).
`scripts/diag/{e2e_functional_test,e2e_audio_pipeline_orchestrator,e2e_direct_export,e2e_render_test}.py`
lösten ihren Root via `parent.parent` / `__file__.parent` auf → nach dem Move nach
`scripts/diag/` falsch (`scripts/` statt Repo-Root) → `ModuleNotFoundError`.
Fix: `Path(__file__).resolve().parents[2]`. Verifiziert (Import ohne `PYTHONPATH`).

## Fund 3 — OTK-008 Datensatz: Such-String-Mismatch (kein echtes Daten-Problem)
**Status: DOKUMENTIERT** (kein Code-Fix; User-Entscheidung).
OTK-008 (SCHNITT-Redesign Phase-12) gilt als `blocked-formal-dataset-missing`, weil
`Crusty Progressive Psy Set2.mp3` "nicht gefunden" wurde. Tatsächlich existiert die Datei —
mit **Unterstrich** statt Leerzeichen:

- `C:\Users\David Lochmann\Music\Crusty_Progressive Psy Set2.mp3` (142,9 MB)
- `C:\Users\David Lochmann\Music\Audio\Psy-Set\Crusty_Progressive Psy Set2.mp3` (142,9 MB, Duplikat)

Video `Solo_Natur`: erwartet wurden 103 MP4, vorhanden sind **124** in
`Solo_Natur\` und **100** in `Solo_Natur\converted\` (224 gesamt rekursiv).

**Implikation:** Die Audio-Blockade von OTK-008 ist nur ein Such-String-Fehler — die Datei ist da.
Mögliche User-Aktionen: (a) Plan/Checkliste auf den realen Dateinamen (Unterstrich) korrigieren,
(b) Clip-Soll 103 ↔ 124/100 klären, dann OTK-008 Phase-12 GUI-Abnahme erneut ansetzen.

## Noch offen (keine App-Code-Tasks)
- **DG-001** (Deferred Gate): voller 4h-Modell-Pipeline-Lauf und
  Mensch/QMediaPlayer-Playback-Abnahme bleiben Pflicht vor `release/fixed`.
- **Bereits nachtraeglich live erledigt:** H3 echte gleichzeitige Demucs+Video-Analyse,
  H2.1 NVENC-Export, SCHNITT-GUI-Widget-Abnahme, und H1 62-Min-Scale-Lauf
  (`outputs/h1_scale.log`, `H1_EXIT 0`, `failed=False`).
