# B-913 Prüfung im echten Produktpfad — Vision lehnt Learn ab (2026-08-30)

status: code-verified-no-gui-live
bug: B-913
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
verifier: Claude (agentseitig, kein User-Marker)

## Ziel

B-913 war `code-fix-pending-live-verification`: `brain_learn_note` lief im
Vision-Modus an der Mode-Allowlist vorbei und schrieb, obwohl Vision laut
B-738/D-083 strikt read-only ist. Belegt war der Fix bisher nur über
`tests/test_services/test_b738_brain_gateway.py` (`35 passed in 1.63s`), also
mit konstruierten Orchestrator-Objekten.

## Warum es keinen GUI-Live-Beleg gibt

Der Fehlerfall setzt voraus, dass das Sprachmodell im Vision-Modus von sich
aus ein `brain_learn_note`-Envelope erzeugt. Das lässt sich über die
Oberfläche nicht gezielt herbeiführen — man kann dem Modell nicht zuverlässig
vorschreiben, genau diese verbotene Aktion vorzuschlagen. Ein GUI-Klickpfad
wäre also entweder Zufall oder eine Manipulation der Modellantwort und damit
kein ehrlicher Livebeleg.

Statt dessen wurde der echte Produktcode direkt aufgerufen: ein eigener
Prozess (conda-Python `pb-studio`) ruft
`services.brain_gateway.execute_gateway_response()` mit einem echten
Antwort-String auf. Keine Mocks, kein Monkeypatch, keine Fakes — nur die
Funktion, die im Betrieb auch die Modellantwort verarbeitet.

## Ergebnis

Eingabe (identisch für beide Aufrufe):

```json
{"pb_brain_gateway": "v1", "action": "brain_learn_note",
 "params": {"text": "B-913 Live-Probe: dieser Eintrag darf nie geschrieben werden"}}
```

Vision-Modus mit `allow_learn=True` — also genau die Konstellation, die vor
dem Fix geschrieben hätte:

```json
{"action": "brain_gateway_rejected",
 "message": "Brain-Gateway abgelehnt: Aktion 'brain_learn_note' ist im vision-Gateway nicht erlaubt",
 "error": "Aktion 'brain_learn_note' ist im vision-Gateway nicht erlaubt"}
```

Chat-Modus ohne Merkauftrag als Gegenprobe:

```json
{"action": "brain_gateway_rejected",
 "message": "Brain-Gateway abgelehnt: brain_learn_note braucht ausdruecklichen Merk-/Speicherauftrag"}
```

Anschließend wurden alle SQLite-Datenbanken unter `AppData` und unter dem
Projektbaum nach dem Probetext durchsucht (Tabellen mit `note`/`mem` im Namen,
Text-Spalten): **0 Treffer**. Die Ablehnung ist also nicht nur eine Meldung —
es wurde tatsächlich nichts persistiert.

## Einordnung

Der Fix greift im echten Produktcode. Was fehlt, ist ausschließlich der Weg
über ChatDock und ein reales Ollama-Modell im Vision-Modus. Deshalb lautet der
Status hier bewusst `code-verified-no-gui-live` und nicht
`agent-live-verified`. `fixed` setzt ausschließlich der User.

## Belege

- Skript: `scratchpad/b913_gateway_check.py` (außerhalb des Repos)
- Produktcode: `services/brain_gateway.py:367-392`
