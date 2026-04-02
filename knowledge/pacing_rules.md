# Pacing-Regeln — PhD-Level Audio/Video-Synchronisation

## Grundprinzip

**"Audio ist der Master, Video ist der Sklave."**
Die Musik diktiert Länge und Timing aller Schnitte. Video passt sich an — nie umgekehrt.

## Die Pacing-Formel

```
S_eff = S_base × E_factor × R_factor × B_factor × C_factor × M_factor
```

| Variable   | Bedeutung                                | Wertebereich |
|------------|------------------------------------------|--------------|
| S_base     | Basis-Schnittdauer (Beats)               | 1 – 64       |
| E_factor   | Energie-Skalierung                       | 0.5 – 2.0    |
| R_factor   | Reaktivitäts-Boost                       | 1.0 – 1.9    |
| B_factor   | Breakdown-Dämpfung                       | 0.5 – 1.0    |
| C_factor   | Kurven-Modulation (Ramp-up/down)         | 0.7 – 1.3    |
| M_factor   | Motion-Matching                          | 0.8 – 1.2    |

## Beat-Hierarchie

PB Studio analysiert drei Ebenen der Beat-Struktur:

1. **Beat-Ebene** (1x BPM): Einzelne Schläge — für maximale Intensität (DROP)
2. **Phrase-Ebene** (8x Beat): 8-Beat-Gruppen — Standard für WARMUP/BUILDUP
3. **Sektion-Ebene** (32x Beat): 32-Beat-Gruppen — für INTRO/COOLDOWN

**KRITISCH**: Schnitte dürfen NUR auf Beat-Timestamps fallen!
Off-Beat-Schnitte sind verboten und zerstören die Synchronisation.

## Stem-Gewichtung

| Stem    | Gewicht | Analyse-Zweck                              |
|---------|---------|--------------------------------------------|
| Drums   | 0.40    | Kick-Positionen, Snare, HiHat → Cut-Trigger |
| Bass    | 0.30    | Drop-Erkennung, Sub-Energie                |
| Vocals  | 0.10    | Ducking-Trigger, Textverständlichkeit       |
| Other   | 0.20    | Mood/Atmosphere-Matching                   |

## Drop-Erkennung (Kritische Regel)

Ein Drop wird erkannt wenn:
- Bass-RMS **vorher** < 0.2 AND Bass-RMS **nachher** > 0.7
- Energieanstieg innerhalb von 0.5s

Bei erkanntem Drop:
- S_eff = 1 Beat für die ersten 8-16 Beats
- Danach langsame Entspannung auf 4 Beats (16 Beats Übergang)

## Vocal-Ducking-Regel

Wenn `vocal_rms > 0.3` (Gesang aktiv):
- `S_eff × 2` (Clips doppelt so lang)
- Begründung: Zuschaurer müssen Text verstehen können
- Gilt auch bei Instrumental-Hooks mit dominanter Melodie

## Mindestdauer-Regel

- **Absolutes Minimum**: 1.5 Sekunden pro Clip (unter dieser Grenze wird der Clip übersprungen)
- **Empfohlenes Minimum**: 3.0 Sekunden (Standard)
- **Bei INTRO/COOLDOWN**: min. 8 Sekunden
- **Begründung**: Kürzere Clips sind nicht wahrnehmbar und erzeugen Flimmern

## Energie-abhängige Schnittrate

```python
if energy > 0.7:
    S_eff = S_eff / speed_boost  # max speed_boost = 1.9
elif energy < 0.3:
    S_eff = S_eff * 1.5  # langsamer bei niedriger Energie
```

## Motion-Matching

Motion-Score (0.0 – 1.0) kombiniert:
```
combined = E × 0.6 + M × 0.4
```
- Hoher Motion-Score → schnellere Schnitte → mehr Dynamik
- Niedriger Motion-Score → ruhigere Schnitte → Kontemplation

## Variety-Score

- **0.0**: Gleiche Clips wiederholen (Mantra-Effekt, für Drops)
- **0.5**: Ausgewogene Abwechslung (Standard)
- **1.0**: Maximale Abwechslung (für BUILDUP-Sequenzen)

Clips die bereits >3× gezeigt wurden, werden mit 50% Wahrscheinlichkeit übersprungen
(wenn Variety > 0.5).
