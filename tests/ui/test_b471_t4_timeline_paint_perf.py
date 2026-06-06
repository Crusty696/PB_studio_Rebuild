import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsLineItem
from ui.timeline import InteractiveTimeline, BeatGridItem

def test_timeline_paint_perf_uses_beat_grid_item(qapp) -> None:
    """T4: Testet, dass das Beatgrid ueber ein einzelnes BeatGridItem statt vieler LineItems gezeichnet wird."""
    timeline = InteractiveTimeline()
    
    # 1. Pruefen, ob BeatGridItem existiert und in der Szene ist
    assert hasattr(timeline, "_beat_grid_item")
    assert isinstance(timeline._beat_grid_item, BeatGridItem)
    assert timeline._beat_grid_item in timeline.scene().items()
    
    # 2. Grid setzen mit 100 Beats
    beats = [float(i) * 0.5 for i in range(100)]
    timeline.set_beat_grid(beats)
    
    # 3. Pruefen, ob die Daten im BeatGridItem ankommen
    assert timeline._beat_grid_item._beat_times == sorted(beats)
    
    # 4. Pruefen, ob KEINE QGraphicsLineItems fuer die Beats in der Scene erzeugt wurden
    line_items = [item for item in timeline.scene().items() if isinstance(item, QGraphicsLineItem)]
    # Eventuelle andere Linien (wie Ruler) herausfiltern: Ruler-Linie ist auf RULER_Y.
    # Beatgrid-Linien waren auf grid_top bis grid_bottom.
    beat_line_count = len([l for l in line_items if l.line().y1() < 100 and l not in timeline._ruler_items])
    assert beat_line_count == 0
