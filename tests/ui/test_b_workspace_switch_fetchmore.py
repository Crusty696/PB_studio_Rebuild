"""B-workspace-switch-freeze-qt-render: inkrementelles fetchMore() fuer
den Video-Pool.

Root-Cause (recherchiert 2026-07-15): der Video-Pool zeigte ALLE Zeilen
(375+ im Testprojekt) sofort per ``rowCount()`` beim Sichtbarwerden — Qt
musste die komplette Tabelle layouten/painten (cProfile: 88% Zeit in
``QApplication.notify``), das erzeugte bis zu 7,5s Main-Thread-Freeze beim
Workspace-Wechsel. Fix (User-Entscheidung: Option 2, fetchMore statt Pager):
``MediaTableModel(paginated_fetch=True)`` exponiert anfangs nur einen
kleinen Zeilen-Ausschnitt und laedt beim Scrollen inkrementell nach
(Qt-Standardmuster ``canFetchMore``/``fetchMore``) — freies Scrollen bleibt
erhalten, kein Pager-UX-Bruch.

Der Audio-Pool (``paginated_fetch=False``, Default) nutzt weiterhin
unveraendert den bestehenden ``PagedProxyModel``-Pfad — das muss diese Tests
NICHT betreffen (Regressionsschutz separat gepinnt).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _items(n: int) -> list[dict]:
    return [{"id": i, "title": f"clip_{i}"} for i in range(n)]


class TestPaginatedFetchVideoPool:
    def test_default_disabled_exposes_all_rows_immediately(self):
        """Backward-Kompatibilitaet: ohne paginated_fetch (Audio-Pool-Default)
        bleibt das alte Verhalten — rowCount() == len(items) sofort."""
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Audio")
        m.set_items(_items(250))
        assert m.rowCount() == 250
        assert m.canFetchMore(QModelIndex()) is False

    def test_paginated_fetch_exposes_only_initial_chunk(self):
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        assert m.rowCount() == m._INITIAL_FETCH_ROWS
        assert m.rowCount() < 375

    def test_can_fetch_more_true_while_rows_remain(self):
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        assert m.canFetchMore(QModelIndex()) is True

    def test_fetch_more_grows_row_count_incrementally(self):
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        before = m.rowCount()
        m.fetchMore(QModelIndex())
        after = m.rowCount()
        assert after == before + m._FETCH_CHUNK_ROWS
        assert after < 375

    def test_repeated_fetch_more_reaches_full_count_then_stops(self):
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        # Genug Iterationen, um garantiert alle Zeilen zu erreichen.
        for _ in range(10):
            if m.canFetchMore(QModelIndex()):
                m.fetchMore(QModelIndex())
        assert m.rowCount() == 375
        assert m.canFetchMore(QModelIndex()) is False
        # Ein weiterer fetchMore()-Call darf nichts mehr aendern (kein Crash,
        # keine Duplikate).
        m.fetchMore(QModelIndex())
        assert m.rowCount() == 375

    def test_small_pool_below_initial_chunk_exposes_all_immediately(self):
        """Kleinere Pools (< INITIAL_FETCH_ROWS) brauchen kein fetchMore —
        alle Zeilen sofort sichtbar, kein UX-Unterschied zu vorher."""
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(12))
        assert m.rowCount() == 12
        assert m.canFetchMore(QModelIndex()) is False

    def test_set_items_resets_fetched_count_to_initial_chunk(self):
        """Ein zweiter set_items()-Aufruf (z.B. Filter-Reload) darf nicht
        die durch vorheriges Scrollen erweiterte Fetch-Menge beibehalten —
        sonst waere der Freeze-Schutz beim naechsten Rebuild wirkungslos."""
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        m.fetchMore(QModelIndex())
        assert m.rowCount() > m._INITIAL_FETCH_ROWS

        m.set_items(_items(375))
        assert m.rowCount() == m._INITIAL_FETCH_ROWS

    def test_data_and_timeline_usage_stay_correct_within_exposed_range(self):
        """set_timeline_usage() darf nur ueber tatsaechlich exponierte
        Zeilen emittieren (rowCount()), sonst waeren Indizes ausserhalb des
        Fetch-Fensters ungueltig."""
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        # Kein Crash trotz 375 Items aber nur INITIAL_FETCH_ROWS exponiert.
        m.set_timeline_usage({0: 5, 374: 2})

        title_idx_first = m.index(0, 2)
        assert "[5×]" in m.data(title_idx_first, Qt.ItemDataRole.DisplayRole)

        # Item 374 ist (noch) nicht exponiert -> kein gueltiger Index im
        # Model, aber die reinen Datenwerte in _items bleiben unveraendert.
        assert m._items[374]["id"] == 374

    def test_checked_ids_track_full_pool_not_just_exposed_rows(self):
        """get_checked_ids()/toggle_all() muessen weiterhin den GESAMTEN
        Pool betreffen, nicht nur den aktuell exponierten Ausschnitt —
        sonst waere 'Alle auswaehlen' bei einem 375er-Pool kaputt."""
        _qapp()
        from ui.models.media_table_model import MediaTableModel
        m = MediaTableModel("Video", paginated_fetch=True)
        m.set_items(_items(375))
        m.toggle_all()
        assert len(m.get_checked_ids()) == 375
