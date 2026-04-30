"""STEMS Workspace — DAW-Style 4-Track Stem View mit Wellenformen.

Haupt-Container und Koordinator. Sub-Widgets:
- StemTrackWidget  (stem_track_widget.py) — Track-Band mit Waveform + Mixer
- StemMixerPanel   (stem_mixer_panel.py)  — Volume/Mute/Solo Controls
- TransportBar     (stem_transport.py)    — Play/Pause/Stop/Seek/Zoom

Performance: Aggressives Downsampling für 1h+ DJ-Mixes.
Peak-Daten werden in einem Worker-Thread berechnet und gecacht.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import shiboken6
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollBar, QFrame,
)

from .stem_track_widget import StemTrackWidget, PeakWorker, WaveformWidget  # noqa: F401 (re-exported)
from .stem_mixer_panel import StemMixerPanel  # noqa: F401 (re-exported)
from .stem_transport import TransportBar  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)

# ── Stem-Konfiguration ──
STEM_CONFIG = {
    "vocals": {"color": "#E91E63", "label": "VOCALS"},
    "drums":  {"color": "#FF9800", "label": "DRUMS"},
    "bass":   {"color": "#00E676", "label": "BASS"},
    "other":  {"color": "#42A5F5", "label": "OTHER"},
}
STEM_ORDER = ["vocals", "drums", "bass", "other"]


# =====================================================================
# Haupt-Widget: StemWorkspace
# =====================================================================

class StemWorkspace(QWidget):
    """Kompletter STEMS Workspace mit 4 Track-Bändern und Transport.

    Signals (zum Verbinden mit StemPlayer):
        stem_volume_changed(stem_name, value)
        stem_mute_toggled(stem_name, is_muted)
        play_requested()
        pause_requested()
        stop_requested()
        seek_requested(float)  — Sekunden
    """

    stem_volume_changed = Signal(str, int)
    stem_mute_toggled = Signal(str, bool)
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._is_being_destroyed = False  # M1-FIX: Flag fuer endgueltiges Destroy
        self.setObjectName("stem_workspace")
        self.setAccessibleName("STEMS Workspace")
        self.setWhatsThis(
            "Der STEMS Workspace zeigt die vier separierten Audio-Spuren (Vocals, Drums, Bass, Other) "
            "als Wellenform-Bander an. Jede Spur kann individuell abgespielt, stummgeschaltet oder "
            "solo gehort werden. Der Transport-Bereich unten steuert die globale Wiedergabe und "
            "den Zoom der Wellenform-Ansicht."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(36)
        header.setObjectName("stem_workspace_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("STEM TRACKS")
        title.setStyleSheet(
            "color: #A0A0A0; font-weight: 700; font-size: 13px; "
            "background: transparent; border: none;"
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._info_label = QLabel("Kein Track geladen")
        self._info_label.setStyleSheet(
            "color: #505050; font-size: 11px; background: transparent; border: none;"
        )
        header_layout.addWidget(self._info_label)

        header_layout.addSpacing(16)

        btn_reset = QPushButton("Reset All")
        btn_reset.setFixedHeight(24)
        btn_reset.setStyleSheet(
            "QPushButton { background: #1E1E1E; color: #606060; border: 1px solid #2E2E2E; "
            "border-radius: 3px; font-size: 10px; padding: 2px 10px; }"
            "QPushButton:hover { color: #B0B0B0; border-color: #484848; }"
        )
        btn_reset.setAccessibleName("Alle Stems zuruecksetzen")
        btn_reset.setToolTip(
            "Alle Stem-Lautstaerken, Mute- und Solo-Schalter auf Standard zuruecksetzen."
        )
        btn_reset.setStatusTip("Alle Stem-Lautstaerke, Mute und Solo auf Standard zuruecksetzen")
        btn_reset.clicked.connect(self._reset_all)
        header_layout.addWidget(btn_reset)

        layout.addWidget(header)

        # Trennlinie
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #222222;")
        layout.addWidget(sep)

        # ── 4 Track-Bänder ──
        tracks_container = QWidget()
        tracks_layout = QVBoxLayout(tracks_container)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.setSpacing(0)

        self._tracks: dict[str, StemTrackWidget] = {}
        for name in STEM_ORDER:
            cfg = STEM_CONFIG[name]
            track = StemTrackWidget(name, cfg["color"], cfg["label"], self)
            track.volume_changed.connect(self.stem_volume_changed)
            track.mute_toggled.connect(self._on_mute_toggled)
            track.seek_requested.connect(self._on_waveform_seek)
            track.solo_btn.toggled.connect(
                lambda checked, n=name: self._on_solo_toggled(n, checked)
            )
            tracks_layout.addWidget(track, stretch=1)
            self._tracks[name] = track

        layout.addWidget(tracks_container, stretch=1)

        # ── Horizontal Scrollbar ──
        self._h_scroll = QScrollBar(Qt.Orientation.Horizontal)
        self._h_scroll.setRange(0, 0)
        self._h_scroll.setFixedHeight(14)
        self._h_scroll.setStyleSheet(
            "QScrollBar:horizontal { background: #121212; height: 14px; margin: 0; }"
            "QScrollBar::handle:horizontal { background: #303030; min-width: 30px; "
            "border-radius: 3px; margin: 2px; }"
            "QScrollBar::handle:horizontal:hover { background: #484848; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )
        self._h_scroll.valueChanged.connect(self._on_scroll)
        layout.addWidget(self._h_scroll)

        # ── Transport Bar ──
        self._transport = TransportBar(self)
        self._transport.play_requested.connect(self.play_requested)
        self._transport.pause_requested.connect(self.pause_requested)
        self._transport.stop_requested.connect(self.stop_requested)
        self._transport.seek_requested.connect(self.seek_requested)
        self._transport.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        layout.addWidget(self._transport)

        # ── State ──
        self._duration: float = 0.0
        self._current_track_id: int | None = None
        self._peak_threads: list[QThread] = []
        self._peak_workers: list[PeakWorker] = []
        # B-602 Fix: Lock für Thread-Safe Access auf Peak-Thread-Listen
        self._peak_lock = threading.Lock()
        self._solo_active: set[str] = set()
        self._pre_solo_mute_state: dict[str, bool] = {}

    # ── Public API ──

    def update_for_track(self, track_id: int | None,
                         stem_paths: dict[str, str | None] | None = None):
        """Aktualisiert alle 4 Tracks für einen neuen AudioTrack."""
        self._current_track_id = track_id
        self._cleanup_peak_threads()

        if track_id is None or stem_paths is None:
            self._info_label.setText("Kein Track geladen")
            for track in self._tracks.values():
                track.set_enabled_state(False)
            return

        available = {k: v for k, v in stem_paths.items() if v and Path(v).exists()}
        if not available:
            self._info_label.setText("Keine Stems vorhanden")
            for track in self._tracks.values():
                track.set_enabled_state(False)
            return

        self._info_label.setText(f"Track #{track_id} — {len(available)}/4 Stems")

        for name, track in self._tracks.items():
            if name in available:
                track.set_enabled_state(True)
                track.waveform.set_loading(True)
                self._start_peak_generation(name, available[name])
            else:
                track.set_enabled_state(False)

    def set_duration(self, duration: float):
        """Setzt die Track-Dauer für Transport und Waveforms."""
        self._duration = duration
        self._transport.set_duration(duration)

    def update_position(self, seconds: float):
        """Aktualisiert Playhead-Position in allen Waveforms und Transport."""
        self._transport.update_position(seconds)
        if self._duration > 0:
            ratio = seconds / self._duration
            for track in self._tracks.values():
                track.waveform.set_playhead(ratio)

    def update_playback_state(self, state: str):
        """Aktualisiert Play-Button basierend auf Player-State."""
        self._transport.update_playback_state(state)

    @property
    def current_track_id(self) -> int | None:
        return self._current_track_id

    # ── Interne Logik ──

    def _start_peak_generation(self, stem_name: str, file_path: str):
        """Startet Peak-Berechnung in einem Worker-Thread."""
        thread = QThread()
        worker = PeakWorker(stem_name, file_path)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_peaks_ready)
        worker.error.connect(self._on_peaks_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        # GC-FIX: Starke Referenzen halten bis thread wirklich fertig ist.
        # _remove_finished_thread() wird via finished-Signal aufgerufen —
        # erst dann werden die Python-Wrapper-Objekte freigegeben.
        # (verhindert "Internal C++ object already deleted" wenn quit() async läuft)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._remove_finished_thread(t, w))

        # B-602 Fix: Thread-Safe Zugriff auf Listen mit Lock
        with self._peak_lock:
            self._peak_threads.append(thread)
            self._peak_workers.append(worker)

        thread.start()

    def _remove_finished_thread(self, thread: QThread, worker: "PeakWorker"):
        """Entfernt einen fertigen Thread/Worker aus den Tracking-Listen.

        Wird via thread.finished aufgerufen — zu diesem Zeitpunkt ist der
        C++ QThread noch gültig (deleteLater steht erst in der Queue).
        """
        # B-602 Fix: Thread-Safe Zugriff auf Listen mit Lock
        with self._peak_lock:
            try:
                self._peak_threads.remove(thread)
            except ValueError as exc:
                logger.warning("_remove_finished_thread: thread not in list: %s", exc)
            try:
                self._peak_workers.remove(worker)
            except ValueError as exc:
                logger.warning("_remove_finished_thread: worker not in list: %s", exc)

    def _on_peaks_ready(self, stem_name: str, peaks: np.ndarray):
        """Callback wenn Peak-Daten fertig sind."""
        if stem_name in self._tracks:
            self._tracks[stem_name].waveform.set_peaks(peaks)

    def _on_peaks_error(self, stem_name: str, error_msg: str):
        """Callback bei Fehler in der Peak-Berechnung."""
        logger.warning("[StemWorkspace] Peak-Fehler bei %s: %s", stem_name, error_msg)
        if stem_name in self._tracks:
            self._tracks[stem_name].waveform.set_loading(False)

    def _cleanup_peak_threads(self):
        """Beendet laufende Peak-Threads.

        GC-FIX: KEIN clear() der Listen hier — Python würde sonst die
        Wrapper-Objekte sofort freigeben, während der C++ QThread noch läuft.
        Stattdessen: cancel + quit, und _remove_finished_thread() räumt
        die Listen auf sobald das thread.finished-Signal eintrifft.
        """
        # B-602 Fix: Thread-Safe Zugriff auf Listen mit Lock
        with self._peak_lock:
            workers_to_cancel = list(self._peak_workers)
            threads_to_quit = list(self._peak_threads)

        for worker in workers_to_cancel:
            try:
                if shiboken6.isValid(worker):
                    worker.cancel()
                else:
                    with self._peak_lock:
                        try:
                            self._peak_workers.remove(worker)
                        except ValueError:
                            pass
            except RuntimeError:
                with self._peak_lock:
                    try:
                        self._peak_workers.remove(worker)
                    except ValueError:
                        pass
        for thread in threads_to_quit:
            try:
                if shiboken6.isValid(thread) and thread.isRunning():
                    thread.quit()
                elif not shiboken6.isValid(thread):
                    with self._peak_lock:
                        try:
                            self._peak_threads.remove(thread)
                        except ValueError:
                            pass
            except RuntimeError:
                with self._peak_lock:
                    try:
                        self._peak_threads.remove(thread)
                    except ValueError:
                        pass

    def _on_mute_toggled(self, stem_name: str, muted: bool):
        """Mute-Signal weiterleiten."""
        self.stem_mute_toggled.emit(stem_name, muted)

    def _on_solo_toggled(self, stem_name: str, checked: bool):
        """Solo-Logik: Nur der Solo-Track ist hörbar, alle anderen muted.

        Speichert den vorherigen Mute-Zustand beim Aktivieren von Solo und
        stellt ihn beim Deaktivieren wieder her. Die Mute-Buttons werden
        visuell aktualisiert, damit der Zustand sichtbar ist.

        Performance: Sammelt alle Mute-Aenderungen und emittiert sie gebuendelt,
        statt 4 einzelne Signal-Emits (4x Lock im Audio-Thread).
        """
        if checked:
            if not self._solo_active:
                self._pre_solo_mute_state = {
                    name: track.is_muted for name, track in self._tracks.items()
                }
            self._solo_active.add(stem_name)
        else:
            self._solo_active.discard(stem_name)

        # Alle Mute-States sammeln, Buttons batched aktualisieren
        mute_updates: list[tuple[str, bool]] = []

        if self._solo_active:
            for name, track in self._tracks.items():
                should_mute = name not in self._solo_active
                track._mute_btn.blockSignals(True)
                try:
                    track._mute_btn.setChecked(should_mute)
                finally:
                    track._mute_btn.blockSignals(False)
                mute_updates.append((name, should_mute))
        else:
            pre_state = getattr(self, '_pre_solo_mute_state', {})
            for name, track in self._tracks.items():
                was_muted = pre_state.get(name, False)
                track._mute_btn.blockSignals(True)
                try:
                    track._mute_btn.setChecked(was_muted)
                finally:
                    track._mute_btn.blockSignals(False)
                mute_updates.append((name, was_muted))

        # Gebuendelt emittieren — StemPlayer.set_mute() nimmt den Lock nur 4x
        # statt interleaved mit UI-Repaints
        for name, muted in mute_updates:
            self.stem_mute_toggled.emit(name, muted)

    def _on_waveform_seek(self, ratio: float):
        """Klick in eine Waveform → Seek in Sekunden."""
        if self._duration > 0:
            self.seek_requested.emit(ratio * self._duration)

    def _on_zoom_changed(self, value: int):
        """Zoom-Slider geändert → alle Waveforms aktualisieren."""
        zoom = value / 10.0
        self._transport.zoom_label.setText(f"{zoom:.1f}x")

        for track in self._tracks.values():
            track.waveform.set_zoom(zoom)

        # Scrollbar-Range anpassen
        if zoom > 1.0:
            max_scroll = int((1.0 - 1.0 / zoom) * 10000)
            self._h_scroll.setRange(0, max_scroll)
            self._h_scroll.setPageStep(int(10000 / zoom))
        else:
            self._h_scroll.setRange(0, 0)

    def _on_scroll(self, value: int):
        """Scrollbar geändert → alle Waveforms scrollen."""
        max_val = self._h_scroll.maximum()
        if max_val > 0:
            offset = value / max_val
        else:
            offset = 0.0
        for track in self._tracks.values():
            track.waveform.set_scroll(offset)

    def _reset_all(self):
        """Alle Tracks zurücksetzen."""
        self._solo_active.clear()
        for track in self._tracks.values():
            track.reset()

    def closeEvent(self, event):
        """Cleanup beim Schliessen der StemWorkspace — Bug #26 Fix.

        M1-FIX: Nur beim endgueltigen Destroy (nicht bei Tab-/Workspace-Wechsel)
        Signale disconnecten. ``event.spontaneous()`` ist True bei Fenster-Close
        durch den Window-Manager, aber bei programmatischem hide/show ist es False.
        Stattdessen pruefen wir, ob das Widget tatsaechlich zerstoert wird
        (d.h. nicht nur versteckt).
        """
        if not self._is_being_destroyed:
            # Nur versteckt (z.B. Tab-Wechsel) — Signale intakt lassen
            super().closeEvent(event)
            return

        # Endgueltiger Destroy — Signale und Threads aufraeumen
        try:
            self.stem_volume_changed.disconnect()
            self.stem_mute_toggled.disconnect()
            self.play_requested.disconnect()
            self.pause_requested.disconnect()
            self.stop_requested.disconnect()
            self.seek_requested.disconnect()
        except (TypeError, RuntimeError) as exc:
            logger.warning("StemWorkspace.closeEvent: failed to disconnect signals: %s", exc)

        # Cleanup Peak Worker threads
        try:
            if hasattr(self, '_peak_threads'):
                for thread in self._peak_threads:
                    if shiboken6.isValid(thread) and thread.isRunning():
                        thread.quit()
                        thread.wait(1000)
        except (TypeError, RuntimeError) as exc:
            logger.warning("StemWorkspace.closeEvent: failed to cleanup peak threads: %s", exc)

        super().closeEvent(event)

    def destroy_workspace(self):
        """Explizit aufrufen wenn das Widget endgueltig zerstoert werden soll."""
        self._is_being_destroyed = True
        self.close()
