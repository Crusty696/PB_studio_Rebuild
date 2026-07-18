# Bucket-2-Entscheidungsvorlage (2026-07-19)

Zweck: Die 6 offenen USER-Entscheidungen aus dem Master-Plan
(`2026-07-16-master-offene-tasks-konsolidierung.md`, Bucket 2) entscheidbar
machen. Pro Punkt: Frage, Optionen, Fakten, Empfehlung. **Entscheiden tut nur
der User.** Kein Code entsteht vor dem jeweiligen Entscheid.

Recherche-Basis: Consulting-Review-Fixplan (2026-06-12), Konsolidierungs-Plan
(2026-07-12, K6), Aufraeum-Refactor-Plan (2026-07-08), Vault-Decisions
(D-030/D-040/D-064/D-072), Bug-File B-634.

---

## E1 — Brain v1/v2/v3-Deprecation (One-way door)

**Frage:** Brain v1/v2 zugunsten v3 deprecaten/loeschen?

**Fakten:**
- Toter v1/v2-Code laut Aufraeum-Audit ~1.130 Zeilen (`subtrack_detector.py`,
  `embedding_repository.py`, `onnx_export.py`, `visual_curves.py`,
  `schemas/audio.py`+`video.py`). `brain_v3_schemas.py` ist LIVE — tabu.
- `services/brain/legacy_sqlite.py` (1952 Z.): Usage-Check ausstehend;
  falls tot → groesster Einzel-Gewinn.
- Embedding-Raum-Ziel (768 vs. 1152 Dim) haengt mit dran.
- Wiederherstellbar via Git-Historie (wie video_pipeline-Loeschung 2026-07-17).

**Optionen:**
- **A (empfohlen als naechster Schritt):** Agent macht read-only Usage-Check
  (was nutzt v1/v2 exklusiv? legacy_sqlite tot?) → danach informierter
  Loesch-Entscheid. Kein Code-Delete vorher.
- **B:** Sofort-Deprecation der 6 als tot auditierten Dateien (ohne
  legacy_sqlite), Rest spaeter.
- **C:** Alles behalten, Punkt parken.

## E2 — Vault-Sync-Strategie (D-064, ausgearbeitet)

**Frage:** Wie wird der Vault offsite gesichert?

**Fakten:** Vault ist lokales Git-Repo (main), ~109 MB, kein Remote =
kein Offsite-Backup. Muss privat bleiben (Pfade/interne Notizen).

**Optionen (aus D-064):**
- **1 (empfohlen, dokumentiert):** privates GitHub-Repo + Obsidian-Git
  Auto-Push. Schritte stehen fertig in D-064. Einziger User-Part:
  privates Repo anlegen + PAT/Login.
- **2:** Obsidian Sync (Bezahldienst). **3:** OneDrive/Dropbox (riskant,
  .git-Konflikte). **4:** Submodule im Code-Repo (nicht empfohlen).

## E3 — torch-2.x/cu121-Migration + requirements-Dedup

**Frage:** Jetzt migrieren oder aufschieben? requirements.txt archivieren?

**Fakten:**
- D-030: Probe-Env torch 2.2.2+cu121 lief gruen; Aufwand 0,5-1 Tag;
  Empfehlung dort: **separater Sprint, NICHT jetzt** (cu113 laeuft stabil).
- GPU-Hartregel D-040 bleibt unberuehrt (GTX 1060 only, Treiber 546.33 gepinnt).
- Ollama-Ceiling (0.21.2=GPU) haengt am Treiber-Pin — unabhaengig von torch.
- requirements.txt traegt bereits Kopfkommentar "NICHT INSTALLIEREN";
  kanonisch ist `requirements-py310-cu113.txt`.

**Optionen:**
- **A (empfohlen):** Migration aufschieben (bestaetigt D-030); requirements.txt
  nach `docs/archive/` verschieben + Setup-Doku-Verweise anpassen.
- **B:** Migration jetzt als eigener Sprint.
- **C:** Alles lassen wie ist.

## E4 — K6-B: foreign_keys=ON im Auto-Edit-Pfad (STOP+ASK-Gate)

**Frage:** FK-Enforcement im Auto-Edit-Pfad aktivieren?

**Fakten:** K6-A (gemeinsame Engine-Fabrik, busy_timeout — verhaltensneutral)
ist code-complete. Teil B aendert Verhalten: `foreign_keys=ON` kann bislang
stille FK-Verletzungen zu harten Fehlern machen. Verify-Vorgabe existiert:
Auto-Edit auf test33-Kopie, Timeline-Rows-Paritaet, Lock-Test parallel.

**Optionen:**
- **A:** Aktivieren mit dem definierten Verify (Paritaets-Test vor Merge).
- **B (konservativ):** Aus lassen, Punkt schliessen.
- Keine dokumentierte Empfehlung — echte 50/50-Abwaegung Integritaet vs. Risiko.

## E5 — 8 Aufraeum-Entscheide (einzeln ankreuzbar)

| # | Punkt | Fakten | Empfehlung |
|---|---|---|---|
| 5.1 | dist/ loeschen (~11 GB) | v0.5.0-Build vom 2026-07-18 liegt drin; User-Regel: keine Installer-Builds bis fertig | **Behalten** bis Install-Test-Phase; danach neu entscheiden |
| 5.2 | IDE-Configs (.clinerules/.cursor/.opencode/.windsurf) loeschen | eingefroren seit 2026-05-26, Risiko null | **Loeschen** |
| 5.3 | DEAD-009 storage_provenance | OTK-021 hat live-evidence-pass → nicht tot | **Behalten**, DEAD-009 schliessen |
| 5.4 | mood/energy-Formel vereinheitlichen | 3-4 konkurrierende Formeln, aendert Schnitt-Ergebnisse; ueberlappt NEUBAU-Pacing | **Parken** bis NEUBAUTEN-Gate (dort sowieso beruehrt) |
| 5.5 | Migrationssysteme → nur Alembic | Legacy-Migrations FROZEN, Risiko hoch (Live-DBs) | **Parken** (kein Leidensdruck) |
| 5.6 | requirements.txt deprecaten | = E3-A requirements-Teil | mit **E3** entscheiden |
| 5.7 | Doku-Konsolidierung (App-Beschreibung doppelt, graph_system-Docs) | reine Doku, risikofrei | **Ja**, Agent-frei ausfuehrbar nach OK |
| 5.8 | legacy_sqlite.py (1952 Z.) | Usage-Check ausstehend | mit **E1-A** entscheiden |

## E6 — B-634 Cyan-Marker wieder aufnehmen?

**Fakten:** Hauptnutzen (Anker-Liste aus DB) LIVE erfuellt; Auto-Edit nutzt
Anker (B-619). Cyan-Marker = Eye-Candy, rendert isoliert (604 px bewiesen),
aber 0 px im vollen load_from_db-Kontext. Vom User 2026-07-14 geparkt.

**Optionen:**
- **A (empfohlen):** geparkt lassen (Status quo bestaetigen).
- **B:** Wiederaufnahme — dann headless-Repro MIT echtem load_from_db (test33)
  statt weiterer GUI-Zyklen.

---

## Minimal-Antwortformat fuer den User

`E1: A|B|C · E2: 1|2|3|4 · E3: A|B|C · E4: A|B · E5: 5.1-5.8 je ja/nein/parken · E6: A|B`

Jede Antwort wird als D-0xx-Decision-File im Vault festgehalten, erst danach
entsteht Code.
