# PB_studio v0.4.0 — Ergonomie & Manual Pacing Bericht

## SEKTOR 1: Radikales Decluttering & Proportionen

### Vorher (Probleme)
- EDIT Workspace: Pacing-Steuerung (GroupBox) nahm 75% der oberen Haelfte ein (3:1 Ratio),
  Video-Vorschau war auf 320x180px / max 220px Hoehe beschraenkt
- Vertikale Slider in einzelnen GroupBoxen: jeder Slider brauchte ~120px Breite
- Timeline war ein GroupBox mit Titel-Overhead, bekam nur `stretch=1` aber keinen
  garantierten Platzanteil
- Alle Buttons in MEDIA hatten `setMinimumHeight(38-50)` — viel zu gross
- Chat-Dock hatte `setMinimumWidth(340)` — nahm zu viel Platz weg

### Nachher (Loesung)
1. **Video-Vorschau dominiert** (70% der oberen Haelfte, keine Hoehenbegrenzung)
2. **Inspector Panel** (rechts, 200-260px, einklappbar) ersetzt die riesige Pacing-GroupBox
   - Horizontale Kompakt-Slider (Label|Slider|Wert in einer Zeile)
   - Keine GroupBoxen mehr — flache Sections mit kleinen Labels
3. **Timeline bekommt 60% des vertikalen Raums** (main_splitter: 2:3 Ratio)
4. **Kein GroupBox-Wrapper** mehr um die Timeline
5. **Buttons in MEDIA** auf Standard-Hoehe reduziert (kein setMinimumHeight mehr)
6. **Chat-Dock** minimale Breite von 340px auf 240px reduziert
7. **Export-Buttons** von 50px auf 36px Hoehe reduziert

### Platzbilanz
| Bereich          | Vorher   | Nachher   |
|------------------|----------|-----------|
| Video-Vorschau   | 320x180  | 480+ x flex |
| Pacing-Controls  | ~400px W | ~240px W (Inspector) |
| Timeline         | ~35% H   | ~60% H    |
| Chat-Dock min W  | 340px    | 240px     |
| Button-Hoehe     | 38-50px  | 28-36px   |

---

## SEKTOR 2: Manuelles Pacing-Modul

### Was fehlte
Der alte Prototyp (Version B) hatte nur parametrische Slider und ein Anchor-System.
Es gab **keine Moeglichkeit**, die Schnitt-Dichte ueber die Zeit visuell zu zeichnen.
Der Nutzer konnte nur globale Werte (Tempo, Energie, Dichte) einstellen.

### Was jetzt integriert ist: PacingCurveWidget
- **Drawable Density Curve**: Der Nutzer malt mit Klick+Ziehen eine Dichte-Kurve
  ueber die gesamte Song-Laenge
- **200 Samples**: Interne Aufloesung fuer smoothe Kurven
- **Brush-Radius**: Beim Malen werden benachbarte Samples geglättet (Radius 3)
- **Visuelles Feedback**: Gefuellte Flaeche + Kurven-Linie mit Zeitachse
- **Reset-Button**: Setzt die Kurve auf 50% zurueck
- **Integration mit Pacing-Engine**: `PacingSettings.manual_density_curve` moduliert
  die Staerke jedes Cut-Points. Niedrige Dichte = Cuts werden ausgefiltert.

### Position im UI
```
┌─────────────────────────────────────────┬──────────────┐
│      Video-Vorschau (GROSS)             │  Inspector   │
│      Flexibel, keine Max-Hoehe          │  (einklappbar│
│                                         │   240px)     │
├─────────────────────────────────────────┴──────────────┤
│  MANUAL PACING [Reset]                                  │
│  ▁▂▃▅▇█▇▅▃▂▁▂▃▅▇████▇▅▃▁  (drawable curve, 55-75px)  │
├─────────────────────────────────────────────────────────┤
│  Timeline (Drag & Drop, Mausrad-Zoom)                   │
│  Volle Breite, maximaler vertikaler Raum                │
└─────────────────────────────────────────────────────────┘
```

### Technische Integration
- `pacing_service.py`: Neues Feld `manual_density_curve` in `PacingSettings`
- `calculate_cut_points()`: Vor dem Density-Filter wird jeder Cut-Strength mit dem
  Kurven-Wert an seiner Zeitposition multipliziert
- Effekt: Wo die Kurve niedrig gezeichnet ist, werden Cuts schwaecher und fallen
  unter den Threshold. Wo sie hoch ist, bleiben mehr Cuts erhalten.

---

## SEKTOR 3: KI-Agent Chat-Dock

### Aenderungen
- `chat_dock.py`: `setMinimumWidth` von 340 auf 240 reduziert
- `main.py`: Zusaetzlich `setMinimumWidth(220)` auf dem Dock gesetzt
- Das Chat-Dock ist jetzt standardmaessig schmaler und verdeckt weniger
  vom Edit-Workspace

---

## Zusammenfassung der geaenderten Dateien

| Datei | Aenderungen |
|-------|-------------|
| `main.py` | PacingCurveWidget hinzugefuegt, EDIT-Workspace komplett neu, Inspector Panel, kompakte Slider, schmalerer Chat-Dock, kleinere Buttons |
| `services/pacing_service.py` | `manual_density_curve` in PacingSettings, Curve-Modulation in calculate_cut_points |
| `ui/chat_dock.py` | Minimale Breite von 340 auf 240 reduziert |
| `resources/styles.qss` | Styles fuer PacingCurveWidget und Inspector Panel |
