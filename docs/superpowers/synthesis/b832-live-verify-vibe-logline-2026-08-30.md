# B-832 Live-Verifikation — Vibe erreicht den auswertenden Code (2026-08-30)

status: agent-live-verified-await-user-marker
bug: B-832
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
decision: D-095
verifier: Claude (agentseitig, kein User-Marker)

## Ausgangslage

Ein erster Live-Versuch am selben Tag scheiterte an der Beobachtbarkeit, nicht
am Fix: `text_to_embedding()` schreibt bei Erfolg keine Logzeile, und die
Clip-Auswahl wird von einem Zufalls-Seed dominiert. Gemessen wurde damals ein
Lauf mit Vibe gegen einen ohne (6 von 80 gleichen Clips) und zwei Läufe ohne
Vibe gegeneinander (5 von 80) — der Vibe-Effekt lag vollständig im Rauschen.
B-832 blieb deshalb `code-fix-pending-live-verification`.

Auf ausdrückliche Anweisung des Users ("mach die logzeile rein und teste b832
nochmal") wurde der Vibe-Zweig instrumentiert.

## Änderung am Produktcode

`services/pacing_service.py:1176-1199`. Nach dem Aufruf von
`text_to_embedding()` unterscheidet der Code jetzt drei Fälle und protokolliert
sie:

- Erfolg → `INFO  B-832: Vibe-Embedding aktiv (<text>, dim=<n>, <n> Kandidaten)`
- Rückgabe `None` → `WARNING B-832: Vibe-Embedding nicht verfuegbar ... Vibe wirkt nicht`
- Vibe-Text gesetzt, aber keine Clip-Embeddings vorhanden → eigener
  `elif`-Zweig mit `WARNING ... Vibe wirkt nicht`

Die bestehende Exception-Warnung bleibt unverändert. Keine Logik-, Gewichts-
oder Auswahländerung; ausschließlich Protokollierung. `py_compile` PASS.

## Aufbau

App neu gestartet (der alte Prozess hielt noch den alten Code), PID 2556,
Projekt `123454321`, Audio `Maceo Plex - Sub-Alot`. Vor dem Neustart wurde die
Projekt-DB gesichert nach
`projects/123454321/pb_studio_2026-08-30_pre-b832-logline.db` (80 Video-Entries,
`quick_check ok`); nach dem Kill war die DB unverändert und weiterhin
`quick_check ok`. Bedienung wieder ausschließlich per UIA-Klick.

Zwei Läufe im direkten Vergleich, alles andere identisch:

**Lauf A — Vibe-Feld leer** (Referenz, 20:06:12). Log:

```
Schritt-3-Diversitaet: 80 Slots, 121 Videos, max_uses=1, seed=2659088890
Phase 3: 80 Segmente, 80 CutPoints, 337.1s Video (Audio 337.1s)
```

Keine einzige `B-832`-Zeile — korrekt, denn ohne Vibe-Text darf der Zweig gar
nicht laufen.

**Lauf B — Vibe-Text per Tastatur eingegeben** (20:07:04). Log:

```
SigLIP Batch: 29/29 Text-Embeddings berechnet
B-832: Vibe-Embedding aktiv ('dunkle hoehle, steine, kein gruen', dim=1152, 147 Kandidaten)
SigLIP Batch: 11/11 Text-Embeddings berechnet
Schritt-3-Diversitaet: 80 Slots, 121 Videos, max_uses=1, seed=3884086548
Phase 3: 80 Segmente, 80 CutPoints, 337.1s Video (Audio 337.1s)
```

## Bewertung

Der ursprüngliche B-832-Befund lautete: „Das Vibe-Feld erreicht im
Normalbetrieb nie den Code, der es auswertet." Genau das ist jetzt widerlegt.
Der eingetippte Text wird als 1152-dimensionaler SigLIP-Vektor eingebettet und
gegen alle 147 Kandidaten geführt — im laufenden Programm, im regulären
Auto-Edit, mit gefüllter VectorDB, also in exakt der Konstellation, in der das
Feld vorher wirkungslos war. Der Kontrast zu Lauf A ohne Vibe belegt, dass die
Zeile am Vibe-Text hängt und nicht generisch erscheint.

Der Zielvertragstest bleibt grün: `tests/test_services/test_b832_vibe_active_factor.py`
→ `4 passed in 0.94s`.

## Was weiterhin nicht belegt ist

Wie stark der Vibe-Faktor die Auswahl verschiebt, bleibt offen. Der Vergleich
Lauf A gegen Lauf B ergab 11 von 80 gleichen Clips — gegenüber 5 von 80 bei
zwei Läufen ohne Vibe ist das kein belastbarer Unterschied, weil beide Läufe
verschiedene Diversitäts-Seeds hatten (2659088890 gegen 3884086548). Belegt ist
also: der Vibe-Text kommt als Faktor an. Nicht belegt ist: wie viel er am Ende
bewegt. Dafür bräuchte es einen fixierten Seed.

Die Timeline-Qualität blieb unauffällig: 80 Segmente, kürzestes 2.213 s, keines
unter 2 s — der B-912-Ruhe-Floor gilt unverändert.

`fixed` setzt ausschließlich der User.

## Belege

- Screenshots: `tests/qa_artifacts/b832-run-boot_20260830_200539.png`,
  `b832-pacing-tab_20260830_200555.png`, `b832-vibe-set_20260830_200702.png`
- App-Log: `logs/pb_studio.log` (2026-08-30 20:06:12 und 20:07:04)
- DB-Sicherung: `projects/123454321/pb_studio_2026-08-30_pre-b832-logline.db`
