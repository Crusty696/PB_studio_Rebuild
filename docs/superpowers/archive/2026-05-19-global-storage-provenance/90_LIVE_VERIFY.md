# 90 — Globaler Live-Verify

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Verifikation

## Pflicht-Schritte (User)

1. **Migration:** Bestehendes V2 + Plan-A-Daten in `by_sha/`-Layout via Junctions registriert.
2. **SCHNITT-Audio-Subtab** funktioniert weiter ohne Code-Touch.
3. **Cross-Project-Reuse:** Datei in 2 Projekten → Notify-Toast, Analysen sofort gruen.
4. **File-Tracking:** Datei verschoben → App findet wieder via SHA.
5. **Storage-Browser:** Alle Files sichtbar, Bulk-Delete funktioniert.
6. **Project-Export + Import** auf andere VM.
7. **Backup + Restore** auf VM.

## Akzept-Kriterien

- [ ] Alle 7 Schritte ohne Stacktrace
- [ ] SCHNITT unangetastet, funktional
- [ ] V2-Pipeline laeuft weiter mit Provenance-Eintraegen
- **Erst dann** `status: fixed`
