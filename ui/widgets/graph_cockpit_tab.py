"""P1.5 / Cycle 11: Graph-Cockpit-Tab (D-023 P4 UI).

QWebEngineView-Widget das das Sigma.js-HTML aus
`services.graph.sigma_renderer.render_sigma_html` lädt + Klick-Events
über QWebChannel an das CockpitViewModel weiterreicht.

Pattern wie ui/studio_brain/audit_tab.py:
- QWidget-Subklasse
- View-Model-Injection im __init__
- Signal `nodeSelected(str)` bei Klick

Falls QtWebEngine nicht verfügbar (z.B. Headless-CI ohne Chromium):
fällt graceful auf einen Plain-QTextEdit-Fallback zurück.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from services.graph.cockpit_view_model import CockpitViewModel

logger = logging.getLogger(__name__)


def _try_import_qwebengine():
    """Try-Import-Helper — gibt None zurück wenn QtWebEngine fehlt."""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return QWebEngineView
    except ImportError as e:
        logger.warning("QWebEngineView nicht verfügbar — fallback auf Text-View: %s", e)
        return None


class GraphCockpitTab(QWidget):
    """Tab-Widget für den interaktiven Graph (D-023)."""

    nodeSelected = Signal(str)  # node_id
    statsRefreshed = Signal(dict)

    def __init__(
        self,
        view_model: CockpitViewModel | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._vm = view_model or CockpitViewModel()
        self._engine_cls = _try_import_qwebengine()
        self._build_ui()
        self._refresh_html()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header: Stats + Refresh
        header_row = QHBoxLayout()
        self.stats_label = QLabel(self.tr("Knoten: 0 | Kanten: 0"))
        header_row.addWidget(self.stats_label)
        header_row.addStretch()
        self.btn_refresh = QPushButton(self.tr("Aktualisieren"))
        self.btn_refresh.clicked.connect(self._refresh_html)
        header_row.addWidget(self.btn_refresh)
        layout.addLayout(header_row)

        # Splitter: Graph-View links, Detail-Panel rechts
        splitter = QSplitter(Qt.Orientation.Horizontal)

        if self._engine_cls is not None:
            self.web_view = self._engine_cls()
            splitter.addWidget(self.web_view)
        else:
            # Fallback: zeige Sigma-HTML als Text
            self.fallback_text = QTextEdit()
            self.fallback_text.setReadOnly(True)
            self.fallback_text.setPlaceholderText(
                "QtWebEngine nicht installiert — installiere PySide6-Addons "
                "oder nutze python -m pip install PySide6-Addons."
            )
            splitter.addWidget(self.fallback_text)
            self.web_view = None

        # Detail-Panel
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.addWidget(QLabel(self.tr("Knoten-Details")))
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)
        splitter.addWidget(detail_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    # ── Public API ─────────────────────────────────────────────────────────

    def set_view_model(self, vm: CockpitViewModel) -> None:
        self._vm = vm
        self._refresh_html()

    def select_node(self, node_id: str) -> None:
        """Externer Hook — z.B. von Decision-Explorer verlinkt."""
        result = self._vm.select_node(node_id)
        if "error" in result:
            self.detail_text.setPlainText(f"Knoten {node_id} nicht gefunden.")
            return
        self._show_node_details(result)
        self.nodeSelected.emit(node_id)

    # ── Internals ──────────────────────────────────────────────────────────

    def _refresh_html(self) -> None:
        stats = self._vm.stats()
        self.stats_label.setText(
            self.tr("Knoten: {n} | Kanten: {e}").format(
                n=stats["n_nodes"], e=stats["n_edges"]
            )
        )
        self.statsRefreshed.emit(stats)
        html = self._vm.render_html()
        if self.web_view is not None:
            try:
                self.web_view.setHtml(html)
            except Exception as e:  # broad: WebEngine-Renderer kann werfen
                logger.warning("setHtml failed: %s", e)
        else:
            self.fallback_text.setPlainText(
                f"Sigma-HTML rendered ({len(html)} chars). "
                "QtWebEngine nicht installiert — nur Text-Vorschau."
            )

    def _show_node_details(self, result: dict[str, Any]) -> None:
        node = result.get("node", {})
        neighbors = result.get("neighbors", [])
        lines = [
            f"Node: {node.get('title', '?')}",
            f"Type: {node.get('node_type', '-')}",
            "",
            "Neighbors:",
        ]
        for n in neighbors:
            lines.append(
                f"  → {n.get('target', '?')}  "
                f"({n.get('edge_type', '-')}, w={n.get('weight', 0.0):.3f})"
            )
        self.detail_text.setPlainText("\n".join(lines))
