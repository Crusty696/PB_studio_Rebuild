"""Brain V3 Pfad-Konventionen — strikt getrennt von V1/V2.

App-globale V3-Stores liegen unter %APPDATA%\\PB_Studio\\brain_v3\\.
Projekt-spezifische V3-Stores liegen unter <project>/brain_v3/.

Alle Pfade werden bei erstem Zugriff erstellt (mkdir parents=True).
"""
from __future__ import annotations

import os
from pathlib import Path


_APP_NAME = "PB_Studio"
_BRAIN_V3 = "brain_v3"


def _appdata_root() -> Path:
    """Windows: %APPDATA%. Linux/macOS-Fallback: ~/.config (fuer Dev/Test)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata)
    # Fallback fuer Nicht-Windows (Tests in CI etc.)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def brain_v3_app_dir(create: bool = True) -> Path:
    """App-globaler V3-Store: %APPDATA%\\PB_Studio\\brain_v3\\.

    Enthaelt: weights.db, patterns.db, embedding_cache.db, embeddings/*.npy
    Nicht zu verwechseln mit V1/V2 unter %APPDATA%\\PB_Studio\\ ohne brain_v3/.
    """
    p = _appdata_root() / _APP_NAME / _BRAIN_V3
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def brain_v3_app_embeddings_dir(create: bool = True) -> Path:
    """Physische .npy-Embedding-Files (Index liegt in embedding_cache.db)."""
    p = brain_v3_app_dir(create=create) / "embeddings"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def brain_v3_project_dir(project_root: Path, create: bool = True) -> Path:
    """Projekt-spezifischer V3-Store: <project>/brain_v3/.

    Enthaelt: embeddings.db (sqlite-vec virtuelle Tabellen), state.db
    """
    p = Path(project_root) / _BRAIN_V3
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def weights_db_path(create_dir: bool = True) -> Path:
    return brain_v3_app_dir(create=create_dir) / "weights.db"


def patterns_db_path(create_dir: bool = True) -> Path:
    return brain_v3_app_dir(create=create_dir) / "patterns.db"


def embedding_cache_db_path(create_dir: bool = True) -> Path:
    return brain_v3_app_dir(create=create_dir) / "embedding_cache.db"


def project_embeddings_db_path(project_root: Path, create_dir: bool = True) -> Path:
    return brain_v3_project_dir(project_root, create=create_dir) / "embeddings.db"


def project_state_db_path(project_root: Path, create_dir: bool = True) -> Path:
    return brain_v3_project_dir(project_root, create=create_dir) / "state.db"
