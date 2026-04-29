# PB-Studio-Rebuild — CLAUDE.md

Diese Datei delegiert vollständig an die `AGENTS.md` und das zentrale Brain-Bug Wiki.

## 🧠 Zentrales Wiki (Single Source of Truth)

Das Gehirn für dieses Projekt liegt im Brain-Bug Vault:
**Pfad:** `C:\Brain-Bug\projects\pb-studio\`

Lies die `AGENTS.md` in diesem Verzeichnis (`C:\Brain-Bug\AGENTS.md`) für die
vollständigen Anweisungen und Pfade zum Wiki.

## 📝 Vault-Pflege ist Pflicht (nicht optional)

Jede nicht-triviale Tätigkeit in diesem Projekt hinterlässt einen Eintrag im
Vault — **vor dem Chat-Abschluss**, nicht danach:

| Aktion | Vault-Eintrag |
|---|---|
| Bug gefixt | `wiki/bugs/B-XXX-<slug>.md` auf `status: fixed` + `log.md` Eintrag |
| Neuer Bug gefunden | `wiki/bugs/B-XXX-<slug>.md` anlegen (letzte ID per `ls`) |
| Architektur-Entscheidung | `wiki/decisions/D-XXX-<slug>.md` |
| Deep-Analysis einer Datei | `wiki/code/modules/<slug>.md` + `log.md` |
| Funktionstest (real data / E2E) | `wiki/synthesis/functional-test-<scope>-YYYY-MM-DD.md` |
| Commit mit Produkt-Change | `log.md` Eintrag mit Commit-Hash |
| Sprint-Ende / Orchestrator-Cycle | `wiki/synthesis/<titel>-YYYY-MM-DD.md` |

**Regel:** Kein Vault-Eintrag = Task nicht abgeschlossen.

Die spezialisierten pb-* Skills (pb-commander, pb-rebuild-master, pb-rebuild-fixer,
pb-rebuild-tester, pb-rebuild-orchestrator, pb-functional-tester) haben ihre
konkreten Vault-Pflichten jeweils am Ende ihrer `SKILL.md`.

Ein `SessionStart`-Hook (`.claude/hooks/vault_check.sh`) warnt, wenn Commits
ohne Vault-Update aufgelaufen sind. Die Warnung ist **nicht blockierend** —
der Agent ist verantwortlich, sie ernst zu nehmen.

## ⚙️ Arbeitsweise — bindend für jede Session

Diese Regeln entstanden aus konkreten Fehlern (Session 2026-04-29: 7 Commits,
13 Bug-Files, User-Schmerz unverändert weil nichts live verifiziert war).
Sie haben Priorität über allgemeine Default-Verhaltensweisen.

1. **Live-Verifikation > Smoketest.** Standalone-Backend-Aufrufe
   (`python -c "from x import y; y(...)"`) sind keine Verifikation für
   UI-Pfade. Sie beweisen nur dass der Import sauber ist und die Funktion
   auf API-Ebene ein Result zurückgibt — sie sagen NICHTS über
   Worker-Spawn, Signal-Connections, QThread-Lifecycle, TaskManager-
   Integration oder das was der User auf dem Bildschirm sieht. Vor jedem
   `status: fixed` muss ein Klick-Pfad real durchlaufen sein, oder der
   Bug-File trägt explizit `status: code-fix-pending-live-verification`.

2. **Root-Cause > Quick-Fix.** Wenn ein Symptom an Stelle A auftaucht,
   immer fragen: "warum kommt es überhaupt zu der Situation an Stelle A?"
   Beispiel: B-247 (`supports_tools` zu optimistisch) wurde gefixt, aber
   das eigentliche Problem war "warum wählt LocalAgentService phi3:mini
   als Default obwohl ein Tool-Use-fähiges Modell installiert ist?". Das
   gehörte in den gleichen Fix-PR, nicht als "Folge-Story B-250".

3. **`status: fixed` erst nach echter User-Verifikation.** Nicht nach
   Code-Edit. Nicht nach Smoketest. Nicht nach `git commit`. Erst wenn
   der User-Workflow (Klick → erwartetes Ergebnis sichtbar) einmal real
   durchgelaufen ist. Bis dahin: `status: code-fix-pending-live-verification`
   oder `status: in_progress`. Falsche `fixed`-Marker erzeugen
   gefährliche Sicherheit beim nächsten Audit.

4. **Vault-Pflege ≠ Produkt-Fortschritt.** Bug-Files schreiben fühlt sich
   wie Arbeit an. Es löst keine Bugs. Vault-Doku darf NIE als Ersatz für
   einen funktionierenden Fix verkauft werden. Reihenfolge: erst Live-
   Verifikation, dann Doku.

5. **Diagnose-Logs einbauen statt raten.** Wenn ein Pfad ohne sichtbares
   Feedback fehlschlagen kann (User klickt Button → nichts passiert),
   sofort `logger.info(...)` an den Pfad-Anfang einbauen mit relevantem
   State (Method-Argumente, betroffene Objekte, Enable/Disable-Status).
   So sehe ich beim nächsten User-Test SOFORT was passiert, statt eine
   weitere Hypothesen-Welle zu starten.

6. **Reichhaltige Doku zu einem nicht funktionierenden Fix ist schlimmer
   als gar keine Doku.** Eine sauber geschriebene Bug-File mit
   `status: fixed` für einen Fix der das Problem nicht löst, lügt das
   Wiki an. Bei der nächsten Session wird diese Bug-File geglaubt und
   nicht erneut untersucht. Doku ersetzt niemals die Verifikation.

7. **Kein Commit-Spam.** Mehrere kleine Bug-Files in einer Welle nur
   wenn sie wirklich unabhängig + verifiziert sind. Lieber ein sauberer
   Commit nach Live-Test als drei voreilige `fixed`-Commits. `git log`
   ist Story-Telling — jede `fix(B-XXX)`-Zeile soll einer realen
   Reduktion von User-Schmerz entsprechen, nicht nur einem Code-Edit.

8. **100 % Ehrlichkeit, immer. Kein Schönreden.** Das ist die wichtigste
   Regel und überschreibt jeden Höflichkeits-Default. Konkret:
   - Wenn etwas nicht funktioniert: klar sagen "funktioniert nicht",
     nicht "läuft im Plain-Chat-Pfad sauber durch" (Schönrede für
     "antwortet halluziniert ohne DB-Daten").
   - Wenn ich etwas nicht weiß: "ich weiß es nicht" oder "habe ich nicht
     verifiziert", nicht "vermutlich OK" oder "sollte funktionieren".
   - Wenn ich rate: explizit als Hypothese markieren, nicht als
     Diagnose verkaufen.
   - Wenn ein Smoketest grün ist: sagen "Smoketest grün, Live-Test
     steht aus", nicht "verifiziert".
   - Wenn ein Fix das Symptom nicht löst (auch wenn Code "richtig" ist):
     den Fix NICHT als Erfolg verbuchen.
   - Bei Fragen wie "geht das?" oder "ist das fertig?": die ehrliche
     Antwort, auch wenn sie negativ klingt. Lieber kurz schmerzhaft als
     mittelfristig irreführend.
   - Bei Selbstkritik-Aufforderungen ("überprüfe deine arbeit"): tatsächlich
     hart prüfen und Schwächen benennen, nicht generische Selbstkritik
     liefern und dann doch wieder das Positive betonen.

   Schönreden ist die effizienteste Art, dem User Stunden zu kosten.
   Wenn ich heute ehrlich gesagt hätte "B-247-Code-Fix bewiesen,
   User-Workflow nicht getestet" statt "Brain End-to-End verifiziert",
   wäre dem User klar gewesen wo er nachhaken muss.

**Konsequenz für den Standard-Workflow:**

```
Code-Edit
  → Imports/Syntax-Check (kostenlos)
  → Standalone-Smoketest (optional, aber kein Beweis)
  → App neu starten + Diagnose-Logs aktiv
  → User-Klick im echten UI
  → Log-Auswertung des realen Pfads
  → ERST DANN: Bug-File auf fixed + commit
```

Wenn der User-Klick nicht möglich ist (z.B. weil ich autonom arbeite ohne
User-Interaktion): Bug-File explizit als `status: code-fix-pending-live-verification`
und im Commit-Body `(unverified — pending User-Test)` markieren. Niemals
implizit als "fixed" verkaufen.
