---
title: Waechter - Bilanz Loop 7 (gemessen) und Konfiguration Loop 8
status: laufend
created: 2026-09-04 21:30
---

# Waechter - Loop 8

## 1. Bilanz Loop 7 — gemessen

| Kennzahl | Loop 5 | Loop 6 | Loop 7 |
|---|---|---|---|
| Neue Funde | 4 | 8 | **7** (B-973 bis B-979) |
| Reparierte Bugs | 4 | 5 | 4 (B-973, B-975 teil, B-976, B-977) |
| Neue Pruefwerkzeuge | 2 | 1 | 0 (Werkzeug eingefroren — wie konfiguriert) |
| Neue Tests | 27 | ~140 | 49 (13 B-977, 8 B-975, 28 B-979) |
| Eigene Messfehler im Werkzeug | 0 | 7 | **0** |
| Live-GUI-Rundgaenge | 1 | 1 | 2 |

### Reparierte Bugs mit Beleg

| Bug | Was | Beleg |
|---|---|---|
| B-973 | `member_count` der Stil-Cluster um 46 zu hoch | DB nachgezaehlt: 105/66, 11/11, 29/22 vor dem Fix |
| B-975 | Ein abgewiesener Klick stand nur in der GUI-Konsole, nie im Logfile | Gate schreibt jetzt `logger.warning`; **Ursache des Klickverlusts bleibt offen** |
| B-976 | Pacing-Kurve zum Einzeichnen — vom Nutzer als unbrauchbar verworfen | Wirkung vorher gemessen: Rampen kommen an (Faktor 16), Wellen verpuffen. Ersetzt durch zwei Zahlen (Anfang/Ende) |
| B-977 | Rollenmatrix sperrte 60 % des Materials aus | Live: Notfallpfad 82x bei 79 Segmenten, nach dem Fix 13x (−84 %), B-768 greift gar nicht mehr |

**Dokumentiert ohne Aenderung, Userentscheidung steht aus:** B-974 (48 Szenen an
abgeschalteten Clustern), B-978 (1175 Logzeilen/Tag aus Power-Events).

### Loop 7.4 — die 42 IDs ohne Testbezug

Jede hat eine Entscheidung, damit ist das Abbruchkriterium erfuellt.
8 mit Tests nachgeliefert, 2 bis zur ID-Klaerung zurueckgestellt, 6 offen/
deferred/obsolete, 1 anderweitig gedeckt, 7 nur live pruefbar, 18 Aufwands-
abwaegung. Belegt in `loop7-4-entscheidungen-42-ids.md`.

Abnahme der 8: sechs Stellen geprueft, **alle sechs gedeckt** —
Mutationsprobe fuer B-453/B-622/B-913, Handprobe fuer B-335/B-354/B-244
(dort passte keine generische Mutation).

### Loop 7.5

Kriterium erfuellt **ohne Code-Aenderung**: beide DB-lesenden Skripte
(`tools/pacing_metrics.py:89`, `test-report/loop7/kurven_messung.py:7`) rufen
`set_project()` vor dem ersten Zugriff. Nachgemessen, nicht angenommen.

### Was in Loop 7 schiefging

| Fehler | Folge |
|---|---|
| Erster Regressionslauf per `nohup &` gestartet | Prozess starb mit der Shell, die Ausgabedatei enthielt nur Migrationszeilen. Kein Ergebnis, Zeit verloren |
| Beim Schliessen des Einstellungen-Dialogs OK statt Abbrechen getroffen | `qwen2.5:3b` wurde als Ollama-Modell gespeichert. Zurueckgesetzt, Sicherung `settings.json.vor-ruecksetzung-20260904_025824` |
| Drei Hypothesen zu B-975 nacheinander aufgestellt und selbst widerlegt | Ursache weiter offen; die Zeit floss in Hypothesen statt in Messung |
| Eine Hochrechnung als Aussage formuliert ("die 33 sind mehrheitlich ungedeckt") | Aus 3 Messungen extrapoliert. Im Bugfile B-971 richtiggestellt |

## 2. Die Luecke, die Loop 8 traegt

In 7.1 wurden alle fuenf Workspaces **geoeffnet**. Ausgefuehrt wurde nur
SCHNITT (Timeline generieren, Auto-Edit). **CONVERT und EXPORT wurden nie
gefahren.** Damit ist die Endstrecke der App — aus einer fertigen Timeline
eine abspielbare Videodatei zu machen — bis heute ungemessen.

Das ist genau der Teil, den der Nutzer am Ende benutzt.

Statische Vorpruefung der GPU-Hartregel im Export ergab **keinen Verstoss**:
`h264_nvenc` als Encoder, `libx264` nur als CPU-Fallback bei fehlendem NVENC,
`-c:v copy` beim Verketten (kein Re-Encode), kein fremder Backend
(`services/export_service.py:921-923, 1018`).

