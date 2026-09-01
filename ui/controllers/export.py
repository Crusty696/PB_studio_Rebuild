"""ExportController — Refactored from ExportMixin."""

import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from database import get_active_project_id
from services.task_manager import TaskManagerProxy
from services.export_service import get_timeline_summary, estimate_render_time
from services.export.ffmpeg_runner import set_export_preset
from workers import ExportWorker, PreviewExportWorker
from workers.base import BaseWorker, run_worker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)
task_manager = TaskManagerProxy()


class _ProductionInfoWorker(BaseWorker):
    """FREEZE-Fix 2026-07-10: get_timeline_summary + estimate_render_time
    liefen beim EXPORT-Workspace-Wechsel SYNCHRON im Main-Thread. Bei busy DB
    (Hintergrund-Writer + busy_timeout) fror der Klick die UI 20-60s ein
    (freeze_stacks-Watchdog-Beweis: Query.all in get_all_audio). Beide
    DB-Reads laufen jetzt hier im Hintergrund-Thread.

    K8-Migration: BaseWorker-Subklasse fuer run_worker (B-513). Payload
    von ``finished``: Tupel ``(summary, estimate|None)``. Fehler werden
    wie vor der Migration intern gefangen (leere Payload statt Crash)."""

    def __init__(self, project_id, resolution: str, fps: float):
        super().__init__()
        self._project_id = project_id
        self._resolution = resolution
        self._fps = fps

    def _do_work(self):
        try:
            summary = get_timeline_summary(self._project_id)
        except Exception as e:  # noqa: BLE001 — Label-Refresh darf nie crashen
            logger.debug("ProductionInfo summary fehlgeschlagen: %s", e)
            return ({}, None)
        estimate = None
        try:
            # virt-M4-Fix: summary weiterreichen — vorher lief derselbe
            # Timeline-Scan pro EXPORT-Klick doppelt (get_timeline_summary
            # intern nochmal in estimate_render_time).
            estimate = estimate_render_time(
                self._project_id, self._resolution, self._fps, summary=summary
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Render-Schaetzung fehlgeschlagen: %s", e)
        return (summary, estimate)


class ExportController(PBComponent):
    """Export / Deliver methods for PBWindow."""

    def _set_deliver_status(self, text: str) -> None:
        """Schreibt in die Statusleiste des DELIVER-Bereichs.

        B-937: ``StatusStrip.set_status`` hatte keinen einzigen Aufrufer. Der
        Streifen zeigte deshalb dauerhaft "Export bereit, sobald eine Timeline
        vorhanden ist." — auch waehrend eines laufenden Exports, nach Erfolg
        und nach Fehlschlag. Das faellt umso schwerer ins Gewicht, weil
        ``export_log`` im PROTOKOLL-Tab haengt, der derzeit gar nicht sichtbar
        ist (B-933): die Statusleiste ist die einzige Rueckmeldung, die den
        Nutzer erreicht.
        """
        ws = getattr(self.window, "_deliver_ws", None)
        strip = getattr(ws, "deliver_status", None)
        if strip is not None:
            strip.set_status(text)

    def _update_deliver_status_from_timeline(self) -> None:
        """Setzt den Statusstreifen auf den tatsaechlichen Timeline-Stand.

        B-964: B-937 hat den Setter mit Aufrufern versehen — aber nur fuer
        Export-Vorgaenge. Beim Betreten des Bereichs blieb der Startwert aus
        ``deliver_workspace.py`` stehen. Gemessen am 2026-09-01 in zwei
        App-Sitzungen: der Streifen meldete "Export bereit, sobald eine
        Timeline vorhanden ist.", waehrend das Projekt 161 Eintraege hatte.
        """
        try:
            summary = get_timeline_summary(get_active_project_id())
            anzahl = int(summary.get("total_entries", 0))
        except Exception as e:  # noqa: BLE001 — Status darf den Wechsel nie kippen
            logger.debug("Timeline-Stand fuer den Statusstreifen nicht lesbar: %s", e)
            return
        if anzahl == 0:
            self._set_deliver_status("Export bereit, sobald eine Timeline vorhanden ist.")
        else:
            self._set_deliver_status(
                f"Timeline mit {anzahl} Eintraegen bereit. Export kann gestartet werden."
            )

    def _refresh_production_info(self):
        """Startet den async Refresh der Produktions-Infos (nicht-blockierend).

        UI-Werte (Combos) werden VOR dem Worker-Start im Main-Thread gelesen;
        die DB-Reads laufen im Worker; die Labels setzt der done-Slot (queued,
        Main-Thread). Doppelstart-Guard: laeuft bereits ein Refresh, wird der
        Klick ignoriert (der laufende liefert gleich frische Werte).
        """
        if getattr(self, "_pinfo_thread", None) is not None and self._pinfo_thread.isRunning():
            return
        try:
            resolution = self.window.resolution_combo.currentText()
            fps = float(self.window.fps_combo.currentText())
        except (AttributeError, ValueError):
            resolution, fps = "1920x1080", 30.0
        self.window.production_info.setText("Lade Produktions-Infos…")

        worker = _ProductionInfoWorker(get_active_project_id(), resolution, fps)
        # K8: run_worker (B-513) statt Hand-Verdrahtung — gleiche Signal-
        # Kette (finished->Slot queued, finished->quit, deleteLater), plus
        # destroyed-Guard am Window. Referenzen bleiben fuer den
        # Doppelstart-Guard erhalten (B-605-Lektion) und werden im Slot
        # VOR dem deleteLater genullt.
        self._pinfo_worker = worker
        self._pinfo_thread = run_worker(
            self.window, worker,
            on_finish=self._on_production_info_payload,
            on_error=self._on_production_info_error,
        )

    def _on_production_info_payload(self, payload) -> None:
        """run_worker-Adapter: Payload-Tupel -> bestehender 2-Arg-Slot."""
        summary, estimate = payload
        self._on_production_info_ready(summary, estimate)

    def _on_production_info_error(self, msg: str) -> None:
        """Sicherheitsnetz fuer unerwartete Worker-Exceptions — wie leere
        Summary behandeln (vorher: Thread blieb ohne quit haengen)."""
        logger.debug("ProductionInfo-Worker error: %s", msg)
        self._on_production_info_ready({}, None)

    def _on_production_info_ready(self, summary: dict, estimate) -> None:
        self._pinfo_worker = None
        self._pinfo_thread = None
        if not summary:
            self.window.production_info.setText("Produktions-Infos nicht verfuegbar.")
            self.window.render_estimate_label.setText("Geschaetzte Renderzeit: —")
            return
        self.window.production_info.setText(
            f"Video-Clips: {summary['video_clips']} | "
            f"Audio-Tracks: {summary['audio_tracks']} | "
            f"Gesamt-Eintraege: {summary['total_entries']} | "
            f"Geschaetzte Dauer: {summary['estimated_duration']:.1f}s"
        )
        if estimate is None:
            self.window.render_estimate_label.setText("Geschaetzte Renderzeit: —")
            return
        preset_name = self.window.preset_combo.currentText()
        self.window.render_estimate_label.setText(
            f"Geschaetzte Renderzeit: {estimate['estimated_label']} | "
            f"Dauer: {estimate['total_duration']:.1f}s | "
            f"{estimate['segment_count']} Clips | "
            f"Preset: {preset_name}"
        )

    def _update_render_estimate(self):
        """Aktualisiert die Render-Schaetzung — delegiert an den async Refresh
        (FREEZE-Fix 2026-07-10: vorher synchrone DB-Reads im Main-Thread)."""
        self._refresh_production_info()

    def _apply_export_preset(self) -> str:
        """Uebertraegt die Preset-Wahl der Combo an den Encoder.

        Die Combo war bisher eine Attrappe: der Wert landete nur im
        Renderzeit-Label, waehrend Bitrate/Qualitaet in
        ``services/export/ffmpeg_runner._video_encode_args`` hart verdrahtet
        waren ("Draft" und "Hohe Qualitaet" ergaben dieselbe Datei).

        Gesetzt wird hier im GUI-Thread VOR dem Worker-Start; der Worker liest
        den Wert beim Bauen der ffmpeg-Kommandos. Ein Durchreichen als
        Parameter (Controller -> ExportWorker -> export_timeline) wuerde
        ``workers/import_export.py`` beruehren und war fuer diese Aenderung
        nicht freigegeben.

        Returns: den effektiv gesetzten Preset-Key.
        """
        try:
            key = self.window.preset_combo.currentData()
        except AttributeError:
            key = None
        return set_export_preset(key)

    def _start_export(self):
        summary = get_timeline_summary(get_active_project_id())
        if summary["total_entries"] == 0:
            self.window.export_log.append("[Fehler] Keine Clips auf der Timeline!")
            self._set_deliver_status("Export nicht moeglich: keine Clips auf der Timeline.")
            return

        preset_key = self._apply_export_preset()

        output_name = self.window.export_name_input.text().strip() or "output.mp4"
        if not output_name.endswith(".mp4"):
            output_name += ".mp4"

        resolution = self.window.resolution_combo.currentText()
        fps = float(self.window.fps_combo.currentText())

        task = task_manager.create_task(f"Export: {output_name}", "Video-Rendering")
        self.window.btn_export.setEnabled(False)
        self.window.btn_export.setText("Exportiere...")
        self.window.export_progress.setVisible(True)
        self.window.export_progress.setRange(0, 0)
        self.window.export_log.append(
            f"[Export] Starte Export: {output_name} ({resolution} @ {fps}fps, "
            f"Preset: {preset_key})"
        )
        self._set_deliver_status(
            f"Export laeuft: {output_name} ({resolution} @ {fps}fps, Preset: {preset_key})"
        )

        # B-580: Warnungen dieses Laufs sammeln (pro Export zuruecksetzen).
        self._export_warnings: list[str] = []
        worker = ExportWorker(project_id=get_active_project_id(), output_name=output_name,
                              resolution=resolution, fps=fps)
        worker.task_id = task.task_id
        worker.progress.connect(self._on_export_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(
            lambda p: self._on_export_finished(p, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda err: self._on_export_error(err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.warning.connect(
            self._on_export_warning, Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_export_progress(self, pct: int, message: str):
        self.window.export_progress.setRange(0, 100)
        self.window.export_progress.setValue(pct)
        self.window.export_log.append(f"[Export] {message} ({pct}%)")
        self._set_deliver_status(f"Export {pct}%: {message}")

    def _on_export_warning(self, message: str):
        """B-580: Export laeuft weiter, der User erfaehrt es aber.

        Bisher stand der Verlust nur im Logfile — der Export meldete
        Erfolg und lieferte still ein kuerzeres Video.
        """
        if not hasattr(self, "_export_warnings"):
            self._export_warnings = []
        self._export_warnings.append(message)
        self.window.export_log.append(f"[WARNUNG] {message}")
        self.window.console_text.append(f"[Export-Warnung] {message}")

    def _on_export_finished(self, output_path: str, task_id: str = ""):
        self.window.btn_export.setEnabled(True)
        self.window.btn_export.setText("Video exportieren")
        self.window.export_progress.setVisible(False)
        if not output_path:
            task = task_manager.get_task(task_id) if task_id else None
            if task is not None and task.status == "cancelled":
                return
            if task_id:
                task_manager.finish_task(task_id, "error", "Leerer Export-Pfad")
            self._set_deliver_status("Export fehlgeschlagen: leerer Ausgabepfad.")
            return
        self.window.export_log.append(f"[Export] FERTIG: {output_path}")
        self.window.console_text.append(f"[Export] Video exportiert: {output_path}")
        # B-580: "fertig" darf einen Materialverlust nicht ueberdecken.
        if getattr(self, "_export_warnings", None):
            _warn_text = "\n".join(f"- {w}" for w in self._export_warnings)
            self.window.status_bar.showMessage(
                f"Export fertig MIT WARNUNGEN: {output_path}"
            )
            self._set_deliver_status(
                f"Export fertig, aber unvollstaendig ({len(self._export_warnings)} "
                f"Warnung(en)): {output_path}"
            )
            QMessageBox.warning(
                self.window,
                "Export mit Materialverlust abgeschlossen",
                f"Der Export wurde erstellt, aber nicht vollstaendig:\n\n"
                f"{_warn_text}\n\nDatei: {output_path}",
            )
        else:
            self.window.status_bar.showMessage(f"Export fertig: {output_path}")
            self._set_deliver_status(f"Export fertig: {output_path}")
        if task_id:
            task_manager.finish_task(task_id, "finished", output_path)

    def _on_export_error(self, error_msg: str, task_id: str = ""):
        self.window.btn_export.setEnabled(True)
        self.window.btn_export.setText("Video exportieren")
        self.window.export_progress.setVisible(False)
        self.window.export_log.append(f"[FEHLER] Export fehlgeschlagen: {error_msg}")
        self._set_deliver_status(f"Export fehlgeschlagen: {error_msg}")
        self.window.console_text.append(f"[Fehler] Export: {error_msg}")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    def _start_preview_export(self):
        """Rendert die ersten 10 Sekunden der Timeline als Vorschau."""
        summary = get_timeline_summary(get_active_project_id())
        if summary["total_entries"] == 0:
            self.window.export_log.append("[Preview] Keine Clips auf der Timeline!")
            self._set_deliver_status("Vorschau nicht moeglich: keine Clips auf der Timeline.")
            return

        resolution = self.window.resolution_combo.currentText()
        fps = float(self.window.fps_combo.currentText())
        self._apply_export_preset()

        self.window.btn_preview.setEnabled(False)
        self.window.btn_preview.setText("Rendere Vorschau...")
        self.window.export_progress.setVisible(True)
        self.window.export_progress.setRange(0, 0)
        self.window.export_log.append(
            f"[Preview] Starte Quick-Preview (10s) — {resolution} @ {fps}fps"
        )
        self._set_deliver_status(
            f"Vorschau wird gerendert (10s) — {resolution} @ {fps}fps"
        )

        worker = PreviewExportWorker(
            project_id=get_active_project_id(),
            resolution=resolution,
            fps=fps,
            duration_limit=10.0,
        )
        worker.progress.connect(self._on_preview_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._on_preview_finished, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._on_preview_error, Qt.ConnectionType.QueuedConnection)
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_preview_progress(self, pct: int, message: str):
        self.window.export_progress.setRange(0, 100)
        self.window.export_progress.setValue(pct)
        self._set_deliver_status(f"Vorschau {pct}%: {message}")

    def _on_preview_finished(self, preview_path: str):
        self.window.btn_preview.setEnabled(True)
        self.window.btn_preview.setText("Quick-Preview (10s)")
        self.window.export_progress.setVisible(False)

        if not preview_path:
            self.window.export_log.append("[Preview] Vorschau fehlgeschlagen (leerer Pfad)")
            self._set_deliver_status("Vorschau fehlgeschlagen: leerer Ausgabepfad.")
            return

        self.window.export_log.append(f"[Preview] Vorschau fertig: {preview_path}")
        self.window.console_text.append(f"[Preview] Vorschau gerendert: {preview_path}")
        self._set_deliver_status(f"Vorschau fertig: {preview_path}")

        from pathlib import Path
        if Path(preview_path).exists():
            self.window._preview_path = preview_path
            _ws = self.window._deliver_ws
            _ws.preview_video_label.setStyleSheet(
                "background-color: #1a1a2e; color: #22c55e; "
                "border: 1px solid #22c55e; border-radius: 4px;"
            )
            _ws.btn_preview_play.setEnabled(True)
            _ws.btn_preview_stop.setEnabled(True)
            # B-922: Die Vorschau wird jetzt in die Flaeche des DELIVER-Tabs
            # geladen, nicht mehr nur in den Player des SCHNITT-Tabs. Vorher
            # startete "Play" die Wiedergabe in einem anderen Workspace,
            # waehrend hier "Vorschau geladen" und 0:00 / 0:00 stehen blieben.
            _ws.preview_video_label.load_video(preview_path, 10.0)
            self._verbinde_deliver_preview_signale()
            # B-945: Hier wurde dieselbe Datei zusaetzlich in
            # ``window.video_preview`` geladen — den Player im SCHNITT-Tab.
            # Das startete eine zweite ffmpeg-Extraktion und ersetzte dort die
            # Timeline-Vorschau durch das Export-Video. Seit B-922 hat der
            # DELIVER-Tab seinen eigenen Player; der Zweitaufruf ist damit
            # doppelte Arbeit mit unerwuenschter Nebenwirkung.
            self.window.export_log.append("[Preview] Video-Player geladen — druecke Play")
        else:
            self.window.export_log.append("[Preview] Vorschau-Datei nicht gefunden")
            self._set_deliver_status("Vorschau fertig gemeldet, Datei aber nicht gefunden.")

    def _on_preview_error(self, error_msg: str):
        self.window.btn_preview.setEnabled(True)
        self.window.btn_preview.setText("Quick-Preview (10s)")
        self.window.export_progress.setVisible(False)
        self.window.export_log.append(f"[FEHLER] Vorschau fehlgeschlagen: {error_msg}")
        self._set_deliver_status(f"Vorschau fehlgeschlagen: {error_msg}")
        self.window.console_text.append(f"[Fehler] Preview: {error_msg}")

    def _deliver_preview_widget(self):
        """Die Abspielflaeche im DELIVER-Tab (seit B-922 ein echter Player)."""
        ws = getattr(self.window, "_deliver_ws", None)
        widget = getattr(ws, "preview_video_label", None)
        return widget if hasattr(widget, "play_from") else None

    def _verbinde_deliver_preview_signale(self):
        """Haengt die Zeitanzeige des DELIVER-Tabs an den dortigen Player.

        Einmalig — ``_on_preview_finished`` laeuft nach jedem Rendern.
        """
        if getattr(self, "_deliver_preview_verbunden", False):
            return
        widget = self._deliver_preview_widget()
        if widget is None:
            return

        def _fmt(sekunden: float) -> str:
            sekunden = max(0.0, float(sekunden))
            return f"{int(sekunden // 60)}:{int(sekunden % 60):02d}"

        def _zeige(aktuell: float, gesamt: float) -> None:
            label = getattr(self.window._deliver_ws, "preview_time_label", None)
            if label is not None:
                label.setText(f"{_fmt(aktuell)} / {_fmt(gesamt)}")

        widget.position_changed.connect(_zeige, Qt.ConnectionType.QueuedConnection)
        self._deliver_preview_verbunden = True

    def _play_preview(self):
        """Spielt die gerenderte Vorschau im DELIVER-Tab ab."""
        from pathlib import Path

        pfad = getattr(self.window, "_preview_path", "")
        if not pfad or not Path(pfad).exists():
            self._set_deliver_status("Keine gerenderte Vorschau vorhanden.")
            return

        widget = self._deliver_preview_widget()
        if widget is None:
            # Faellt auf den SCHNITT-Player zurueck, statt gar nichts zu tun.
            if hasattr(self.window, "video_preview"):
                self.window.video_preview.load_video(pfad, 10.0)
                self.window.video_preview.play_from(0.0)
            return

        self._verbinde_deliver_preview_signale()
        widget.load_video(pfad, 10.0)
        widget.play_from(0.0)

    def _stop_preview(self):
        """Stoppt die Vorschau-Wiedergabe."""
        widget = self._deliver_preview_widget()
        if widget is not None:
            widget.stop()
        if hasattr(self.window, 'video_preview'):
            self.window.video_preview.stop()
