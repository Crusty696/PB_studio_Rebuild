# AGY-Handoff — PB-Studio Obsidian-Dashboard fertigbauen

Stand: 2026-07-28
Auftraggeber: David
Empfänger: Antigravity / AGY
Status: Dashboard unbrauchbar; vollständige Korrektur ausdrücklich an AGY übergeben.

## Einziger Startbefehl für AGY

> Lies `docs/superpowers/AGY_OBSIDIAN_DASHBOARD_HANDOFF.md` vollständig und führe den darin beschriebenen Dashboard-Auftrag autonom bis zur echten Live-Verifikation in Obsidian aus. Ändere ausschließlich Dashboard-/Obsidian-Konfiguration und zugehörige Vault-Doku; keinen PB-Studio-Produktcode, keine Plan- oder Bugstatusmarker.

## Ziel

Beim Öffnen von Obsidian muss sofort ein klar lesbares PB-Studio-Dashboard erscheinen. Es muss bei offenem Obsidian fortlaufend den aktuellen Arbeitsstand anzeigen:

- tatsächlich laufendes Stabilitätsprogramm;
- kanonischen Parent-Plan getrennt davon;
- aktuelle Phase, aktuelle Agenten-Task und letzten Update-Zeitpunkt;
- Fortschritt jeder STAB-Phase in Prozent;
- erledigte Belege;
- aktive Probleme/Blocker;
- exakt nächste Task;
- klar verständliche grafische Fortschrittsanzeige.

## Kanonische Wahrheitsquellen

1. Repo-Planwahl:
   `docs/superpowers/ACTIVE_PLAN.md`
2. Parent-Plan:
   `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`
3. Stabilitätsprogramm:
   Vault `projects/pb-studio/wiki/decisions/D-076-stabilitaetsprogramm-current-head.md`
4. Aktuelle Teststrategie:
   Vault `projects/pb-studio/wiki/decisions/D-078-tests-nach-restarbeiten.md`
   beziehungsweise aktuell verlinkte Nachfolgeentscheidung, falls Dateiname geändert wurde.
5. Laufender Live-Status:
   Vault `projects/pb-studio/wiki/synthesis/stability-status-current.md`
6. Aktiver Handoff:
   Vault `projects/pb-studio/index.md#Aktiver Handoff`
7. Chronologie:
   Vault `projects/pb-studio/log.md`

Wichtig: `ACTIVE_PLAN.md` nennt weiterhin den Masterplan als kanonischen Parent. Das aktuell ausgeführte Arbeitsprogramm ist das Stabilitätsprogramm D-076/D-078. Dashboard muss beide Ebenen klar trennen und darf sie nicht gegeneinander austauschen.

## Aktueller Live-Befund

Direkte Obsidian-Accessibility-Sichtung am 2026-07-28:

- Obsidian 1.12.7 startet mit `PB-Studio-Dashboard`.
- Eingebettete Statusquelle zeigte Update `2026-07-28 02:48 Europe/Zurich`.
- Aktive Task war `STAB-1 / B-741 Default-Suite-Ollama-Isolation`.
- STAB-0: 100 %.
- STAB-1: ca. 65 %.
- STAB-2 bis STAB-7: 0 %, jeweils durch Vorgängerphase blockiert.
- B-740 war code-fix-pending-live-verification; B-741 aktiv.
- Dashboard war dennoch unbrauchbar: zu lange Rohlisten, schwache Hierarchie, kaum visuelle Priorisierung, keine verlässlich bewiesene fortlaufende Aktualisierung.

Dieser Befund ist nur Ausgangspunkt. Vor jeder Änderung aktuelle Quellen erneut lesen.

## Bestehende Dashboard-Dateien

Vault-Root:
`C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug`

- Dashboard:
  `projects/pb-studio/PB-Studio-Dashboard.md`
- bisherige Base:
  `projects/pb-studio/wiki/dashboard/active-plans.base`
- Live-Status:
  `projects/pb-studio/wiki/synthesis/stability-status-current.md`
- Workspace:
  `.obsidian/workspace.json`
- Community-Plugin-Liste:
  `.obsidian/community-plugins.json`
- unbewiesener lokaler Refresh-Plugin:
  `.obsidian/plugins/pb-live-dashboard-refresh/manifest.json`
  `.obsidian/plugins/pb-live-dashboard-refresh/main.js`

## Nachgewiesene Fehler der bisherigen Umsetzung