## 3. Konfiguration Loop 8 — die Endstrecke messen

**Werkzeuge unveraendert:** `pruefstand`, `mutationsprobe` (eingefroren),
`consulting-team`, `caveman ultra`.

| Schritt | Inhalt | Abbruchkriterium |
|---|---|---|
| 8.1 | Quick-Preview (10 s) im EXPORT-Workspace real fahren, Log aufzeichnen | Datei existiert, `ffprobe` bestaetigt Dauer/Codec/Aufloesung |
| 8.2 | Vollen Export der 79-Segment-Timeline fahren | Datei existiert, Dauer entspricht der Timeline (337 s ± 1 s), Videospur **und** Audiospur vorhanden |
| 8.3 | GPU-Hartregel **im Lauf** belegen, nicht nur im Quelltext | Kommandozeile im Log zeigt `h264_nvenc`; `nvidia-smi` zeigt Encoder-Last waehrend des Laufs |
| 8.4 | CONVERT real fahren (eine Datei, ein Preset) | Ausgabedatei per `ffprobe` geprueft, Preset-Codec eingehalten |
| 8.5 | `log_audit` nach jedem der vier Laeufe | Jede ERROR-Zeile einer Ursache zugeordnet, keine neue Wiederholungsgruppe unerklaert |
| 8.6 | A/V-Synchronitaet der Ausgabe aus 8.2 stichprobenhaft pruefen | Belegt oder als ungeprueft benannt — keine Behauptung ohne Messung |

**Bewusst ausgelassen:** weiterer Ausbau der Mutationsprobe; B-975
(nicht reproduzierbar — wird erst wieder angefasst, wenn der Zustand auftritt
und das neue Log ihn einordnet); B-603, B-870, B-923, B-960, B-961, B-966,
B-974, B-978 (Userentscheidung steht aus).

**Nicht als gedeckt gezaehlt:** B-891 (`edit_workspace.py:943`), B-371
(`pacing_service.py:1621`), B-795 und B-865 (in der Abnahme nicht gemessen —
die Tests existieren, ihre Wirksamkeit unter Mutation ist offen).

## 3b. Bilanz Loop 8 — die Endstrecke, gemessen

Alle sechs Schritte erfuellt. Zwei neue Funde, beide gefixt und **live**
verifiziert.

| Schritt | Ergebnis |
|---|---|
| 8.1 Quick-Preview | 10,006 s, h264 1920x1080 @30fps, aac 48 kHz stereo, 22,9 MB |
| 8.2 Voller Export | 337,131 s (Timeline 337,1 s), 10105 Videoframes, 15804 Audioframes, 722 MB, Lauf 2:46 |
| 8.3 GPU-Hartregel im Lauf | `TAG:encoder=Lavc60.31.102 h264_nvenc` in der Ausgabedatei; `GPU_EXECUTION_LOCK reason=batch_convert_nvenc` im Log |
| 8.4 CONVERT | 121/121 Dateien, **alle** per ffprobe geprueft: 121x `('h264',1920,1080,'30/1','h264_nvenc')`, 0 Abweichungen |
| 8.5 log_audit | **0 ERROR/CRITICAL**, 0 Muster unter 60 s Takt, alle fuenf Wiederholungsgruppen zugeordnet |
| 8.6 A/V | beide Spuren ab 0,000; 337,131 s gegen 337,130 s — 1,3 ms, kein Versatz |

### Zwei neue Funde — dieselbe Klasse

| Bug | Was | Live-Beleg |
|---|---|---|
| B-980 | Der Export-Controller definiert einen Logger und ruft ihn **nie** auf — 36 GUI-Ausgaben, 0 Logzeilen. Auch beide Fehlerpfade | `ui.controllers.export: [Export] fertig: ...` nach dem Fix |
| B-981 | Dieselbe Luecke im Convert-Controller: 121 Videos in 3:49, im Logfile zwei GPU-Lock-Zeilen | `ui.controllers.convert: [Convert] fertig: 121/121 Videos konvertiert` |

Zusammen mit B-975 (Schnitt-Gate) sind das **drei Stellen derselben Klasse**:
der Zustand steht am Bildschirm und ist nach dem Schliessen der App weg.

### Der Fund kam aus einem eigenen Irrtum

B-980 wurde sichtbar, weil ich den Preview-Lauf **zwoelf Minuten lang fuer
haengengeblieben hielt**: das Logfile endete nach `Concat-Export`, kein
ffmpeg-Prozess lief mehr. Tatsaechlich war die Vorschau nach rund 10 Sekunden
fertig — die Meldung stand nur in der GUI. Genau die Verwechslung, die der Bug
erzeugt, ist mir selbst passiert.

### Drei Regressionen aus Loop 7, gefunden und behoben

