# Freeze/Crash-Sanierung — Konsolidierter Fixplan 2026-07-14

> **⛔ SUPERSEDED 2026-07-16 — PLAN GESCHLOSSEN.** Alle offenen Tasks wurden in
> `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16` konsolidiert (Decision D-071, Registry-Status
> `superseded`). War nie ein aktiver Registry-Plan. Der Task-Text bleibt nur als Historie.
> Tier-P-Alt-Bug-Triage ist grossteils 2026-07-16 bereits gefixt. Aktuelle offene Arbeit:
> `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

plan_id: PB-STUDIO-FREEZE-CRASH-SANIERUNG-KONSOLIDIERT-2026-07-14
status: proposed-needs-user-activation
owner: (agent-proposed, user aktiviert)
created: 2026-07-14
authorized_by_user: 2026-07-14 chat ("mach den fixplan für B-625 und verbinde ihn mit den anderen noch offenen aufgaben ... füge sie alle zu einem zusammen")
scope_type: freeze-crash-remediation + offene-task-konsolidierung
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-freeze-crash-sanierung-2026-07-14.md

## Zweck

Ein Plan, der **alle offenen Freeze/Crash/Broken-Punkte** buendelt:
- Neu-Funde vom Ultracode-Discovery-Sweep 2026-07-14 (B-625/626/627).
- Bereits offene Freeze-Bugs aus dem PERF-DB-CLEANUP-Umfeld (B-622/623/624, B-618-Rest).
- Die gemeinsame Wurzel B-090 (`lazy='joined'` global).
- Verknuepfung zu den offenen Plan-Level-Punkten + User-Entscheidungen + Release-Nachzug.

Kein `fixed` durch Agent. Keine Code-Aenderung durch diese Planung.

## Governance-Einordnung

- Aktiver Plan bleibt formal `PB-STUDIO-PERF-DB-CLEANUP-2026-07-12` bis User umschaltet.
- Dieser Fixplan ist **inhaltlich die Fortsetzung** des Perf-Plans (dieselbe Blob-Load-Freeze-Klasse) + zieht die neuen Funde hinzu.
- Plan-Level-`fixed`-Marker (Tier M) sind **User-only**, kein Code — nur Sichtung.
- **TEST-REGEL (User 2026-07-14, global):** Tests NICHT einzeln pro Task. Erst F1–F7 sammeln → **ein** gebuendelter Testlauf (Tier V). Vault-Logging bleibt pro Sub-Schritt.

---

## TIER F — Code-Sanierung Freeze/Crash (Agent-machbar)

Gemeinsames Muster: synchrones `session.get()`/`.query()` laedt via
`lazy='joined'`/`selectin` grosse JSON-Blob-Spalten auf GUI/Main-Thread.
Fix-Strategie durchgaengig wie B-620: **column-select statt Voll-ORM-Load**
(nur benoetigte Skalarfelder laden, Blob-Spalten nicht anfassen).

| Task | Bug | Datei:Zeile | Fix-Ansatz | Prio | Abhaengig von |
|---|---|---|---|---|---|
| F1 | **B-625** | `edit_workspace.py:67/34/598`, `audio_analysis.py:50/636`, `stems.py:203`, `ab_compare_dialog.py:96`, `undo_commands.py:288` | column-select je Callsite (nur duration/file_path/title/bpm/stem-pfade); Blobs nie laden | hoch | F0 empfohlen |
| F2 | B-622 | `edit_workspace.py:598 _build_otio_timeline` | session.get vom GUI-Thread nehmen; column-select + ggf. verspaeteten Finish-Handler entkoppeln | hoch | teil von F1 |
| F3 | B-623 | `storage_migration.py:81 migrate_existing_outputs` | `.all()`-Query ohne Blob-Decode; column-select oder Migration off-thread | mittel | — |
| F4 | B-624 | `pacing_beat_grid.py:891 compute_stem_snr`, `:314 _get_bpm_cached` | column-select statt Blob-Lazy-Load | mittel | — |
| F5 | B-627 | `embedding_scheduler.py:174/255` | Callsite-Thread pruefen; 5s-Block off-GUI-thread oder async | niedrig | Callsite-Analyse |
| F6 | B-618-Rest | `style_bucket_clusterer.py:70-81` | Frozen-Build-Warmup-Pfad: Numba-Cache in Installer vorwarmen ODER warmup auch im frozen build ermoeglichen | mittel | Release-Build (Tier R) |
| F0 | **B-090** (Wurzel) | `database/models.py:195-196` (`waveform_data`/`beatgrid` = `lazy='joined'`), `:234` (`scenes` = `selectin`) | **Kern-Entscheidung:** Meta-Fix (lazy→`select`/`raise` global) ODER pro-Callsite column-select. Meta-Fix loest F1–F4 auf einen Schlag, ist aber breit (alle Callsites betroffen). | Entscheidung | — |

**F0 ist die zentrale Architektur-Entscheidung:** global `lazy` umstellen
(1 Change, aber breite Wirkung, Regression-Risiko auf ALLE ORM-Loads) vs.
pro-Callsite column-select (viele kleine Changes, lokal sicher). → **User-Entscheid** vor F1.

---

## TIER D — User-Entscheidungen (blockieren zugehoerige Code-Tasks)

| Task | Bug | Entscheidung | Optionen |
|---|---|---|---|
| D1 | **B-619** | Anchor-Sync No-Op beheben | (1) sync_anchors paarweise umbauen / (2) AudioVideoAnchor-Schema + eigener Sync-Pfad / (3) UI entwirren |
| D2 | **F0/B-090** | Blob-Load-Fix-Strategie | (a) Meta-Fix global lazy / (b) pro-Callsite column-select |
| D3 | **B-626** | Alembic-Fehler geschluckt (`migrations.py:838`) | (a) gewolltes Graceful-Degrade = wontfix / (b) Bug → hart abbrechen bei Migration-Fail |

---

## TIER V — Verifikation (GEBUENDELT, nach Tier F)

Nach neuer Test-Regel **ein** Durchlauf, nicht pro Task:
- V1: gezielter pytest-Batch fuer alle geaenderten Module (Perf/DB/UI-Controller).
- V2: **ein** GUI-Live-Retest (pb-gui-tester) der alle Freeze-Pfade in Folge durchklickt: Combo-Wechsel, A/B-Compare, Auto-Ducking, Undo, Projekt-Switch, Auto-Edit, Storage-Migration-Load.
- V3: freeze_stacks.log-Auswertung + Freeze-Dauer-Messung (vorher/nachher).
- `fixed` setzt danach der User.

---

## TIER R — Release-Nachzug (nach Fixes)

| Task | Was |
|---|---|
| R1 | Frozen neu bauen mit B-618/B-620/B-625-Fixes (`PB_SKIP_PYINSTALLER=0`) — **aktuelle signierte Artefakte + Clean-VM-Proof sind Stand `4a61dc2`, VOR den Fixes** |
| R2 | Neu signieren (signtool + Timestamp) |
| R3 | Clean-VM-Proof neu (Windows Sandbox) |
| R4 | Gate-Loch schliessen: Release-Gate Hash-Bindung an aktuelle Artefakte statt nur Proof-Existenz (User-Entscheid ob jetzt) |

---

## TIER M — Plan-Level `fixed`-Marker (User-Sichtung, kein Code)

| Plan / Task | Zustand | offen |
|---|---|---|
| PERF-DB-CLEANUP (aktiv) | E1–E10 committed+backend-verifiziert | GUI-Livepfade + D-069 Package-Test + User-`fixed` |
| KONSOLIDIERUNG-2026-07-12 | code-complete | 4 K8-Live-Flows sichten + `fixed` |
| TIMELINE-VIRTUALISIERUNG (D-066) | M0–M4 + Harness-PASS | virt-M4-Live-Sichtung + `fixed` (Plan, B-613, B-614) |
| AUDIT-FIXPLAN 2026-07-07 | code-complete | `fixed` nach Sichtung |
| NEUBAUTEN-VOLLINTEGRATION | code-complete | VLM-Backend Stub (`app_integration.py:121`), DEAD-008-Rest, UI-Perf; `fixed` |
| OTK-021 (Storage-Provenance) | live-evidence-pass | `fixed`-Marker offen |
| OTK-008 | blocked | Dataset fehlt (Solo_Natur 124 statt 103 MP4, Crusty-MP3 nicht gefunden) |
| OTK-019 | deferred | 4h-Heavy-Pipeline-Live-Gate |

---

## TIER P — Geparkte/aeltere Bugs (Triage-Durchlauf noetig)

Bug-Files mit `status: open`, teils veraltete Marker — **kurzer Triage** (echt-offen vs. schon abgehandelt) noetig:
- Broken/unwired: B-617 (Sections nie verdrahtet), Brain-V3 `suggest()`/`learning_session()` = Stub (`brain_v3_service.py:14`).
- Audio: B-595/B-538/B-235 (Onset-Long-Audio 1800s-Limit), B-603 (Crossfade-Export, deferred).
- Infra/Boot: B-604 (llama-Vulkan-Crash), B-601 (Ollama-redist), B-600 (system-check FFmpeg false-fail), B-586 (frozen-gui-wrapper), B-615 (self-close ohne Save-Prompt).
- Weitere `open`-Marker: B-553, B-550, B-522, B-521, B-494, B-090(→F0), B-077.
- Verifikations-Audit 2026-06-18: 12 alte `fixed/PASS`-Marker ohne nachpruefbare Evidenz — vor Release neu belegen.

---

## Empfohlene Reihenfolge

1. **D2 (F0-Strategie)** + **D1 (B-619)** + **D3 (B-626)** — User entscheidet (blockiert Code).
2. **Tier F** F1→F2→F3→F4→F5 (Blob-Load-Sanierung), F6 mit Tier R.
3. **Tier V** — ein gebuendelter Testlauf.
4. **Tier R** — Release neu bauen/signieren/Clean-VM.
5. **Tier M** — User-Sichtung + `fixed`.
6. **Tier P** — Alt-Bug-Triage.

## Grenzen / Ehrlichkeit

- Tier-F-Fundstellen sind statisch + adversarial am Code bestaetigt, aber Freeze-Dauer NICHT live gemessen.
- F5/B-627 + Teil-B-625 (undo_commands, edit_workspace:598) sind `assumption_free=false` → Callsite-Thread-Analyse vor Fix.
- Tier P Marker teils veraltet — nicht als echt-offen angenommen, Triage explizit als eigener Schritt.

---

## FORTSCHRITT 2026-07-14

### Tier F — umgesetzt (Commits 25800dd, 2ce0f2d)
- F1 B-625: 6 Sites column-select ✅ (ab_compare AudioTrack teil-blocked, dokumentiert)
- F2 B-622: _build_otio_timeline ✅
- F3 B-623: storage_migration ✅
- F4 B-624: pacing_beat_grid ✅
- F0 B-090: NICHT global geaendert (D-070: pro-Callsite-Weg gewaehlt) ✅
- F5 B-627: analysis-only — GUI-Thread jetzt BELEGT, kein Fix (Off-Thread-Umbau = offener User-Entscheid)
- F6 B-618-Rest: offen (mit Tier R Release-Build)
Verify: adversarial diff (alle SAFE) + Import-Smoke 8/8 + pytest 14 passed.

### Tier D
- D2 entschieden: (b) pro-Callsite column-select → D-070 ✅
- D3 entschieden: B-626 = Bug, Fail-fast umgesetzt ✅
- D1 B-619: ZURUECKGESTELLT — Option 1 kollidiert mit Datenmodell (ClipAnchor kann
  Pool-Material nicht referenzieren, kein Pairing, CASCADE-Lifecycle). Agent-Empfehlung
  Option 2 (AudioVideoAnchor). User-Nachentscheid offen.

### Offen
- GUI-Live-Freeze-Messung (gebuendelter Test, User) — Tier V2/V3
- Tier R Release-Rebuild, Tier M fixed-Marker, Tier P Alt-Bug-Triage
- B-627 Off-Thread-Fix (User-Entscheid), ab_compare AudioTrack-Rest-Freeze

### Update 2026-07-14 (Commits 24b104a, 60f273d)
- D1 B-619 = Option 2 + Konsument (Timeline-Marker) UMGESETZT. anchor_sync_service +
  edit_workspace + timeline DialogAnchorMarkersItem. pytest 9 passed.
- F5 B-627 = Off-Thread UMGESETZT. embedding_scheduler non-blocking + fire-and-forget.
Tier-F/D Code damit weitgehend abgeschlossen. Offen: B-618-Rest (Frozen/Tier R),
ab_compare AudioTrack-Rest-Freeze, GUI-Live-Verify (Tier V2/V3), Tier R/M/P.
5 Commits lokal, ungepusht.
