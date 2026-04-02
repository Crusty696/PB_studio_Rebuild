# DJ-Set Struktur — Domain Knowledge

## Überblick der Sektionen

Ein typischer DJ-Set besteht aus aufeinanderfolgenden Sektionen mit unterschiedlicher
Energie und Pacing-Anforderungen. PB Studio erkennt diese Sektionen automatisch
aus der Audio-Analyse.

## Sektionstypen

### INTRO (0-5 Minuten)
- **Energie**: 0.1 – 0.3
- **Atmosphäre**: atmosphärisch, einladend, aufbauend
- **Pacing-Regel**: Sehr langsame Schnitte (32-64 Beats). Clips MÜSSEN lang laufen.
- **Video-Stil**: Establishing Shots, weite Landschaften, Zeitlupen
- **Beat-Hierarchie**: Nur auf 4-Beat-Grenzen schneiden

### WARMUP (5-20 Minuten)
- **Energie**: 0.2 – 0.4
- **Atmosphäre**: gemütlich, einladend, groove-building
- **Pacing-Regel**: Langsame Schnitte (16-32 Beats). Clips min. 8 Sekunden.
- **Video-Stil**: Crowd-Shots, DJ-Booth, Nahaufnahmen
- **Beat-Hierarchie**: Auf 8-Beat-Grenzen (Phrasen) schneiden

### BUILDUP (var.)
- **Energie**: 0.5 – 0.9 (steigend)
- **Atmosphäre**: Spannung, Erwartung, rising tension
- **Pacing-Regel**: Schnitte werden progressiv schneller (8→4→2→1 Beat).
  Letzte 16-32 Beats vor dem Drop: 1 Schnitt pro Beat.
- **Video-Stil**: Close-ups, Crowd-Reaktionen, Lichtstrahlen, Nebel
- **Beat-Hierarchie**: Beginnt mit 8-Beat-Grenzen, endet mit jedem Beat

### DROP (var., meist 32-64 Beats)
- **Energie**: 0.8 – 1.0
- **Atmosphäre**: explosiv, maximal, euphoric
- **Pacing-Regel**: Erste 8 Beats: 1 Schnitt pro Beat. Dann 2-4 Beats pro Schnitt.
  Bass-RMS-Sprung > 0.7 ist der exakte Drop-Trigger.
- **Video-Stil**: Schnelle Montage, Crowd-Euphorie, Visuals, Licht-Shows
- **Beat-Hierarchie**: Jeden Beat schneiden für maximale Wirkung

### BREAKDOWN (var.)
- **Energie**: 0.2 – 0.5
- **Atmosphäre**: reflektiv, emotional, ruhig nach dem Drop
- **Pacing-Regel**: Sehr langsame Schnitte (8-16 Beats). Clips min. 6 Sekunden.
  Vocals-aktiv? → Schnitt-Rate × 2 (Textverständlichkeit).
- **Video-Stil**: Atmosphärische Shots, Zeitlupen, Nahaufnahmen Gesichter
- **Beat-Hierarchie**: Nur auf Phrasen-Grenzen (8 Beats)

### TRANSITION (16-32 Beats)
- **Energie**: variabel (Mix-abhängig)
- **Atmosphäre**: Übergang, Bridge
- **Pacing-Regel**: Gleichmäßige Schnitte (4 Beats). Keine extremen Wechsel.
- **Video-Stil**: Mix aus letztem und nächstem Track-Stil
- **Beat-Hierarchie**: 4-Beat-Grenzen

### COOLDOWN / OUTRO (letzte 5-10 Minuten)
- **Energie**: 0.1 – 0.3 (abfallend)
- **Atmosphäre**: entspannt, Abschluss, nachklingend
- **Pacing-Regel**: Sehr langsame Schnitte (32+ Beats). Langer letzter Clip.
- **Video-Stil**: Weite Shots, Abschluss-Stimmung, Fade-Out
- **Beat-Hierarchie**: Nur auf 4-Beat-Grenzen

## Sektions-Übergänge

```
INTRO → WARMUP → BUILDUP → DROP → BREAKDOWN → (BUILDUP → DROP)* → COOLDOWN
```

- Jeder Übergang ist eine TRANSITION-Sektion
- Mehrere DROP/BREAKDOWN-Zyklen sind in langen Sets normal
- BPM-Änderungen > 5% zwischen Tracks = immer TRANSITION

## Energie-Mapping

```
Energie 0.0 - 0.3 = atmosphärisch, ruhig
Energie 0.3 - 0.5 = gemäßigt, groove-orientiert
Energie 0.5 - 0.7 = erhöht, treibend
Energie 0.7 - 0.9 = hoch, intensiv
Energie 0.9 - 1.0 = maximal, Drop/Climax
```
