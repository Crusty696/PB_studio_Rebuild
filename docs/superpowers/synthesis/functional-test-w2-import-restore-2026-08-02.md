---
title: PB Studio W2 Import, Papierkorb, Restore und Reuse — Current Live
date: 2026-08-02
status: live-pass-user-marker-pending
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
phase: STAB-2/W2
branch: codex/B-727-stability-gate
current_commit: b97dec4003475b8823f609938009f7ae08f5df01
---

# W2 Import, Papierkorb, Restore und Reuse — Livebericht

## Verdict

`pass`, Usermarker offen. Kein `fixed`.

Import, aktiver Duplikatimport, Bulk-Soft-Delete, Papierkorb, Bulk-Restore,
Reimport und Cross-Project-Reuse wurden in sichtbarer Current-App ausgeführt.
B-740-Ownership-/Shutdownpfad wurde anschließend Current-live bestanden.

## Isolierte Daten

- Projekt A:
  `%LOCALAPPDATA%\PBStudioStability\20260728T131500-w2\project\STAB-W2`
- Projekt B:
  `%LOCALAPPDATA%\PBStudioStability\2026-08-02_070155\project-cross-reuse\STAB-W2-REUSE-B`
- Medien: ausschließlich Kopien unter `%LOCALAPPDATA%\PBStudioStability`.
- Premanifest:
  `%LOCALAPPDATA%\PBStudioStability\20260728T131800-w2-pre\manifest.json`
- Postmanifest:
  `%LOCALAPPDATA%\PBStudioStability\20260802T0801-w2-post\manifest.json`
- Finalmanifest nach B-740:
  `%LOCALAPPDATA%\PBStudioStability\20260802T0818-w2-final\manifest.json`

15/15 geschützte Pre-Pfade blieben für DB/WAL/SHM in Existenz, Größe und
SHA256 unverändert. Post: 18/18 `quick_check=ok`; drei zusätzliche DBs sind
isolierte Laufdaten. Host-Settings SHA256 unverändert:
`690EE75CD9FB2D36B053563C61B482F72EBCB7C06094CC134ABA3ECA3A2D6DFC`.

## Bestandene Nutzerpfade

1. Zwei Videos und ein Audio importiert.
2. Aktiver Duplikatimport erzeugte keine zweite aktive Row.
3. Zwei Videos zusammen soft-gelöscht und im Papierkorb sichtbar geprüft.
4. Beide Videos zusammen restauriert; DB `deleted_at=null`, UI zwei Rows.
5. Reimport blieb idempotent.
6. Audio V2 in Projekt A vollständig ausgeführt; vier Stem-Artefakte erzeugt.
7. Identisches Audio in Projekt B importiert; Reuse-Backend schrieb
   `stem_separation/done` mit `reuse_source_project=STAB-W2`.
8. B-747 behoben: sichtbarer Dialog meldet Wiederverwendung trotz
   kollidierendem Legacy-Registry-Key `muted_project_1=true`.
9. Native Shutdowns mit `spontaneous=True`; PB-Python und aktuelle App-Kinder
   danach 0.

## Bugs

- B-746 Audio-Modus-No-Op: Fresh Current-Live nicht reproduzierbar;
  Audioansicht schaltete sichtbar um. Kein Codefix.
- B-747 Mute-Key-Kollision: projektpfadgebundener SHA-256-Key, RED/GREEN,
  Ruff und Current-Live-Dialog grün; Usermarker offen.
- B-740: alter PID-5944-Rest stammte aus abnormal beendeter Session ohne
  Exitmetadaten. Nach Ownership-Beweis exakt entfernt. Frische Current-App
  startete eigenen Serve+Runner; nativer Shutdown beendete App, Serve und
  Runner vollständig. Port 11434 frei; Usermarker offen.

## Artefakte

- `tests/qa_artifacts/w2-video-imported_20260728_132554.png`
- `tests/qa_artifacts/w2-two-videos-selected-20260728-1402_20260728_134223.png`
- `tests/qa_artifacts/w2-trash-bulk-selected-20260801_20260801_101208.png`
- `tests/qa_artifacts/b747-reuse-dialog-live_20260802_075722.png`
- `logs/clicklog_2026-08-02_070155.log`
- `logs/pb_studio.log`

## Minimaltests B-747

- RED: 1 erwarteter Fehler wegen fehlendem Key-Helper.
- GREEN: 1 bestanden in 5.25 s.
- `py_compile` Exit 0.
- Ruff für zwei geänderte Dateien grün.
- Keine breite Suite.

## Nächste einzige Task

`LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes Stem`.

W2 ist Current-live bestanden. Vollständiger Audio-V2-Lauf mit vier Stems liegt
bereits als W3-Teilevidenz vor; offen bleiben Cancel während AV-Pacing, Retry,
Neustartvergleich und fehlendes Stem-Artefakt.
