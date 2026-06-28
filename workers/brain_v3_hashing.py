"""Brain V3 — Hash-Registrierungs-Worker (Phase 1 App-Sync).

Laeuft nach FolderImportWorker.finished. Iteriert die importierten
Audio- und Video-Pfade und ruft MediaHashRegistry.register() pro Datei.

Idempotent: doppelte Registrierung wird im Repository erkannt
(is_new=False), keine Fehler.

Pfade die nicht existieren oder nicht lesbar sind, werden geloggt
und uebersprungen — der Import-Status bleibt unberuehrt.
"""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from services.brain.storage.media_hash_registry import (
    MediaHashRegistry,
    get_default_registry,
)

logger = logging.getLogger(__name__)


class BrainV3HashingWorker(QObject):
    """Iteriert Audio/Video-Pfade nach Import und registriert sha256-Hashes.

    Signals:
        file_hashed(str): Console-Nachricht pro Datei
                          ('[Brain V3] Hash <kurz>... in V3-DB gespeichert' /
                           '[Brain V3] Hash <kurz>... bekannt — Cache-Hit')
        progress(int, str): (percent, message)
        finished(int, int): (n_new, n_known)
        error(str): Top-Level-Fehler (Worker-Crash)
    """

    file_hashed = Signal(str)
    progress = Signal(int, str)
    finished = Signal(int, int)
    error = Signal(str)
    # Phase-2 App-Sync: pro registriertem Hash-Eintrag, auch bei Cache-Hits,
    # damit der EmbeddingScheduler fehlende Embeddings nachziehen oder Hits loggen kann.
    hash_registered = Signal(str, str, str)  # (media_hash, source_path, media_type)

    def __init__(
        self,
        paths_audio: list[str],
        paths_video: list[str],
        registry: MediaHashRegistry | None = None,
    ):
        super().__init__()
        self._paths_audio = list(paths_audio)
        self._paths_video = list(paths_video)
        self._registry = registry  # None → lazy-resolve in run() (Singleton)
        self._errored = False

    def run(self) -> None:
        n_new = 0
        n_known = 0
        try:
            registry = self._registry or get_default_registry()
            queue: list[tuple[str, str]] = (
                [(p, "audio") for p in self._paths_audio]
                + [(p, "video") for p in self._paths_video]
            )
            total = len(queue)
            if total == 0:
                self.finished.emit(0, 0)
                return

            for idx, (path_str, media_type) in enumerate(queue, start=1):
                p = Path(path_str)
                name = p.name
                if not p.exists():
                    self.file_hashed.emit(
                        f"[Brain V3] Datei verschwunden, skip: {name}"
                    )
                    pct = int(idx / total * 100)
                    self.progress.emit(pct, f"Hashe {idx}/{total} ...")
                    continue
                try:
                    result = registry.register(p, media_type)
                except (OSError, IOError, ValueError) as exc:
                    logger.warning(
                        "BrainV3HashingWorker: register failed for %s: %s",
                        path_str, exc,
                    )
                    self.file_hashed.emit(
                        f"[Brain V3] Hash fehlgeschlagen: {name} — {exc}"
                    )
                    pct = int(idx / total * 100)
                    self.progress.emit(pct, f"Hashe {idx}/{total} ...")
                    continue

                short = result.entry.media_hash[:8]
                if result.is_new:
                    n_new += 1
                    self.file_hashed.emit(
                        f"[Brain V3] Hash {short}... in V3-DB gespeichert ({name})"
                    )
                else:
                    n_known += 1
                    self.file_hashed.emit(
                        f"[Brain V3] Hash {short}... bekannt — Cache-Hit ({name})"
                    )
                self.hash_registered.emit(
                    result.entry.media_hash,
                    result.entry.source_path,
                    result.entry.media_type,
                )
                pct = int(idx / total * 100)
                self.progress.emit(pct, f"Hashe {idx}/{total} ...")

            self.finished.emit(n_new, n_known)
        except Exception as exc:
            logger.error(
                "BrainV3HashingWorker crashed: %s\n%s",
                exc, traceback.format_exc(),
            )
            self._errored = True
            self.error.emit(str(exc))
            self.finished.emit(n_new, n_known)
