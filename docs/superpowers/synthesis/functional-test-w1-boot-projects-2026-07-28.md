---
title: PB Studio W1 Boot und Projekte — Current Live
date: 2026-07-28
status: live-pass-user-marker-pending
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
phase: STAB-2/W1
branch: codex/B-727-stability-gate
current_commit: d02f3c3
---

# W1 Boot und Projekte — Livebericht

## Verdict

`pass`, Usermarker offen. Kein `fixed`.

Current-Produktstand wurde sichtbar gestartet. Neues isoliertes Projekt,
bestehende isolierte Projekte, drei Projektwechsel, Shutdown, Neustart,
erneutes Öffnen und finaler nativer Shutdown bestanden.

## Isolierte Daten

- Projekt B:
  `%LOCALAPPDATA%\PBStudioStability\2026-07-28_122204\project\STAB-W1-B`
- Projekt C:
  `%LOCALAPPDATA%\PBStudioStability\2026-07-28_123634\project\STAB-W1-C`
- Host-Settings SHA256 vorher/nachher:
  `690EE75CD9FB2D36B053563C61B482F72EBCB7C06094CC134ABA3ECA3A2D6DFC`
- 15 geschützte Vorher-DB-Pfade unverändert.
- Schlussmanifest:
  `%LOCALAPPDATA%\PBStudioStability\20260728T130200-b745-native-close\manifest.json`
- Schlussmanifest: 17 DBs, 17/17 `quick_check=ok`, 0 geschützte Änderungen.

Originalprojekte, Originalmedien und Host-Settings wurden nicht verändert.

## Ausgeführter Nutzerpfad

1. App/Setup/Hauptfenster sichtbar gestartet.
2. `STAB-W1-B` und `STAB-W1-C` isoliert erstellt.
3. Bestehendes Projekt B per Dialog geöffnet.
4. Wechsel B→C.
5. Wechsel C→B.
6. Wechsel B→C.
7. Nativer Shutdown; App/Launcher beendet.
8. App neu gestartet.
9. Projekt C erneut per Dialog geöffnet.
10. Screenshot erstellt.
11. Nativer Shutdown wiederholt.

App blieb bei allen sichtbaren Schritten responding. Nach Shutdowns keine
sessioneigenen Python-/FFmpeg-/Ollama-Prozesse.

## Logs und Artefakte

- `logs/clicklog_2026-07-28_122204.log`
- `logs/clicklog_2026-07-28_123634.log`
- `logs/clicklog_2026-07-28_124208.log`
- `logs/clicklog_2026-07-28_124613.log`
- `logs/clicklog_2026-07-28_125017.log`
- `logs/clicklog_2026-07-28_125910.log`
- Screenshot:
  `%LOCALAPPDATA%\PBStudioStability\20260728T124829-w1-final\evidence\w1-restart-project-c.png`
- Screenshot SHA256:
  `E8DC6217E44E500089910A487478FF67FC0788F9BDDE40EDCCD289AA4E141618`

## B-743/B-744

- B-743: Session-Settings/RecentProjects bleiben im isolierten APPDATA.
- B-744: isolierter Erststart migriert keine Host-QSettings.
- Beide live bewiesen, aber ohne Usermarker weiter
  `code-fix-pending-live-verification`.

## B-745 Shutdown-Klärung

Vier programmatische UI-Automationsschlüsse erzeugten
`closeEvent ... spontaneous=False` und danach Windows-Code `0x80010108`
(`RPC_E_DISCONNECTED`). Zwei native Windows-Schlüsse erzeugten
`spontaneous=True`, vollständigen Cleanup und null Fatal-/Traceback-Treffer.

B-745 ist deshalb `wontfix` für Produktcode: Teststeuerungsartefakt, kein
Fehler im Nutzer-Shutdownpfad. Künftige Live-Gates schließen PB Studio nativ.

## Grenzen

- W1 beweist Boot/Projektwechsel/Persistenz/Shutdown, nicht Import oder Analyse.
- Exakter B-278-Timeout-Race wurde nicht erneut erzwungen.
- Usermarker für W1/STAB-2 fehlt; deshalb kein `fixed`.
