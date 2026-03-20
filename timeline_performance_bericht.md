# Timeline Performance & Visual Fix — Bericht

## Sektor 1: LOD & Culling im WaveformGraphicsItem

### Tile-basiertes Caching
- Die monolithische `_render_pixmap()` (ein einziges riesiges QPixmap) wurde durch ein **Tile-System** ersetzt (`TILE_WIDTH = 512px`)
- Tiles werden **on-demand** gerendert und gecacht — nur sichtbare Tiles werden erzeugt
- Bei Zoom-Änderung wird der Tile-Cache invalidiert

### Culling via exposedRect
- `paint()` nutzt jetzt `option.exposedRect` um den sichtbaren Bereich zu bestimmen
- Nur Tiles im sichtbaren Viewport werden gezeichnet (Tile-Index-Range Berechnung)
- `ItemUsesExtendedStyleOption` Flag gesetzt, damit Qt die exposedRect korrekt befüllt

### Multi-Level LOD-Beatgrid
- Durchschnittlicher Beat-Abstand in Pixeln wird berechnet
- **3 LOD-Stufen**:
  - `< 4px` (`LOD_BEAT_MIN_SPACING_PX`) → alle Beats ausgeblendet
  - `< 12px` (`LOD_BEAT_DOWNBEAT_ONLY_PX`) → nur Downbeats (jeder 4.) sichtbar
  - `≥ 12px` → alle Beats sichtbar
- **Binary Search** (`bisect`) statt linearer Scan für sichtbaren Beat-Bereich (O(log n) statt O(n))
- Vorberechnete QPen-Objekte (pen_downbeat/pen_normal) — keine QPen-Erstellung pro Beat
- Beats werden direkt gezeichnet (nicht gecacht), damit sie sofort auf Zoom reagieren

### Downsampling bei Zoom-Out
- Wenn mehr als 2 Samples auf ein Pixel fallen → **Mittelwert** statt Einzelsample
- Verhindert Moiré-Artefakte und überlappende vertikale Striche
- **Optimiert**: `sum(list[start:end])` statt manueller Python-Schleife (C-Level Iteration)
- Lokale Variablen-Referenzen (`band_low = self._band_low`) für schnelleren Attribut-Zugriff
- Saubere, gemittelte Wellenform beim Rauszoomen

### Farb-LUT (Lookup Table)
- 32 vorberechnete Farben pro Band (Low/Mid/High) statt QColor-Erstellung pro Pixel
- Elimiert ~3 QColor-Konstruktionen pro Pixel × tausende Pixel = massive Ersparnis

## Sektor 2: Zoom- & Navigations-Mechanik (Ableton Feel)

### Zoom zur Mausposition
- `setTransformationAnchor(AnchorUnderMouse)` — Zoom zentriert sich auf Cursor
- `setResizeAnchor(AnchorUnderMouse)` — konsistentes Verhalten bei Resize

### Sanfterer Zoom-Faktor
- Von 1.15 auf **1.08** reduziert → flüssigeres, weniger springendes Zoomen
- Zoom-Bereich begrenzt: 0.01x bis 200x (verhindert Extremwerte)

### Panning (Verschieben der Timeline)
- **Mittlere Maustaste**: Gedrückt halten → Timeline verschieben
- **Space + Linksklick**: Alternative Panning-Methode (wie Ableton/Photoshop)
- Cursor wechselt visuell: OpenHand → ClosedHand beim Ziehen
- Direkte ScrollBar-Manipulation für sofortige Reaktion

## Sektor 3: Hardware-Rendering

### OpenGL Viewport
- `QOpenGLWidget` wird als Viewport gesetzt (GPU-beschleunigtes Rendering)
- Try/Except Fallback: Wenn OpenGL nicht verfügbar → Software-Rendering
- Kombiniert mit dem Tile-Cache-System für optimale Performance

### Bestehende Optimierungen (beibehalten)
- `CacheBackground` — Hintergrund wird nicht neu gezeichnet
- `DontSavePainterState` — spart QPainter save/restore Overhead
- `SmartViewportUpdate` — Qt entscheidet intelligent über Neuzeichnen

## Erwartete Performance-Verbesserungen

| Bereich | Vorher | Nachher |
|---------|--------|---------|
| Wellenform bei 5min Track | 1x 6000px Pixmap | ~12 Tiles à 512px (on-demand) |
| Beatgrid bei Zoom-Out | Alle ~600 Beats gezeichnet | 0 Beats / nur Downbeats (Multi-LOD) |
| Beat-Suche sichtbarer Bereich | O(n) linear scan | O(log n) binary search |
| Farbberechnung | 3× QColor() pro Pixel | LUT-Lookup (O(1)) |
| Zoom-Anchor | Viewport-Mitte | Mausposition |
| Panning | Nicht möglich | Maus/Space+Click |
| Rendering | Software (CPU) | OpenGL (GPU, mit Fallback) |