Der Regressionslauf ergab `20 failed, 5131 passed, 57 skipped in 3906.94s
(1:05:06)` gegen 17 in der Baseline. Der Abgleich mit
`tests/known_failures.json` zeigte drei neue — **alle drei aus meinen eigenen
Aenderungen**:

1. `test_schnitt_tooltip_audit` — die zwei neuen SpinBoxen aus B-976 hatten
   keinen Tooltip, der Zuruecksetzen-Knopf keinen accessibleName.
2. `test_hard_rule_drops_wrong_role` — kodierte die alte Rollenmatrix als Soll,
   die Userentscheidung B-977 hat sie geaendert.
3. `test_golden_run_snapshot` — Drift 8 -> 10 und 11 -> 13 passierte
   Kandidaten, exakt die gewollte Wirkung.

Beim Nachziehen von (2) **gemessen statt angenommen**: mit nur zwei Kandidaten
softet B-768 die Rollenmenge und laedt gerade `filler`/`unknown` nach — mit
`filler` liesse sich die harte Regel gar nicht zeigen. Der Test stellt jetzt
8 konforme Kandidaten bereit, dazu eine Gegenprobe, die fehlschlaegt, falls die
Matrix-Erweiterung verloren geht.

### Ein eigener Werkzeugfehler, wiederholt

Der erste Regressionslauf wurde per `nohup &` gestartet und starb mit der
Shell — die Ausgabedatei enthielt nur Migrationszeilen. Der Exitcode war
trotzdem 0, weil er vom `echo` kam. **Konsequenz: nach jedem langen Lauf erst
die Dateigroesse pruefen, nie den Exitcode allein.**

### Nicht erreicht

* B-975 bleibt ohne Ursache — der Zustand trat in diesem Loop nicht auf.
* Die Encoder-Wahl selbst steht in **keiner** Logzeile; belegt ist sie nur
  ueber das Metadatum der Ausgabedatei. Der B-980-Fix wurde bewusst auf die
  vier Abschluss-/Fehlerhandler begrenzt.
* 8.6 ist eine Container-Messung, **kein** inhaltlicher Bild-/Beat-Abgleich.

## 4. Wie der Waechter praeziser geworden ist

| Beobachtung aus Loop 7 | Konsequenz fuer Loop 8 |
|---|---|
| Werkzeug einzufrieren hat gewirkt: 0 Messfehler statt 7, dafuer 4 Reparaturen | Bleibt eingefroren. Erweitert wird erst, wenn ein Fund es zwingend verlangt |
| Der schwerste Fund (B-977, 60 % des Materials gesperrt) kam aus `log_audit` plus einer DB-Gegenrechnung | Jeder Live-Lauf endet mit `log_audit` **und** einer Gegenrechnung in der DB, nicht nur mit dem Blick ins Log |
| `nohup &` verlor den Prozess und damit einen 29-Minuten-Lauf | Lange Laeufe nur ueber den Hintergrundmodus des Werkzeugs, nie per `nohup &`. Vor der Auswertung Dateigroesse pruefen, nicht nur den Exitcode |
| Ein Fehlklick im Dialog aenderte eine Einstellung | Vor jedem Dialog-Schliessen die Zielkoordinate gegen das Element pruefen, nicht gegen die erwartete Position |
| Drei widerlegte Hypothesen zu einem nicht reproduzierbaren Zustand | Ohne Repro keine Hypothesenkette. Erst Messbarkeit herstellen (hier: das Log), dann warten |
| Fuer B-335/B-354/B-244 passte keine generische Mutation | "Ungemessen" wird nicht zu "gedeckt" aufgerundet, sondern per Handprobe entschieden — drei Handproben kosteten zusammen unter einer Minute |
| Die Endstrecke war nach sieben Loops noch nie gefahren | Ein Loop gilt erst als vollstaendig, wenn jeder Workspace nicht nur **geoeffnet**, sondern **ausgefuehrt** wurde |
| Der schwerste Fund kam aus einem eigenen Irrtum ueber ein schweigendes Logfile | Wenn ein Lauf still steht, zuerst pruefen, ob die Stille selbst der Bug ist — vor jeder Annahme ueber den Prozess |
| Drei Stellen derselben Klasse (B-975, B-980, B-981) | Bei einem Fund dieser Art gezielt nach Geschwistern suchen: welcher Controller definiert einen Logger und ruft ihn nicht auf? |
| Der Regressionslauf fand drei selbst verursachte Regressionen | Ein Loop endet erst nach einem Regressionslauf **mit Baseline-Abgleich**. "Meine Tests sind gruen" ist kein Ersatz |
| Eine Stichprobe von 1 Datei haette 8.4 auch "belegt" | Wo eine vollstaendige Pruefung Sekunden kostet (121x ffprobe = 25 s), wird nicht gestichprobt |
