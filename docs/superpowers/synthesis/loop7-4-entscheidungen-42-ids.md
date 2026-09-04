---
title: Loop 7.4 — Entscheidung zu den 42 Bug-IDs ohne jeden Testbezug
status: abgeschlossen
created: 2026-09-04
---

# Loop 7.4 — Entscheidung zu den 42 IDs ohne Testbezug

**Abbruchkriterium des Wächters:** *„Jede der 42 hat eine Entscheidung."*

`tools/fix_ohne_test.py` führt diese IDs als **nachweislich ungedeckt** — weder
die Bug-ID noch das umschließende Symbol kommt irgendwo unter `tests/` vor. Die
Mutationsprobe hilft hier nicht: wo kein Test ist, gibt es nichts zu messen.

Stand der Messung: `591 Bug-IDs im Produktivcode`, davon `57` in keinem Test
genannt, davon `42` nachweislich ungedeckt und `15` nur unbeschriftet.

## Entscheidung je ID

### A — Test nachgeliefert (8 IDs)

`tests/test_services/test_b979_loop7_charge_ohne_testbezug.py`, 28 Tests.
Ausgewählt nach zwei Kriterien: `severity: high` und ohne GUI/Hardware prüfbar.

| ID | Stelle | Was der Fix tut |
|---|---|---|
| B-244 | `services/actions/audio_actions.py:263` | Lese-Aktion `describe_audio_track` |
| B-335 | `services/brain/scorer.py:52` | gewichtetes Mittel statt Division durch Achsenzahl |
| B-354 | `services/convert_service.py:275` | NVENC prüft den echten Preset-Codec (GPU-Hartregel) |
| B-453 | `ui/widgets/media_grid.py:1002` | QPixmap entsteht auf dem GUI-Thread |
| B-622 | `ui/controllers/edit_workspace.py:957` | column-select statt `session.get` — 42-s-Freeze |
| B-795 | `ui/controllers/edit_workspace.py` (5×) | Projekt-Token-Guard für Auto-Edit |
| B-865 | `ui/controllers/project_management.py` (2×) | nur Auto-Resume überspringt den Hinweis |
| B-913 | `services/brain_gateway.py:397` | Vision-Modus durchläuft die Mode-Allowlist |

B-335 war zusätzlich per Handprobe am 2026-09-03 als ungedeckt **belegt**: Fix
umgekehrt, `8 passed` — kein Test bemerkte es.

### B — Kein Test, ID-Klärung geht vor (2 IDs)

| ID | Grund |
|---|---|
| B-216 | Vault: `reserved-gap`, `real_bug: false`, `component: [vault-index]`. Code: markiert eine echte Reparatur in `services/action_registry.py:27/247/256` (Loose-Fuzzy-Threshold für nicht-destruktive Aktionen). |
| B-217 | Vault: dieselbe Platzhalter-Datei. Code: markiert den Content-keyed L2-Norm-Cache in `services/pacing/scorer.py:168/205/632`. |

Zwei echte Reparaturen tragen IDs, die im Vault als „gibt es nicht" geführt
werden. Wer die ID nachschlägt, findet einen Platzhalter — der Kommentar im
Code wird dadurch unauffindbar. **Ein Test würde festschreiben, was gelten
soll, bevor geklärt ist, welche der beiden Quellen falsch ist.**

### C — Kein Test, Zustand steht zur Entscheidung (6 IDs)

| ID | Status | Grund |
|---|---|---|
| B-241 | `obsolete` | überholt |
| B-235 | `deferred` | zurückgestellt |
| B-864 | `open` | offen |
| B-922 | `open` | offen — Play-Knopf der Vorschau ist ein stiller No-Op |
| B-961 | `open` | offen — Registry prüft Pflichtparameter nicht, Userentscheidung |
| B-603 | `fixed`, 13 Stellen | Laut Vault scheitert der Batch-xfade-Pfad real und läuft im Hard-Cut-Fallback. Ein Test würde den Ist-Zustand als Soll zementieren — hier fehlt zuerst die Ursachenanalyse. |

### D — Bereits anderweitig gedeckt (1 ID)

| ID | Grund |
|---|---|
| B-330 | Die Fundstelle in `main.py:1947` ist ein Verweis im Kommentar. Der eigentliche Fix sitzt in `ui/widgets/wheel_guard.py:17-19` und hat dort einen Test (`tests/ui/test_wheel_guard.py:109`). |

### E — Test lohnt, aber nur im Live-Lauf prüfbar (7 IDs)

Diese hängen an GUI-Verhalten, Hardware oder langen Läufen. Sie gehören in den
nächsten Live-Rundgang, nicht in die Suite.

| ID | Warum nur live |
|---|---|
| B-435 | Power-Event-Flut — hängt an der Hardware (siehe B-978) |
| B-512 | GUI-Freeze bis 0,75 s pro Clip-Move |
| B-534 | Abbruch mitten in einer Download-Stream-Schleife |
| B-644 | Beatgrid-Darstellung („8-Bit-Look") — optisch |
| B-645 | Timeline-Zoom verschiebt die Spurposition |
| B-654 | Einstellungen-Dialog öffnet scheinbar spontan |
| B-716 | Kontext-Dock-X lässt den Toggle aktiv |

### F — Rest: Test möglich, Aufwand steht gegen Nutzen (18 IDs)

B-007, B-014, B-015, B-245, B-343, B-360, B-361, B-371, B-545, B-564, B-595,
B-600, B-617, B-623, B-624, B-632, B-636, B-740, B-794, B-798, B-856, B-898,
B-968, B-283.

Alle mit `severity: medium` oder `low` und Status `fixed`. Sie sind testbar,
aber jeder Test kostet mehr als er hier einbringt — das Schadensbild ist
entweder kosmetisch (B-644-Klasse), bereits durch benachbarte Tests mit
abgedeckt, oder betrifft Werkzeuge statt der App (B-856, B-864).

**Kandidaten für Loop 8**, in dieser Reihenfolge: B-600 (eine Assertion:
`STARTUP_FFMPEG_OUTER_TIMEOUT_SEC >= 2 × STARTUP_FFMPEG_CHECK_TIMEOUT_SEC`),
B-624/B-636/B-632 (dasselbe Query-Shape-Muster wie B-622, das Testmuster steht
schon), B-798 (ein statischer Scan-Test statt zwölf Einzeltests).

## Zusammenfassung

| Kategorie | IDs |
|---|---|
| A — Test nachgeliefert | 8 |
| B — ID-Klärung geht vor | 2 |
| C — Zustand offen | 6 |
| D — anderweitig gedeckt | 1 |
| E — nur live prüfbar | 7 |
| F — Aufwand gegen Nutzen | 18 |
| **gesamt** | **42** |

Jede der 42 hat damit eine Entscheidung. Das Abbruchkriterium von Schritt 7.4
ist erfüllt.

## Was dabei offen bleibt

* Die **ID-Klärung zu B-216/B-217** ist eine Userentscheidung: gilt der Vault
  (`real_bug: false`) oder der Code-Marker?
* Kategorie F ist eine **Aufwandsabwägung, keine Messung**. Wer die 18 doch
  abgesichert haben will, bekommt sie — die Reihenfolge oben nennt die drei
  günstigsten zuerst.
* Kategorie E setzt voraus, dass der nächste Live-Rundgang diese sieben Punkte
  gezielt ansteuert. Sie stehen sonst weiter ungedeckt.
