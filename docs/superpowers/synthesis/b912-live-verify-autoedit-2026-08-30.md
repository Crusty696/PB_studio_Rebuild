# B-912 Live-Verifikation — echter Auto-Edit-Lauf im Benutzerprojekt (2026-08-30)

status: agent-live-verified-await-user-marker
bug: B-912
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
worktree: main
verifier: Claude (agentseitig, kein User-Marker)

## Ziel

B-912 war `code-fix-pending-live-verification`: die Beat-Stufe nach Drop/Onset
wurde zur harten Ruhe-Untergrenze gemacht, damit die Timeline nicht nervös
wirkt. Bisher existierte dafür nur ein Zielvertragstest (`4 passed in 2.17s`),
kein Beleg aus einem echten Auto-Edit-Lauf in der laufenden App.

## Aufbau

- App live gestartet über `tests/gui_harness.py start`, PID 5236, Fenster
  `PB_studio v0.5.0 — 123454321`.
- Projekt: Benutzerprojekt `123454321`, Audio `Maceo Plex - Sub-Alot`
  (130.4 BPM, 337.1 s), Video-Pool aus `Solo_Natur`.
- GPU vor dem Lauf: GTX 1060, 0 von 6144 MiB belegt. Port 11434 frei,
  verwaister Ollama-Prozess vorher beendet.
- Bedienung ausschließlich über echte UIA-Klicks (`click-element`), keine
  direkten Methodenaufrufe.

## Baseline vor dem Lauf

Direkt aus der Projekt-DB (read-only) gemessen:

| Größe | Wert |
| --- | --- |
| Video-Segmente | 80 |
| kürzestes Segment | 2.213 s |
| längstes Segment | 9.543 s |
| Segmente unter 2 s | 0 |
| Segmente unter 1 s | 0 |

Vor dem Überschreiben gesichert nach
`projects/123454321/pb_studio_2026-08-30_pre-b912-live-autoedit.db`
(51.666.944 Bytes, `quick_check ok`).

Zum Vergleich die im Masterplan dokumentierte Ausgangslage von B-912:
103 Segmente, davon 34 unter 2 s und 9 unter 1 s, Minimum 0.395 s.

## Ablauf

Ein erster Klickversuch war wirkungslos und ist hier vollständigkeitshalber
festgehalten: `click-element --auto-id schnitt_editor.btn_accent` traf den
Nachbarbutton `Timeline generieren`, weil beide Buttons im SCHNITT-Header
dieselbe auto_id tragen. Der dadurch geöffnete modale Dialog
`Pacing neu anwenden?` blockierte den anschließenden Auto-Edit-Klick. Das
bestätigte `Yes` löste folglich nur die Vorschau aus — Log zeigt
`set_beat_markers count=185` und `set_cut_points count=185` bei unveränderter
Datenbank. Das entspricht dem dokumentierten Verhalten in
`ui/workspaces/schnitt/editor_view.py:95-105` (B-833): der Vorschau-Button
zeichnet nur Linien und schreibt nichts.

Der eigentliche Lauf wurde danach über `--name "Auto-Edit starten"` ausgelöst
(19:49:26). Overlay `Auto-Edit läuft… / Lade Audio…` erschien, Task
`Auto-Edit (Phase 3)` stand auf `Running`.

## Pacing-Kette im Log

