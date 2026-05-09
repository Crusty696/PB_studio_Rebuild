"""ProjectManagementController — Refactored from ProjectManagementMixin.

Cycle 14 / Option B: Inline-Workers migriert auf workers.base.BaseWorker.
Vorher 3 ad-hoc QObject-Subklassen mit eigener finished/error-Signal-
Definition + try/except-Pattern. Jetzt: BaseWorker-Subklassen die nur
``_do_work()`` überschreiben — error-Handling + format_user_error() im
BaseWorker zentral.

B-050: Alle drei Project-Worker bekommen jetzt einen ``on_error``-
Handler der dem User einen Status-Bar-Toast + QMessageBox zeigt.
Vorher: Worker raised → Task=error im Dock, aber NULL UI-Feedback —
User dachte "nichts passiert ist".
"""

import logging
from pathlib import Path
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox
from ui.base_component import PBComponent
from workers.base import BaseWorker

logger = logging.getLogger(__name__)

APP_VERSION_PLACEHOLDER = "0.5.0"

class ProjectManagementController(PBComponent):
    """Controller for Project Management and Dialogs in PBWindow."""

    def _make_project_error_handler(self, prefix: str):
        """B-050: Wiederverwendbarer ``on_error``-Handler fuer alle drei
        Project-Worker (CreateWorker, OpenWorker, SaveAsWorker). Zeigt
        Status-Bar + Critical-MessageBox damit der User nicht im Dunkeln
        steht.
        """
        def _on_error(err_msg: str) -> None:
            if not self.window:
                return
            full_msg = f"{prefix}: {err_msg}"
            try:
                if hasattr(self.window, "status_bar"):
                    self.window.status_bar.showMessage(full_msg, 10_000)
            except Exception:  # broad: status-bar darf den Dialog nicht blocken
                pass
            try:
                QMessageBox.critical(self.window, prefix, err_msg)
            except Exception as exc:  # broad: best-effort
                logger.warning("B-050: error-dialog failed: %s", exc)
            logger.error("B-050 %s: %s", prefix, err_msg)
        return _on_error

    def _new_project(self):
        """Show NewProjectDialog and create a new project (Fix F-045: Async)."""
        from ui.dialogs.project_dialog import NewProjectDialog
        dlg = NewProjectDialog(self.window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        
        class CreateWorker(BaseWorker):
            def __init__(self, manager, vals):
                super().__init__()
                self.manager = manager
                self.vals = vals

            def _do_work(self):
                from services.task_manager import GlobalTaskManager
                tm = GlobalTaskManager.instance()
                # Safety check (zusätzlich zum project_manager-internen Check)
                if any(
                    t.status == "running"
                    for t in tm.get_all_tasks()
                    if "Datenbank" not in t.name and t.task_id != self.task_id
                ):
                    raise RuntimeError("Hintergrund-Tasks laufen noch.")
                return self.manager.create_project(
                    path=self.vals["path"], name=self.vals["name"],
                    resolution=self.vals["resolution"], fps=self.vals["fps"],
                    task_id=self.task_id,  # B-047 Cycle 13
                )

        worker = CreateWorker(self.window._project_manager, vals)
        
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
            on_error=self._make_project_error_handler("Projekt-Erstellung fehlgeschlagen"),
            description=f"Initialisiere '{vals['name']}'"
        )

    def _open_project(self):
        """Show OpenProjectDialog and open an existing project (Fix F-045: Async)."""
        from ui.dialogs.project_dialog import OpenProjectDialog
        dlg = OpenProjectDialog(self.window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        path = dlg.get_path()

        class OpenWorker(BaseWorker):
            def __init__(self, manager, target_path):
                super().__init__()
                self.manager = manager
                self.target_path = target_path

            def _do_work(self):
                return self.manager.open_project(
                    self.target_path,
                    task_id=self.task_id,
                )

        worker = OpenWorker(self.window._project_manager, path)

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
            on_error=self._make_project_error_handler("Projekt-Laden fehlgeschlagen"),
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

        class SaveAsWorker(BaseWorker):
            def __init__(self, manager, target_path):
                super().__init__()
                self.manager = manager
                self.target_path = target_path

            def _do_work(self):
                return self.manager.save_project_as(
                    self.target_path,
                    task_id=self.task_id,
                )

        worker = SaveAsWorker(self.window._project_manager, target)

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
            on_error=self._make_project_error_handler("Projekt-Kopie fehlgeschlagen"),
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
        if hasattr(self.window, "_save_state_label"):
            self.window._save_state_label.setText("gespeichert")
            self.window._save_state_label.setStyleSheet("color: #6b7280; font-size: 10px; background: transparent;")
        try:
            dashboard = getattr(self.window, "_project_dashboard", None)
            if dashboard is not None:
                dashboard.update_project(project_name, str(path))
        except Exception as exc:
            logger.debug("Project dashboard update failed: %s", exc)
        self._update_window_title()  # AUD-108: respects dirty flag
        self.window.media_table_controller._refresh_media_table()
        self.window.media_table_controller._refresh_director_combos()
        try:
            self.window.timeline_view.load_from_db()
        except (OSError, RuntimeError, ValueError) as e:
            logging.warning("Timeline-Reload nach Projektwechsel fehlgeschlagen: %s", e)
            self.window.console_text.append(f"[Warnung] Timeline konnte nicht geladen werden: {e}")
        # B-285 Phase B Hook-3: ProjectManager.project_changed -> SCHNITT informieren.
        try:
            self.window.workspace_setup._push_active_project_to_schnitt()
        except Exception as e:
            logging.debug("schnitt push_active_project failed: %s", e)
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
            if hasattr(self.window, "_save_state_label"):
                self.window._save_state_label.setText("ungespeichert")
                self.window._save_state_label.setStyleSheet(
                    "color: #fbbf24; font-size: 10px; background: transparent;"
                )
            self._update_window_title()

    def _mark_clean(self):
        """Mark the session as saved (no pending changes)."""
        if self.window._dirty:
            self.window._dirty = False
            if hasattr(self.window, "_save_state_label"):
                self.window._save_state_label.setText("gespeichert")
                self.window._save_state_label.setStyleSheet(
                    "color: #6b7280; font-size: 10px; background: transparent;"
                )
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
