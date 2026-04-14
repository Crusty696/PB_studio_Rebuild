"""ProjectManagementController — Refactored from ProjectManagementMixin."""

import logging
from pathlib import Path
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

APP_VERSION_PLACEHOLDER = "0.5.0"

class ProjectManagementController(PBComponent):
    """Controller for Project Management and Dialogs in PBWindow."""

    def _new_project(self):
        """Show NewProjectDialog and create a new project (Fix F-045: Async)."""
        from ui.dialogs.project_dialog import NewProjectDialog
        dlg = NewProjectDialog(self.window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        
        from PySide6.QtCore import QObject, Signal
        class CreateWorker(QObject):
            finished = Signal(object)
            error = Signal(str)
            def run(self):
                try:
                    from services.task_manager import GlobalTaskManager
                    # Safety check
                    tm = GlobalTaskManager.instance()
                    if any(t.status == "running" for t in tm.get_all_tasks() if "Datenbank" not in t.name):
                        raise RuntimeError("Hintergrund-Tasks laufen noch.")
                    
                    path = self.manager.create_project(
                        path=vals["path"], name=vals["name"],
                        resolution=vals["resolution"], fps=vals["fps"]
                    )
                    self.finished.emit(path)
                except Exception as e:
                    self.error.emit(str(e))

        worker = CreateWorker()
        worker.manager = self.window._project_manager
        
        def _on_done(path):
            # H-41 fix: Check window still exists before accessing
            if not self.window or not hasattr(self.window, 'panel_setup'):
                logger.debug("Window destroyed before CreateWorker finished, skipping UI update")
                return
            self._mark_clean()
            self.window.panel_setup._console_append(f"[Projekt] Neues Projekt erstellt: {vals['name']}")
            self.window.status_bar.showMessage(f"Projekt erstellt: {vals['name']}")

        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Projekt erstellen",
            worker=worker,
            on_finish=_on_done,
            description=f"Initialisiere '{vals['name']}'"
        )

    def _open_project(self):
        """Show OpenProjectDialog and open an existing project (Fix F-045: Async)."""
        from ui.dialogs.project_dialog import OpenProjectDialog
        dlg = OpenProjectDialog(self.window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        path = dlg.get_path()

        from PySide6.QtCore import QObject, Signal
        class OpenWorker(QObject):
            finished = Signal(dict)
            error = Signal(str)
            def run(self):
                try:
                    meta = self.manager.open_project(path)
                    self.finished.emit(meta)
                except Exception as e:
                    self.error.emit(str(e))

        worker = OpenWorker()
        worker.manager = self.window._project_manager

        def _on_done(meta):
            # H-41 fix: Check window still exists before accessing
            if not self.window or not hasattr(self.window, 'panel_setup'):
                logger.debug("Window destroyed before OpenWorker finished, skipping UI update")
                return
            self._mark_clean()
            self.window.panel_setup._console_append(f"[Projekt] Geoeffnet: {meta.get('name', path.name)}")
            self.window.status_bar.showMessage(f"Projekt geladen: {meta.get('name')}")

        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Projekt laden",
            worker=worker,
            on_finish=_on_done,
            description=f"Lade '{path.name}'"
        )

    def _save_project_as(self):
        """Save the current project to a new location (Fix F-045: Async)."""
        folder = QFileDialog.getExistingDirectory(self.window, "Zielordner waehlen")
        if not folder:
            return
        name, ok = QInputDialog.getText(self.window, "Projektname", "Name fuer das neue Projekt:")
        if not ok or not name.strip():
            return
        target = Path(folder) / name.strip()

        from PySide6.QtCore import QObject, Signal
        class SaveAsWorker(QObject):
            finished = Signal(object)
            error = Signal(str)
            def run(self):
                try:
                    path = self.manager.save_project_as(target)
                    self.finished.emit(path)
                except Exception as e:
                    self.error.emit(str(e))

        worker = SaveAsWorker()
        worker.manager = self.window._project_manager

        def _on_done(path):
            # H-41 fix: Check window still exists before accessing
            if not self.window or not hasattr(self.window, 'panel_setup'):
                logger.debug("Window destroyed before SaveAsWorker finished, skipping UI update")
                return
            self._mark_clean()
            self.window.panel_setup._console_append(f"[Projekt] Gespeichert unter: {path}")
            self.window.status_bar.showMessage(f"Projekt gespeichert: {path.name}")

        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Projekt kopieren",
            worker=worker,
            on_finish=_on_done,
            description=f"Speichere Kopie in {target.name}"
        )

    def _on_project_changed(self, path):
        """Refresh all UI after a project switch."""
        path = Path(path)
        # AUD-106: Record in recent projects list
        try:
            from services.recent_projects import RecentProjectsManager
            RecentProjectsManager.add(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not update recent projects: %s", exc)
        project_name = path.name
        self.window._project_name_label.setText(project_name)
        self._update_window_title()  # AUD-108: respects dirty flag
        self.window.media_table_controller._refresh_media_table()
        self.window.media_table_controller._refresh_director_combos()
        try:
            self.window.timeline_view.load_from_db()
        except (OSError, RuntimeError, ValueError) as e:
            logging.warning("Timeline-Reload nach Projektwechsel fehlgeschlagen: %s", e)
            self.window.console_text.append(f"[Warnung] Timeline konnte nicht geladen werden: {e}")
        self.window.status_bar.showMessage(f"Projekt: {project_name}  |  {path}")

    def _show_about(self):
        from ui.dialogs.about import AboutDialog
        app_version = getattr(self.window, "_app_version", APP_VERSION_PLACEHOLDER)
        dialog = AboutDialog(version=app_version, parent=self.window)
        dialog.exec()

    def _show_shortcut_help(self):
        """AUD-105: Show keyboard shortcut help overlay (F1 / Ctrl+?)."""
        from ui.dialogs.shortcut_help_dialog import ShortcutHelpDialog
        dlg = ShortcutHelpDialog(parent=self.window)
        dlg.exec()

    def _show_settings(self):
        """Oeffnet den Einstellungs-Dialog und wendet Aenderungen sofort an."""
        from ui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(parent=self.window)
        dlg.ollama_settings_changed.connect(self._apply_ollama_settings)
        dlg.exec()

    def _apply_ollama_settings(self, enabled: bool, url: str, model: str):
        """Apply changed Ollama settings to running services."""
        logger.info(
            "Ollama settings applied — enabled=%s, url=%s, model=%s",
            enabled, url, model,
        )
        if enabled:
            from services.ollama_client import get_ollama_client
            get_ollama_client(base_url=url)
        status = "aktiviert" if enabled else "deaktiviert"
        self.window.status_bar.showMessage(
            f"Ollama {status} | URL: {url} | Modell: {model}"
        )

    def _mark_dirty(self):
        """Mark the session as having unsaved changes."""
        if not self.window._dirty:
            self.window._dirty = True
            self._update_window_title()

    def _mark_clean(self):
        """Mark the session as saved (no pending changes)."""
        if self.window._dirty:
            self.window._dirty = False
            self._update_window_title()

    def _update_window_title(self):
        """Rebuild the window title, appending '*' when dirty."""
        import database.session as _session
        app_version = getattr(self.window, "_app_version", "0.5.0")
        if _session.APP_ROOT:
            project_name = Path(_session.APP_ROOT).name
            title = f"PB_studio v{app_version} — {project_name}"
        else:
            title = f"PB_studio v{app_version} — Director's Cockpit"
        if getattr(self.window, "_dirty", False):
            title += " *"
        self.window.setWindowTitle(title)