```
Phase 3 Auto-Edit: Audio-Dauer = 337.1s
Stem-SNR: drums=46.3 dB, bass=55.6 dB, vocals=57.3 dB, other=34.0 dB
Stem-gewichtete Energie berechnet: 738 Beats
Sektionen aus Struktur-Analyse (DB): 27 Sections
Drop-Detection: 1 Drops erkannt
Transition-Detektion: 4 DJ-Uebergaenge erkannt
Roter Faden: 94 Schnittanlaesse (start=1, section=16, drop=6, energie=32, maximaldauer=39)
Mindestdauer: 96 -> 96 Cut-Beats (entfernt: 0)
finalize_cut_beats: 96 -> 104 Cuts (26 Pflicht-Cuts an Section-Grenzen)
T2.5.2 Drop-Burst: 104 -> 105 Cuts
T2.5.1 Onset-Snap: 87/103 Cuts auf Kick/Snare-Onsets verschoben (+-50ms, 2185 Onsets)
B-912 Ruhe-Floor: 1.840s (4 Beats), Cuts 105 -> 81, Section-Pflichtpunkte 26
Phase 3: 80 Segmente, 80 CutPoints, 337.1s Video (Audio 337.1s)
Timeline: 80 Video-Segmente geschrieben (project=1, locked-aware)
B-598 ApplyAutoEditCommand.redo apply_auto_edit_segments project_id=1 segments=80
```

Die entscheidende Zeile ist `B-912 Ruhe-Floor: 1.840s (4 Beats),
Cuts 105 -> 81, Section-Pflichtpunkte 26`: der Fix läuft im Produktivpfad,
entfernt 24 zu eng stehende Cuts und lässt die 26 echten Section-Grenzen als
Pflichtpunkte stehen — genau der im Fix beschriebene Vertrag.

## Ergebnis nach dem Lauf

| Größe | Wert |
| --- | --- |
| Video-Segmente | 80 |
| kürzestes Segment | 2.213 s |
| längstes Segment | 9.543 s |
| Median | 3.659 s |
| Mittelwert | 4.214 s |
| Summe | 337.14 s (Audio 337.1 s) |
| Segmente unter dem Floor 1.840 s | 0 |
| Segmente unter 2 s | 0 |
| Segmente unter 1 s | 0 |

Der Lauf hat die Timeline tatsächlich neu geschrieben: gegenüber dem Backup
sind alle 80 Schnittzeitpunkte identisch (der Beat-Grid-Pfad ist
deterministisch), aber nur 5 von 80 Clips gleich — die Clip-Auswahl lief mit
neuem Seed (`Schritt-3-Diversitaet: 80 Slots, 121 Videos, max_uses=1,
seed=1435685965`). Die Timeline-Leiste zeigt danach
`80 Cuts | Beat:48 | DJ-Mix:32 | 337s | 80 Segmente`, der Task steht auf
`Fertig`.

`find-crash` meldet 14 Treffer, alle mit Datum 2026-08-27 bzw. 2026-08-29 aus
früheren Sitzungen. Aus dem heutigen Lauf stammt kein einziger Crash-Eintrag.

## Bewertung

Der B-912-Fix ist im echten App-Lauf wirksam: kein Segment liegt unter der
Ruhe-Untergrenze, das kürzeste ist 2.213 s statt zuvor 0.395 s, und die
Section-Pflichtpunkte bleiben erhalten. Status daher
`agent-live-verified-await-user-marker`.

`fixed` setzt ausschließlich der User. Nicht abgedeckt bleibt die subjektive
Frage, ob die Timeline für den User ruhig genug wirkt — das ist eine
Wahrnehmungsfrage und kein messbares Kriterium.

## Belege

- Screenshots: `tests/qa_artifacts/live-verify-boot_20260830_194537.png`,
  `live-verify-autoedit-1_20260830_194715.png`,
  `live-verify-autoedit-2_20260830_194927.png`,
  `live-verify-b912-done_20260830_195049.png`
- DB-Sicherung: `projects/123454321/pb_studio_2026-08-30_pre-b912-live-autoedit.db`
- App-Log: `logs/pb_studio.log` (2026-08-30 19:49:26 bis 19:49:58)

## Nebenbefund

`auto_id="schnitt_editor.btn_accent"` ist im SCHNITT-Header doppelt vergeben
(`Timeline generieren` und `Auto-Edit`). Für Livetests ist dort nur `--name`
zuverlässig. Kein Produktcode geändert.
