from __future__ import annotations

import logging
import os
import re
import subprocess
import stat
from pathlib import Path

logger = logging.getLogger(__name__)


def _ist_verzeichnis_link(pfad: Path) -> bool:
    """B-809: True fuer Symlinks und Windows-Junctions — auch fuer kaputte.

    Dieselbe Erkennung wie ``storage_browser._is_link`` (B-578):
    ``os.path.islink`` liefert bei ``mklink /J``-Junctions auf CPython 3.10
    ``False``, und ``os.path.isjunction`` gibt es erst ab 3.12. Deshalb
    zusaetzlich der Reparse-Tag aus ``os.lstat`` — genau das Signal, das 3.12
    intern nutzt.
    """
    try:
        if pfad.is_symlink():
            return True
    except OSError:
        return False
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None:
        try:
            if is_junction(pfad):
                return True
        except OSError:
            return False
    try:
        st = os.lstat(pfad)
    except OSError:
        return False
    return bool(getattr(st, "st_reparse_tag", 0) == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003))


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class StorageLayout:
    """Content-addressed storage layout rooted at ``storage/``."""

    def __init__(self, storage_root: str | Path) -> None:
        self.storage_root = Path(storage_root)

    @staticmethod
    def validate_sha256(source_sha256: str) -> str:
        if not _SHA256_RE.match(source_sha256):
            raise ValueError(f"Invalid source_sha256: {source_sha256!r}")
        return source_sha256.lower()

    def source_root(self, source_sha256: str) -> Path:
        sha = self.validate_sha256(source_sha256)
        return self.storage_root / "by_sha" / sha[:2] / sha

    def ensure_source_root(self, source_sha256: str) -> Path:
        root = self.source_root(source_sha256)
        (root / "audio").mkdir(parents=True, exist_ok=True)
        (root / "video").mkdir(parents=True, exist_ok=True)
        return root

    def relative_artifact_path(self, source_sha256: str, artifact_path: str | Path) -> str:
        root = self.source_root(source_sha256).absolute()
        artifact = Path(artifact_path).absolute()
        try:
            rel = artifact.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Artifact path is outside source root: {artifact}") from exc
        return rel.as_posix()


def create_directory_link(link_path: str | Path, target_dir: str | Path) -> Path:
    """Create a Windows junction or POSIX symlink for a directory."""

    link = Path(link_path)
    target = Path(target_dir)
    if not target.is_dir():
        raise FileNotFoundError(f"Directory link target missing: {target}")

    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists():
        if not link.is_dir():
            raise FileExistsError(f"Link path exists and is not a directory: {link}")
        return link

    # B-809: ``exists()`` FOLGT der Junction. Zeigt eine vorhandene Junction auf
    # ein inzwischen geloeschtes Ziel, liefert es ``False`` — obwohl der Pfad im
    # Dateisystem belegt ist. ``mklink`` scheiterte dann mit "Eine Datei kann
    # nicht erstellt werden, wenn sie bereits vorhanden ist", und der
    # SCHNITT-Audio-Adapter wurde bei jedem Projekt-Open nicht initialisiert
    # (live beobachtet 2026-08-12).
    # ``lexists`` folgt dem Link nicht und sieht deshalb auch die kaputte
    # Junction. Sie wird entfernt und neu gesetzt — der Pfad soll auf das
    # aktuelle Ziel zeigen, nicht auf ein verschwundenes.
    if os.path.lexists(link):
        if _ist_verzeichnis_link(link):
            logger.info(
                "B-809: verwaiste Junction %s zeigt ins Leere — wird neu gesetzt.",
                link,
            )
            try:
                os.rmdir(link)  # entfernt die Junction, nicht ihr Ziel
            except OSError as exc:
                raise OSError(
                    f"Verwaiste Junction {link} nicht entfernbar: {exc}"
                ) from exc
        else:
            raise FileExistsError(
                f"Link path exists but is neither a usable directory nor a link: {link}"
            )

    if os.name == "nt":
        # text=True would decode mklink's output with the locale codec (cp1252
        # on German Windows), which crashes on console bytes like 0x81. Decode
        # explicitly as UTF-8 with replacement so a junction is never aborted by
        # an undecodable status message.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise OSError(
                f"mklink /J failed for {link} -> {target}: "
                f"{result.stdout.strip()} {result.stderr.strip()}".strip()
            )
    else:
        link.symlink_to(target, target_is_directory=True)
    return link
