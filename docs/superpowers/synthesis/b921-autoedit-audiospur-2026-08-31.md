# B-921 behoben — der Auto-Edit legt die Tonspur mit (2026-08-31)

status: agent-live-verified-await-user-marker
bug: B-921
verifier: Claude (agentseitig, kein User-Marker)

## Userentscheidung

Auf die Frage, ob der Auto-Edit die Audiospur mitlegen oder der Export warnen
soll, entschied der User: mitlegen. Seine Begruendung trifft den Kern —
"als export muss ein musikvideo zusammen als finale rauskommen, warum sollte
dann die audiospur einzeln sein".

## Aenderung

**`services/timeline_service.py`**
- neuer Helfer `_ensure_audio_track_entry(session, project_id, audio_id)`:
  legt die Tonspur ueber die volle Trackdauer an, aber nur wenn noch keine
  Audiospur auf der Timeline liegt. Fehlt die Laenge, wird sie ueber denselben
  Weg nachgemessen wie beim manuellen Hinzufuegen (B-806). Ein unbekannter
  Track fuehrt zu einer Warnung, nicht zum Abbruch.
- `apply_auto_edit_segments(..., audio_id=None)` und
  `_do_apply_segments(..., audio_id=None)` reichen die ID durch.

**`ui/undo_commands.py`**
- `ApplyAutoEditCommand(..., audio_id=None)`. `redo()` merkt sich im Backup, ob
  bereits eine Tonspur lag; `undo()` entfernt die Spur nur, wenn dieser Lauf
  sie angelegt hat. Eine vorher vorhandene Spur bleibt unberuehrt.

**`ui/controllers/edit_workspace.py`**
- reicht die Audio-ID des Laufs an den Command weiter (`audio_id_override`,
  sonst die Auswahl der Audio-Combo).

**`tests/test_services/test_b683_timeline_apply_retry_backoff.py`**
- drei Test-Fakes an die erweiterte Signatur angepasst; sie bildeten
  `_do_apply_segments` mit zwei Parametern nach.

## Tests

Neu: `tests/test_services/test_b921_autoedit_audio_track.py`, vier Faelle —
Tonspur wird angelegt; eine bereits vorhandene (auch eine andere) bleibt
unangetastet; ohne `audio_id` bleibt das alte Verhalten; ein unbekannter Track
bricht den Apply nicht. `4 passed in 3.81s`.

Regression: `pytest -k "timeline or auto_edit or autoedit or undo or export"`
-> `367 passed, 4 skipped, 72 subtests passed in 166.96s`.

## Live-Verifikation

App aus dem Werkszustand gestartet (PID 11864), Projekt
`Erstlauf_Test_2026-08-30`. Ausgangslage bewusst wie beim Erstlauf-Test
hergestellt: Audiospur aus der Timeline geloescht, danach nur `track='video'`.

Ein einziger Klick auf `Auto-Edit starten` (02:45:03). Log:

```
Phase 3 Auto-Edit: Audio-Dauer = 337.1s
B-912 Ruhe-Floor: 1.840s (4 Beats), Cuts 102 -> 79, Section-Pflichtpunkte 26
Phase 3: 78 Segmente, 78 CutPoints, 337.1s Video (Audio 337.1s)
B-921: Tonspur des Auto-Edits auf die Timeline gelegt (audio_id=1, 337.137s)
```

Timeline danach: `audio=1, video=78`. Der EXPORT-Tab meldet ohne jeden
Zwischenschritt `Video-Clips: 78 | Audio-Tracks: 1 | Gesamt-Eintraege: 79`.

Anschliessender Export ohne weitere Handgriffe: `[LUFS] Normalisierung
erfolgreich -> -14.0 LUFS`, Ergebnis `exports/output.mp4` mit 721.440.099 Bytes.
`ffprobe`:

```
index=0  codec_name=h264  codec_type=video
index=1  codec_name=aac   codec_type=audio  sample_rate=48000  channels=2
nb_streams=2
duration=337.132357
```

Damit ist der Weg, der im Erstlauf-Test ein stummes Video ergab, jetzt
durchgaengig: Auto-Edit klicken, exportieren, fertiges Musikvideo mit Ton.

## Grenzen

- Kein Usermarker; `fixed` setzt der User nach eigener Abnahme.
- Das exportierte Video wurde technisch geprueft, aber nicht angesehen bzw.
  angehoert.
- Nicht getestet: mehrere Audiospuren im Projekt, Undo direkt nach einem
  Auto-Edit in der laufenden App (nur der Vertrag im Testcode ist abgedeckt).
