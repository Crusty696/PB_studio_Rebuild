"""ProjectManagementMixin — extrahiert aus main.py (AUD-44).

Kapselt:
  - _new_project()            — Neues Projekt erstellen
  - _open_project()           — Bestehendes Projekt oeffnen
  - _save_project_as()        — Projekt unter neuem Namen speichern
  - _on_project_changed()     — UI nach Projektwechsel aktualisieren
  - _show_about()             — About-Dialog
  - _show_settings()          — Einstellungs-Dialog
  - _apply_ollama_settings()  — Ollama-Einstellungen anwenden
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog

logger = logging.getLogger(__name__)

APP_VERSION_PLACEHOLDER = "0.5.0"  # wird bei Laufzeit durch self._app_version ersetzt


class ProjectManagementMixin:
    """Mixin fuer MainWindow: Projekt-Verwaltung und Dialoge."""

    def _new_project(self):
        """Show NewProjectDialog and create a new project."""
        from ui.dialogs.project_dialog import NewProjectDialog
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.get_values()
        try:
            self._project_manager.create_project(
                path=vals["path"],
                name=vals["name"],
                resolution=vals["resolution"],
                fps=vals["fps"],
            )
            self._console_append(f"[Projekt] Neues Projekt erstellt: {vals['name']}")
        except (OSError, RuntimeError, ValueError) as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", str(exc))
            self._console_append(f"[Projekt-Fehler] {exc}")

    def _open_project(self):
        """Show OpenProjectDialog and open an existing project."""
        from ui.dialogs.project_dialog import OpenProjectDialog
        dlg = OpenProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        path = dlg.get_path()
        try:
            meta = self._project_manager.open_project(path)
            self._console_append(f"[Projekt] Geoeffnet: {meta.get('name', path.name)}")
        except (OSError, RuntimeError, ValueError) as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", str(exc))
            self._console_append(f"[Projekt-Fehler] {exc}")

    def _save_project_as(self):
        """Save the current project to a new location."""
        from PySide6.QtWidgets import QInputDialog
        folder = QFileDialog.getExistingDirectory(self, "Zielordner waehlen")
        if not folder:
            return
        name, ok = QInputDialog.getText(self, "Projektname", "Name fuer das neue Projekt:")
        if not ok or not name.strip():
            return
        target = Path(folder) / name.strip()
        try:
            self._project_manager.save_project_as(target)
            self._console_append(f"[Projekt] Gespeichert unter: {target}")
        except (OSError, RuntimeError, ValueError) as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Fehler", str(exc))
            self._console_append(f"[Projekt-Fehler] {exc}")

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
        self._project_name_label.setText(project_name)
        app_version = getattr(self, "_app_version", APP_VERSION_PLACEHOLDER)
        self.setWindowTitle(f"PB_studio v{app_version} — {project_name}")
        self._refresh_media_table()
        self._refresh_director_combos()
        try:
            self.timeline_view.load_from_db()
        except (OSError, RuntimeError, ValueError) as e:
            logging.warning("Timeline-Reload nach Projektwechsel fehlgeschlagen: %s", e)
            self.console_text.append(f"[Warnung] Timeline konnte nicht geladen werden: {e}")
        self.status_bar.showMessage(f"Projekt: {project_name}  |  {path}")

    def _show_about(self):
        from ui.dialogs.about import AboutDialog
        app_version = getattr(self, "_app_version", APP_VERSION_PLACEHOLDER)
        dialog = AboutDialog(version=app_version, parent=self)
        dialog.exec()

    def _show_shortcut_help(self):
        """AUD-105: Show keyboard shortcut help overlay (F1 / Ctrl+?)."""
        from ui.dialogs.shortcut_help_dialog import ShortcutHelpDialog
        dlg = ShortcutHelpDialog(parent=self)
        dlg.exec()

    def _show_settings(self):
        """Oeffnet den Einstellungs-Dialog und wendet Aenderungen sofort an."""
        from ui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(parent=self)
        dlg.ollama_settings_changed.connect(self._apply_ollama_settings)
        dlg.exec()

    def _apply_ollama_settings(self, enabled: bool, url: str, model: str) -> None:
        """Wendet neue Ollama-Einstellungen sofort auf den AI-Agent an."""
        if not hasattr(self, "_ai_agent") or self._ai_agent is None:
            return
        try:
            self._ai_agent.configure_ollama(url=url, model=model or None, enabled=enabled)
            status = "aktiv" if enabled else "deaktiviert"
            msg = f"[Einstellungen] Ollama {status}"
            if enabled and model:
                msg += f" — Modell: {model}"
            elif enabled:
                msg += " — Modell: Auto-Select"
            self.console_text.append(msg)
            if hasattr(self, "status_bar"):
                self.status_bar.showMessage(msg, 5000)
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.warning("Ollama-Einstellungen konnten nicht angewendet werden: %s", e)
