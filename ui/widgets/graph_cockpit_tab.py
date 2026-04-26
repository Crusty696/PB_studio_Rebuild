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

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
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


class _CockpitBridge(QObject):
    """QWebChannel-Bridge: JS-Sigma-clickNode ruft Slot, Python emittiert
    Signal weiter.

    P0 #3 Cycle 11: ohne diese Bridge kann der User den Graph zwar
    visuell sehen, aber nicht interaktiv navigieren. Sigma.js-clickNode
    feuert ``cockpitBridge.onNodeClicked(nodeId)`` (über QWebChannel).
    """
    nodeClickedFromJs = Signal(str)

    @Slot(str)
    def onNodeClicked(self, node_id: str) -> None:
        self.nodeClickedFromJs.emit(node_id)


def _try_import_qwebengine():
    """Try-Import-Helper — gibt None zurück wenn QtWebEngine fehlt."""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
        return QWebEngineView
    except ImportError as e:
        logger.warning("QWebEngineView nicht verfügbar — fallback auf Text-View: %s", e)
        return None


def _try_import_qwebchannel():
    """Try-Import-Helper für QtWebChannel."""
    try:
        from PySide6.QtWebChannel import QWebChannel  # noqa: F401
        return QWebChannel
    except ImportError as e:
        logger.warning("QWebChannel nicht verfügbar — Klicks bleiben stumm: %s", e)
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
        self._channel_cls = _try_import_qwebchannel()
        self._bridge: _CockpitBridge | None = None
        self._channel = None
        # Cycle 13 BUG-6: Debounce-Timer für _refresh_html — verhindert
        # rasche setHtml-Aufrufe die die JS-Bridge-Registrierung racy
        # machen.
        self._refresh_debounce = QTimer(self)
        self._refresh_debounce.setSingleShot(True)
        self._refresh_debounce.setInterval(150)  # 150ms debounce
        self._refresh_debounce.timeout.connect(self._do_refresh_html)
        self._build_ui()
        self._setup_webchannel()
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

    def _setup_webchannel(self) -> None:
        """QWebChannel zwischen JS und Python setupen.

        Dependencies optional: Wenn QtWebEngine oder QtWebChannel fehlen,
        wird kein Channel registriert — der JS-Code prüft auf
        `typeof QWebChannel` und bleibt stumm.
        """
        if self.web_view is None or self._channel_cls is None:
            return
        self._bridge = _CockpitBridge(self)
        self._bridge.nodeClickedFromJs.connect(self.select_node)
        try:
            self._channel = self._channel_cls(self.web_view.page())
            self._channel.registerObject("cockpitBridge", self._bridge)
            self.web_view.page().setWebChannel(self._channel)
        except Exception as exc:  # broad: Setup darf Tab nicht crashen
            logger.warning("QWebChannel-Setup failed: %s", exc)
            self._bridge = None
            self._channel = None

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
        """Cycle 13 BUG-6: leitet auf debounced refresh um. Mehrfache
        Klicks auf 'Aktualisieren' in 150ms triggern nur einen setHtml-
        Aufruf — verhindert race in der JS-QWebChannel-Reinitialisierung.
        """
        # Stats sofort aktualisieren (billig)
        stats = self._vm.stats()
        self.stats_label.setText(
            self.tr("Knoten: {n} | Kanten: {e}").format(
                n=stats["n_nodes"], e=stats["n_edges"]
            )
        )
        self.statsRefreshed.emit(stats)
        # setHtml debounced
        self._refresh_debounce.start()

    def _do_refresh_html(self) -> None:
        """Macht den eigentlichen setHtml-Aufruf nach dem Debounce."""
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

    def closeEvent(self, event):
        """Cycle 13 BUG-8: Bridge + Channel sauber freigeben um
        Memory-Leaks bei Tab-Recreate zu vermeiden."""
        try:
            if self._channel is not None and self._bridge is not None:
                try:
                    self._channel.deregisterObject(self._bridge)
                except (RuntimeError, TypeError):
                    pass
            if self._bridge is not None:
                try:
                    self._bridge.deleteLater()
                except RuntimeError:
                    pass
        except Exception as exc:  # broad: cleanup darf nicht crashen
            logger.debug("GraphCockpitTab cleanup warning: %s", exc)
        finally:
            self._bridge = None
            self._channel = None
        super().closeEvent(event)
