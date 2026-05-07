# Brain V3 User Guide

Brain V3 ist die Lern-Schicht ueber dem Pacing-System. Sie merkt sich, welche Schnitte du gut oder schlecht bewertest, und nutzt diese Daten spaeter fuer bessere Cut-Vorschlaege.

## Cold-Start

Cold-Start bedeutet: Brain V3 hat noch keine oder zu wenig Klick-Daten.

In diesem Zustand arbeitet Brain V3 nicht blind. Es nutzt Startwerte aus den bestehenden Pacing-/Trigger-Regeln. Diese Werte sind ein Fallback, kein Urteil ueber dein Material.

Wichtig:

- Cold-Start ist normal bei neuen Projekten oder nach Reset.
- Erste Vorschlaege koennen brauchbar sein, aber noch nicht persoenlich gelernt.
- Nach Bewertungen verlaesst Brain V3 Schritt fuer Schritt den Cold-Start.

## Feedback

Jeder bewertete Cut schreibt Lern-Daten fuer mehrere Kontext-Ebenen.

Die vier Ratings:

- Passt perfekt
- Passt
- Passt nicht ganz
- Passt gar nicht

Jeder Klick aktualisiert 17 Achsen in 6 Backoff-Levels. Das hilft Brain V3, auch dann zu lernen, wenn ein sehr genauer Kontext noch zu wenig Daten hat.

## Lern-Session

Eine Lern-Session zeigt unsichere Cuts, damit du Brain V3 gezielt trainieren kannst.

Lohnt sich besonders:

- nach einem neuen Import mit vielen Clips
- wenn die ersten Vorschlaege noch wechselhaft sind
- nach etwa 50+ Bewertungen im Projekt
- wenn du einen klaren visuellen Stil erzwingen willst

Nicht noetig:

- wenn du nur schnell einen einfachen Export brauchst
- wenn kaum neues Material dazugekommen ist
- direkt nach einem Reset ohne genug Clips

Status: Der Dialog existiert. Audio-/Video-Preview im Lern-Session-Dialog ist noch als offener Punkt dokumentiert.

## Confidence-Balken

Confidence bedeutet: Wie sicher Brain V3 bei einem Cut ist.

Der Balken ist ein schneller visueller Hinweis:

- Rot: wenig sicher, mehr Feedback hilft
- Gelb: mittlere Sicherheit
- Gruen: hohe Sicherheit

Ein gruener Balken bedeutet nicht automatisch "perfekt". Er bedeutet: Brain V3 hat fuer diesen Kontext genug passende Lerndaten.

Wenn kein Balken sichtbar ist, fehlen fuer diesen Cut entweder Confidence-Daten oder die UI hat sie noch nicht an das Timeline-Item uebergeben.

## Reset

Reset loescht gelernte Brain-V3-Gewichte und Pattern-Daten.

Danach startet Brain V3 wieder im Cold-Start. Hashes und Embedding-Cache sind davon getrennte Daten und werden nicht durch jeden Lern-Reset automatisch geloescht.

Reset lohnt sich nur, wenn:

- du komplett anderen Stil trainieren willst
- viele falsche Bewertungen im Projekt gelandet sind
- du Tests mit frischem Lernzustand brauchst

## Backup

Brain V3 erstellt woechentliche Backups der Hirn-Store-Datenbanken.

Gesichert werden:

- `weights.db`
- `patterns.db`
- `embedding_cache.db`

Die Retention ist konfigurierbar; aktuell werden standardmaessig die letzten 4 Backups behalten.

## Was Brain V3 nicht ersetzt

Brain V3 ersetzt nicht die normale Analyse. Beatgrid, Struktur, Embeddings, Pacing-Regeln und Medienimport muessen weiterhin funktionieren.

Wenn CUDA, NVENC oder Embeddings fehlen, kann Brain V3 nur den Teil nutzen, der bereits vorhanden ist.
