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
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox
from ui.base_component import PBComponent
from workers.base import BaseWorker

logger = logging.getLogger(__name__)

APP_VERSION_PLACEHOLDER = "0.5.0"

def _running_under_pytest() -> bool:
    """B-773: Auto-Resume darf in Testlaeufen nie echte Projekte oeffnen."""
    import os
    return "PYTEST_CURRENT_TEST" in os.environ


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

    def _tasks_running_block(self, action_label: str) -> bool:
        """B-465: Sichtbarer Pre-Block vor Projekt-Oeffnen/-Erstellen.

        Wenn Hintergrund-Tasks laufen, warnt den User SOFORT (statt erst tief im
        Worker nach Dialog-Bestaetigung mit dem B-050-Fehler) und bricht ab. Der
        Service-Guard ``ProjectManager._wait_for_tasks_idle`` bleibt unveraendert
        die eigentliche Sicherung — dies ist nur ein zusaetzliches UX-Gate.

        Returns True wenn geblockt (Aufrufer soll dann ohne Dialog returnen).
        """
        try:
            from services.project_manager import ProjectManager
            if not ProjectManager._has_running_tasks():
                return False
        except Exception:  # best-effort: Pre-Block darf den echten Guard nie ersetzen
            return False
        msg = (
            f"{action_label} ist nicht moeglich, solange Hintergrund-Tasks laufen.\n\n"
            "Bitte warte, bis alle Tasks im TASKS-Panel beendet sind, und versuche "
            "es erneut."
        )
        try:
            if hasattr(self.window, "status_bar"):
                self.window.status_bar.showMessage(
                    f"{action_label}: Hintergrund-Tasks laufen noch.", 8000,
                )
        except Exception:  # broad: Status-Bar darf den Dialog nicht blocken
            pass
        try:
            self._show_tasks_running_notice(action_label, msg)
        except Exception as exc:  # broad: best-effort
            logger.warning("B-465: pre-block dialog failed: %s", exc)
        logger.info("B-465: Pre-Block '%s' — Hintergrund-Tasks laufen noch.", action_label)
        return True

    def _show_tasks_running_notice(self, action_label: str, msg: str) -> None:
        """B-799: Pre-Block-Hinweis OHNE verschachtelte Modal-Event-Loop.

        Vorher rief ``_tasks_running_block`` ``QMessageBox.warning(...)`` — die
        statische Variante ruft intern ``exec()`` auf und haengt damit eine
        verschachtelte Qt-Event-Loop in den GUI-Thread. Beleg (live 2026-08-10,
        ``logs/freeze_stacks.log:219668``): der Main-Thread stand >4,5 Minuten in
        ``project_management.py:85 _tasks_running_block`` <- ``:147
        _open_project``, waehrend 486 Proxy-Tasks liefen. Nicht in
        ``_has_running_tasks`` (Zeile 68) — die Iteration laeuft ueber eine Kopie
        (``task_manager.py:652-655``) und haelt kein Lock.

        Unter dieser Last wurde die Box nie gezeichnet und nie bedienbar → der
        Klick-Handler kam nie zurueck (Force-Kill noetig). Ein nicht-modaler
        ``show()``-Dialog kehrt sofort zurueck; der GUI-Thread wird vom Guard
        nicht mehr blockiert.

        Re-Entranz: mehrfaches Klicken darf keine Box-Kette erzeugen — eine
        bereits sichtbare Box wird nur aktualisiert und wieder nach vorn geholt.
        """
        existing = getattr(self, "_pb_pre_block_box", None)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.setWindowTitle(action_label)
                    existing.setText(msg)
                    existing.raise_()
                    return
            except RuntimeError:  # C++-Objekt bereits zerstoert
                pass
            self._pb_pre_block_box = None

        box = QMessageBox(self.window)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(action_label)
        box.setText(msg)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setModal(False)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        box.finished.connect(lambda _result: setattr(self, "_pb_pre_block_box", None))
        self._pb_pre_block_box = box
        box.show()  # NICHT exec(): kein nested event loop im GUI-Thread (B-799)

    def _new_project(self):
        """Show NewProjectDialog and create a new project (Fix F-045: Async)."""
        # B-465: sichtbarer Pre-Block statt Dialog-oeffnen-dann-tief-im-Worker-Fehler.
        if self._tasks_running_block("Neues Projekt"):
            return
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
        # B-465: sichtbarer Pre-Block statt Dialog-oeffnen-dann-tief-im-Worker-Fehler.
        if self._tasks_running_block("Projekt oeffnen"):
            return
        from ui.dialogs.project_dialog import OpenProjectDialog
        dlg = OpenProjectDialog(self.window)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.open_project_async(dlg.get_path())

    def auto_resume_last_project(self) -> None:
        """B-773: Beim App-Start das zuletzt geoeffnete Projekt laden.

        Ein "Autoload" existierte nie — die App bootet auf
        ``APP_ROOT/pb_studio.db``; wechselte der Titel frueher automatisch,
        lag dort zufaellig eine Projekt-Row (Livetest/User-Session
        2026-08-07: Boot-DB leer -> "Kein aktives Projekt", manuelles
        Oeffnen noetig). Hat die Boot-DB bereits ein Projekt, passiert
        nichts. Sonst wird der juengste gueltige Recent-Eintrag ueber
        denselben async OpenWorker-Pfad geoeffnet wie das Menue
        "Letzte Projekte".
        """
        # Testschutz (Muster: graph_cockpit_tab): PBWindow-Tests pumpen den
        # Event-Loop — ohne Guard oeffnete der Timer hier die ECHTEN
        # Recent-Projekte der Maschine mitten im Testlauf (nativer Crash im
        # tests/ui-Bulk-Lauf, beobachtet 2026-08-08). B-773-Tests patchen
        # diese Funktion gezielt auf False.
        if _running_under_pytest():
            return
        try:
            from database import get_active_project_id
            if get_active_project_id() is not None:
                return
        except Exception as exc:
            logger.warning("B-773: Auto-Resume-Check fehlgeschlagen: %s", exc)
            return
        try:
            from services.recent_projects import RecentProjectsManager
            recent = RecentProjectsManager.get_all()
        except Exception as exc:
            logger.warning("B-773: Recent-Liste nicht lesbar: %s", exc)
            return
        from pathlib import Path
        for path_str in recent:
            p = Path(path_str)
            if (p / "pb_studio.db").exists():
                logger.info("B-773: Auto-Resume letztes Projekt: %s", p)
                self.open_project_async(p)
                return
        logger.info(
            "B-773: kein Auto-Resume — Recent-Liste leer oder keine "
            "gueltigen Projektpfade (%d Eintraege).", len(recent),
        )

    def open_project_async(self, path, on_error_extra=None):
        """Oeffnet ein Projekt asynchron via OpenWorker (gemeinsamer Pfad).

        FREEZE-Fix 2026-07-10 (freeze_stacks-Profil): Der Recent-Projekte-Pfad
        rief ``open_project`` bisher SYNCHRON im Main-Thread auf. Bei busy DB
        (Hintergrund-Writer + busy_timeout 120s) blockierte der Klick die UI
        30-60s+ (Watchdog-Beweis: Query.all in migrate_existing_outputs /
        ensure_schnitt_audio_adapter). Jetzt laeuft JEDES Projekt-Oeffnen
        ueber denselben async OpenWorker wie der Dialog-Pfad (F-045).

        Args:
            path: Projektordner.
            on_error_extra: optionaler Callable(exc) zusaetzlich zum
                Standard-Fehlerdialog (z.B. Recent-Eintrag entfernen).
        """
        if self._tasks_running_block("Projekt oeffnen"):
            return

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

        base_error_handler = self._make_project_error_handler("Projekt-Laden fehlgeschlagen")

        def _on_error(exc):
            base_error_handler(exc)
            if on_error_extra is not None:
                try:
                    on_error_extra(exc)
                except Exception:  # noqa: BLE001 — Zusatz-Handler darf nichts brechen
                    logger.debug("open_project_async on_error_extra failed", exc_info=True)

        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Projekt laden",
            worker=worker,
            on_finish=_on_done,
            on_error=_on_error,
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

    def _save_project(self):
        """Save current project state marker for an already-open project."""
        manager = getattr(self.window, "_project_manager", None)
        project_path = getattr(manager, "current_project_path", None)
        if project_path is None:
            QMessageBox.information(
                self.window,
                "Speichern",
                "Kein Projekt geoeffnet. Lege zuerst ein Projekt an oder oeffne eines.",
            )
            return

        try:
            self.window._save_window_state()
        except Exception as exc:
            logger.warning("save_project: failed to save window state: %s", exc)

        self._mark_clean()
        path = Path(project_path)
        self.window.panel_setup._console_append(f"[Projekt] Gespeichert: {path}")
        self.window.status_bar.showMessage(f"Projekt gespeichert: {path.name}", 5000)

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
            self.window._save_state_label.setStyleSheet("color: #98a2b1; font-size: 10px; background: transparent;")
        # B-562: Cockpit-Dashboard VOLL refreshen (Name + Pfad + project_id +
        # Readiness) statt nur das Namens-Label zu setzen. Vorher rief
        # _on_project_changed nur dashboard.update_project(name, path) OHNE
        # project_id/Readiness -> der Cockpit-Innenstatus blieb "Kein Projekt
        # geladen" bis zum ersten Workspace-Wechsel zu Index 0 (der als
        # einziger _refresh_project_dashboard ausloeste). _refresh_project_dashboard
        # liest Name aus _project_name_label (oben gesetzt) + project_id via
        # get_active_project_id() (database.set_project bereits erfolgt).
        try:
            ws_setup = getattr(self.window, "workspace_setup", None)
            if ws_setup is not None and hasattr(ws_setup, "_refresh_project_dashboard"):
                ws_setup._refresh_project_dashboard()
            else:
                dashboard = getattr(self.window, "_project_dashboard", None)
                if dashboard is not None:
                    dashboard.update_project(project_name, str(path))
        except Exception as exc:
            logger.debug("Project dashboard refresh failed: %s", exc)
        self._update_window_title()  # AUD-108: respects dirty flag
        self.window.media_table_controller._refresh_media_table()
        # Analog B-689 (timeline_shell._on_restore_done): Der QUndoStack haelt
        # nach einem Projektwechsel Commands, die auf entry_ids des ALTEN
        # Projekts zeigen. Ein Ctrl+Z danach wuerde Zeilen eines fremden
        # Projekts aendern oder wieder einfuegen. Ein Projektwechsel ist ein
        # neuer Ausgangszustand -> Stack leeren. Bewusst VOR load_from_db und
        # ausserhalb des Reload-try, damit der Stack auch dann sauber ist,
        # wenn der Timeline-Reload scheitert. NICHT in load_from_db selbst,
        # weil undo/redo diese Methode aufrufen.
        try:
            undo_stack = getattr(self.window.timeline_view, "undo_stack", None)
            if undo_stack is not None:
                undo_stack.clear()
        except (AttributeError, RuntimeError) as e:
            logging.warning("Undo-Stack-Reset nach Projektwechsel fehlgeschlagen: %s", e)
        # B-837: Die gezeichnete Pacing-Kurve hing an keinem Lebenszyklus —
        # `reset_curve()` hatte im Produktivcode gar keinen Aufrufer. Eine in
        # Projekt A gezeichnete Kurve blieb damit stehen und bestimmte im
        # Projekt B den Schnitt, weil sie seit B-829 Vorrang vor der
        # Cut-Rate-Wahl hat. Gleiche Begruendung wie beim Undo-Stack darueber:
        # ein Projektwechsel ist ein neuer Ausgangszustand.
        # Eine gezeichnete Kurve geht dabei verloren — sie wird ohnehin
        # nirgends gespeichert (`PacingProfile.manual_density_curve` hat keinen
        # Schreib- oder Lesepfad in die Datenbank).
        try:
            pacing_curve = getattr(self.window, "pacing_curve", None)
            if pacing_curve is not None:
                pacing_curve.reset_curve()
        except (AttributeError, RuntimeError) as e:
            logging.warning("Pacing-Kurven-Reset nach Projektwechsel fehlgeschlagen: %s", e)
        try:
            self.window.timeline_view.load_from_db()
        except (OSError, RuntimeError, ValueError) as e:
            logging.warning("Timeline-Reload nach Projektwechsel fehlgeschlagen: %s", e)
            self.window.console_text.append(f"[Warnung] Timeline konnte nicht geladen werden: {e}")
        # B-657: Die Verwendungs-Markierung im MATERIAL-Pool (Banner "Timeline
        # nutzt X von Y Clips", gruene Zeilen, Grid-Badges) wurde beim
        # Projektwechsel nie neu berechnet -> sie zeigte die Zahlen des ALTEN
        # Projekts weiter, bis zufaellig ein Auto-Edit oder ein Timeline-Add
        # lief. Aufruf-Konvention exakt wie die bestehenden Aufrufer in
        # edit_workspace.py (Zeile 1474/1541): synchron im GUI-Thread mit
        # usage=None, d.h. die Usage wird aus der Timeline-DB des jetzt
        # aktiven Projekts gelesen. Bewusst NACH load_from_db, damit die
        # Timeline-Tabelle bereits auf dem neuen Projekt steht.
        try:
            self.window.edit_workspace._refresh_timeline_usage_marking()
        except Exception as e:
            logging.debug("Timeline-Usage-Markierung nach Projektwechsel fehlgeschlagen: %s", e)
        # B-802: Die Proxy-Warteschlange im VideoAnalysisController wurde
        # repo-weit nie geleert — es gab nur append/popleft. Sie ueberlebte
        # damit den Projektwechsel und erzeugte danach Proxies fuer Clips, die
        # im neuen Projekt gar nicht existieren. Anders als beim Abbruch wird
        # hier zurueckgesetzt, nicht gesperrt: ein Import im neuen Projekt soll
        # normal funktionieren.
        try:
            _va = getattr(self.window, "video_analysis", None)
            if _va is not None and hasattr(_va, "reset_proxy_queue"):
                _va.reset_proxy_queue("Projektwechsel")
        except Exception as e:
            logging.debug("B-802: Proxy-Queue-Reset nach Projektwechsel: %s", e)
        # B-800: keyframe_text ist ein einziges QTextEdit, das beim
        # Projektwechsel nie zurueckgesetzt wurde. Die Keyframe-Strings des
        # ALTEN Projekts blieben deshalb sichtbar und sahen aus, als
        # gehoerten sie zum neuen — live belegt (Live-Verify 2026-08-11:
        # LV-As Strings inkl. eines Clips, den LV-B gar nicht besitzt).
        try:
            self.window.keyframe_text.clear()
        except Exception as e:
            logging.debug("keyframe_text-Reset nach Projektwechsel fehlgeschlagen: %s", e)
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
        try:
            dlg.exec()
        finally:
            # B-706/Q1: ohne Aufraeumen blieb pro Oeffnen ein verstecktes
            # Dialog-QObject samt Signal-Connection am parent haengen
            # (wachsender Leak ueber die Session). deleteLater() NACH exec()
            # ist der sichere Weg (WA_DeleteOnClose + exec() waere ein
            # Use-after-free-Risiko, waehrend exec noch auf dem Stack ist).
            dlg.deleteLater()

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
                    "color: #98a2b1; font-size: 10px; background: transparent;"
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