1. Plan und Task wurden zeitweise hartcodiert (`B-739`), obwohl Statusquelle bereits `B-740`/`B-741` meldete.
2. Prozentwerte wurden doppelt im Dashboard gespeichert und wurden stale.
3. `active-plans.base` setzte `status: in_progress` voraus; Vault-Mirror verwendete zeitweise anderen Status. Damit war Planerkennung nicht zuverlässig.
4. Markdown-Transklusion aktualisierte sich für David bei offenem Obsidian nicht zuverlässig.
5. Lokaler Plugin `pb-live-dashboard-refresh` wurde nur per `node --check` und JSON-Parse geprüft. Kein belastbarer Obsidian-Livebeweis für Datei-Watcher oder 15-Sekunden-Refresh.
6. Dashboard zeigt große rohe Beweislisten statt kompakter „jetzt / fertig / Problem / als Nächstes“-Ansicht.
7. Phasendiagramm zeigte nur Reihenfolge; keine brauchbaren Fortschrittsbalken oder visuelle Blocker.
8. Fortschrittszahl `ca. 12–15 %` und Phasenwerte werden von Statusquelle geliefert, aber nicht berechnet. Keine erfundene Präzision ergänzen.
9. Obsidian zeigte beim Live-Check noch laufende Vault-Indizierung. Darauf nicht als dauerhafte Ursache verlassen.

## AGY-Arbeitsauftrag

1. Vor Änderung Repo-/Vault-Status und Agent-Claims prüfen.
2. Bestehendes Dashboard sowie lokalen Refresh-Plugin vollständig auditieren.
3. Falsche oder unbewiesene Dashboard-Mechanik ersetzen. AGY darf den lokalen Refresh-Plugin innerhalb dieses Scopes korrigieren oder entfernen.
4. Genau eine Live-Statusquelle verwenden. Keine manuell duplizierten Task-/Prozentwerte.
5. Dashboard visuell neu strukturieren:
   - Kopfkarte: laufendes Stabilitätsprogramm;
   - Parent-Plan separat;
   - große aktuelle Task;
   - „zuletzt aktualisiert“ plus sichtbare Frischewarnung;
   - acht kompakte Phasenbalken;
   - Bereich „gerade fertig“;
   - Bereich „aktiver Blocker“;
   - Bereich „nächste Task“;
   - Links zu Beleg/Decision/Bug.
6. Lange Historie standardmäßig einklappen oder auf separate Detailseite verlinken.
7. Obsidian muss Dashboard beim Start direkt in Leseansicht öffnen.
8. Fortlaufende Aktualisierung bei offenem Obsidian echt beweisen.
9. Vault nach jedem Sub-Schritt aktualisieren; keine `fixed`-Marker setzen.

## Erlaubter Änderungsumfang

- `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\PB-Studio-Dashboard.md`
- neue dashboardbezogene Dateien unter
  `projects/pb-studio/wiki/dashboard/`
- `.obsidian/workspace.json`
- `.obsidian/community-plugins.json`
- `.obsidian/plugins/pb-live-dashboard-refresh/`
- dashboardbezogene CSS-Snippets unter `.obsidian/snippets/`
- diese Handoff-Datei und Vault-Mirror
- `projects/pb-studio/log.md` und `index.md` nur für ehrliche Handoff-/Verify-Einträge

Nicht erlaubt:

- PB-Studio-Produktcode;
- Teststrategie oder Stabilitätsplan ändern;
- `status: fixed` setzen;
- Bug-/Planstatus ändern;
- aktive B-741-Arbeit anderer Agenten übernehmen;
- fremde Agenten-Claims bearbeiten oder freigeben.

## Abnahmekriterien

Dashboard gilt erst als fertig, wenn alle Punkte live in Obsidian bewiesen sind:

1. Obsidian kalt starten → Dashboard ist erste Hauptansicht.
2. Sichtbarer Titel nennt laufendes Stabilitätsprogramm, nicht nur Parent-Masterplan.
3. Aktuelle Task entspricht `stability-status-current.md`.
4. Jede STAB-Phase zeigt Prozent und Zustand.
5. Aktiver Blocker und nächste Task ohne Scrollen erkennbar.
6. Erledigte Schritte kompakt sichtbar; vollständige Beweise bleiben erreichbar.
7. Teständerung an einer ausschließlich dafür vorgesehenen Dashboard-Testquelle oder reversible Status-Testkopie:
   Dashboard aktualisiert sich bei offenem Obsidian innerhalb des definierten Intervalls.
8. Aktualisierung funktioniert mindestens zweimal nacheinander, ohne Obsidian-Neustart.
9. Nach Rücksetzen der Testdaten zeigt Dashboard wieder echte Current-Werte.
10. Keine Plugin-Fehler in Obsidian-Developer-Console.
11. Dashboard bleibt nach erneutem Obsidian-Neustart korrekt.
12. Screenshots/Live-Beleg und exakte Testzeit im Vault dokumentiert.

## Ehrlichkeitsregel

Syntaxcheck, Markdown-Render oder Obsidian-Neustart allein beweisen keinen Live-Refresh. „Fertig“ erst nach sichtbarer Quelländerung → automatischer Dashboard-Änderung bei offenem Obsidian → zweiter Wiederholung → Neustarttest.

## Übergabe-Endzustand

AGY liefert:

- genaue geänderte Dateien;
- Root Cause;
- Live-Testablauf und Resultate;
- Screenshot-Pfade;
- verbleibende Einschränkungen;
- Vault-Logeintrag;
- keine Aussage „automatisch“ ohne den oben definierten Live-Beweis.
