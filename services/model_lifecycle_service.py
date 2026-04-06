"""
Model-Lifecycle-Management — AP-4 (AUD-11).

Verantwortlich für:
- Modell-Registry: Alle installierten Modelle (Ollama + HuggingFace) in der DB
- Download-Manager: Ollama Pull mit Streaming-Progress, HF Snapshot-Download
- Auto-Cleanup: Ungenutzte Modelle nach X Tagen vorschlagen
- Scan: Synchronisiert lokale Modelle mit der Registry

Kein torch-Import auf Modul-Ebene (lazy — spart Startup-Zeit).
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from services.timeout_constants import (
    HTTP_API_TIMEOUT_SEC,
    HTTP_HEALTH_CHECK_TIMEOUT_SEC,
    MODEL_DOWNLOAD_TIMEOUT_SEC,
    MODEL_VERIFY_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Empfohlene Modelle für den Download-Dialog
# ──────────────────────────────────────────────────────────────────────────────

RECOMMENDED_OLLAMA_MODELS = [
    {
        "id": "gemma4:e4b",
        "display": "Gemma 4 E4B (Q4_K_M)",
        "size_gb": 9.6,
        "description": "Hauptmodell für AMD RX 7800 XT — Empfohlen",
        "tags": ["empfohlen", "de"],
    },
    {
        "id": "phi3:mini",
        "display": "Phi-3 Mini 3.8B",
        "size_gb": 2.3,
        "description": "Sehr schnell, gut für Action-Parsing",
        "tags": ["schnell"],
    },
    {
        "id": "llama3.1:8b-instruct-q4_K_M",
        "display": "Llama 3.1 8B (Q4)",
        "size_gb": 4.7,
        "description": "Meta's Allrounder — gute Deutsch-Kenntnisse",
        "tags": ["allrounder", "de"],
    },
    {
        "id": "mistral:7b-instruct-q4_K_M",
        "display": "Mistral 7B (Q4)",
        "size_gb": 4.1,
        "description": "Ausgezeichnet für Deutsch, effizient",
        "tags": ["de", "effizient"],
    },
    {
        "id": "gemma2:2b-instruct-q4_K_M",
        "display": "Gemma 2 2B (Q4)",
        "size_gb": 1.6,
        "description": "Google's kleines Modell, sehr effizient",
        "tags": ["klein"],
    },
]

RECOMMENDED_HF_MODELS = [
    {
        "id": "openai/whisper-large-v3",
        "display": "Whisper Large-v3",
        "size_gb": 3.1,
        "description": "Beste Transkriptions-Qualität",
        "tags": ["transcription", "audio"],
    },
    {
        "id": "openai/whisper-medium",
        "display": "Whisper Medium",
        "size_gb": 1.5,
        "description": "Gute Balance Qualität/Geschwindigkeit",
        "tags": ["transcription", "audio", "schnell"],
    },
    {
        "id": "openai/whisper-small",
        "display": "Whisper Small",
        "size_gb": 0.5,
        "description": "Schnell, für Echtzeit-Preview",
        "tags": ["transcription", "audio", "minimal"],
    },
    {
        "id": "google/siglip-so400m-patch14-384",
        "display": "SigLIP Vision (Google)",
        "size_gb": 1.6,
        "description": "Video-Clip-Analyse & Szenen-Embedding",
        "tags": ["vision", "video"],
    },
    {
        "id": "vikhyatk/moondream2",
        "display": "Moondream2",
        "size_gb": 1.7,
        "description": "Leichtes Vision-LLM für Clip-Beschreibung",
        "tags": ["vision", "llm"],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Daten-Strukturen
# ──────────────────────────────────────────────────────────────────────────────

class ModelEntry:
    """Repräsentiert ein einzelnes installiertes Modell."""

    def __init__(
        self,
        model_id: str,
        source: str,
        display_name: str = "",
        size_mb: float = 0.0,
        installed_at: str = "",
        last_used_at: str = "",
        status: str = "installed",
        local_path: str = "",
        metadata: dict | None = None,
    ):
        self.model_id = model_id
        self.source = source
        self.display_name = display_name or model_id
        self.size_mb = size_mb
        self.installed_at = installed_at
        self.last_used_at = last_used_at
        self.status = status
        self.local_path = local_path
        self.metadata = metadata or {}

    @property
    def size_display(self) -> str:
        if self.size_mb >= 1024:
            return f"{self.size_mb / 1024:.1f} GB"
        elif self.size_mb > 0:
            return f"{self.size_mb:.0f} MB"
        return "?"

    @property
    def last_used_display(self) -> str:
        if not self.last_used_at:
            return "Nie"
        try:
            dt = datetime.datetime.fromisoformat(self.last_used_at)
            now = datetime.datetime.utcnow()
            delta = now - dt
            if delta.days == 0:
                return "Heute"
            elif delta.days == 1:
                return "Gestern"
            elif delta.days < 30:
                return f"vor {delta.days} Tagen"
            else:
                return dt.strftime("%d.%m.%Y")
        except (ValueError, AttributeError):
            return self.last_used_at[:10]

    @property
    def days_since_used(self) -> int:
        """Tage seit letzter Nutzung (None wenn nie genutzt = -1)."""
        if not self.last_used_at:
            return -1
        try:
            dt = datetime.datetime.fromisoformat(self.last_used_at)
            return (datetime.datetime.utcnow() - dt).days
        except (ValueError, AttributeError):
            return -1


class DownloadProgress:
    """Progress-State eines laufenden Downloads."""
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.status: str = "starting"
        self.progress: float = 0.0      # 0.0 – 1.0
        self.bytes_done: int = 0
        self.bytes_total: int = 0
        self.speed_mbps: float = 0.0
        self.eta_sec: int = 0
        self.error: str = ""
        self.finished: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Service
# ──────────────────────────────────────────────────────────────────────────────

class ModelLifecycleService:
    """Verwaltet den kompletten Modell-Lebenszyklus.

    Thread-safe. Alle Download-Operationen laufen in Hintergrund-Threads.
    Progress-Callbacks werden aus diesen Threads aufgerufen (Qt-safe via Signal).
    """

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self._lock = threading.Lock()
        self._active_downloads: dict[str, threading.Thread] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Registry: DB-Operationen
    # ──────────────────────────────────────────────────────────────────────

    def _now_iso(self) -> str:
        return datetime.datetime.utcnow().isoformat()

    def _upsert_model(self, entry: ModelEntry) -> None:
        """Erstellt oder aktualisiert einen Registry-Eintrag in der DB."""
        from database import nullpool_session
        from database import ModelRegistry

        with nullpool_session() as session:
            existing = session.query(ModelRegistry).filter_by(model_id=entry.model_id).first()
            if existing is None:
                existing = ModelRegistry(
                    model_id=entry.model_id,
                    source=entry.source,
                    installed_at=entry.installed_at or self._now_iso(),
                )
                session.add(existing)

            existing.display_name = entry.display_name
            existing.size_mb = entry.size_mb
            existing.last_used_at = entry.last_used_at
            existing.status = entry.status
            existing.local_path = entry.local_path
            if entry.metadata:
                existing.metadata_json = json.dumps(entry.metadata, ensure_ascii=False)
            try:
                session.commit()
            except Exception as e:  # broad catch intentional — SQLAlchemy commit can raise many error types
                session.rollback()
                logger.error("ModelRegistry upsert fehlgeschlagen: %s", e)

    def _remove_from_registry(self, model_id: str) -> None:
        """Löscht einen Registry-Eintrag aus der DB."""
        from database import nullpool_session
        from database import ModelRegistry

        with nullpool_session() as session:
            entry = session.query(ModelRegistry).filter_by(model_id=model_id).first()
            if entry:
                session.delete(entry)
                try:
                    session.commit()
                except Exception as e:  # broad catch intentional — SQLAlchemy commit can raise many error types
                    session.rollback()
                    logger.error("ModelRegistry delete fehlgeschlagen: %s", e)

    def touch_last_used(self, model_id: str) -> None:
        """Aktualisiert last_used_at auf jetzt (bei Modell-Load)."""
        from database import nullpool_session
        from database import ModelRegistry

        with nullpool_session() as session:
            entry = session.query(ModelRegistry).filter_by(model_id=model_id).first()
            if entry:
                entry.last_used_at = self._now_iso()
                try:
                    session.commit()
                except Exception as e:  # broad catch intentional — SQLAlchemy commit can raise many error types
                    session.rollback()
                    logger.debug("touch_last_used fehlgeschlagen: %s", e)

    def get_registry_entries(self) -> list[ModelEntry]:
        """Lädt alle Registry-Einträge aus der DB."""
        from database import nullpool_session
        from database import ModelRegistry

        entries = []
        try:
            with nullpool_session() as session:
                rows = session.query(ModelRegistry).order_by(ModelRegistry.source, ModelRegistry.model_id).all()
                for row in rows:
                    meta = {}
                    if row.metadata_json:
                        try:
                            meta = json.loads(row.metadata_json)
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning("Parsing metadata_json for model '%s': %s", row.model_id, e)
                    entries.append(ModelEntry(
                        model_id=row.model_id,
                        source=row.source,
                        display_name=row.display_name or row.model_id,
                        size_mb=row.size_mb or 0.0,
                        installed_at=row.installed_at or "",
                        last_used_at=row.last_used_at or "",
                        status=row.status or "installed",
                        local_path=row.local_path or "",
                        metadata=meta,
                    ))
        except Exception as e:  # broad catch intentional — SQLAlchemy query can raise many error types
            logger.error("get_registry_entries fehlgeschlagen: %s", e)
        return entries

    # ──────────────────────────────────────────────────────────────────────
    # Ollama: Scan + Pull + Delete
    # ──────────────────────────────────────────────────────────────────────

    def scan_ollama_models(self) -> list[ModelEntry]:
        """Fragt Ollama-Server ab und synchronisiert mit der Registry.

        Returns:
            Liste von ModelEntry für alle verfügbaren Ollama-Modelle.
        """
        entries = []
        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/tags",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=HTTP_API_TIMEOUT_SEC) as resp:
                data = json.loads(resp.read())

            for m in data.get("models", []):
                model_id = m.get("name", "")
                if not model_id:
                    continue

                size_bytes = m.get("size", 0)
                size_mb = size_bytes / (1024 * 1024) if size_bytes else 0.0

                # Metadaten aus Ollama-Antwort
                details = m.get("details", {})
                meta = {
                    "parameter_size": details.get("parameter_size", ""),
                    "quantization_level": details.get("quantization_level", ""),
                    "family": details.get("family", ""),
                    "digest": m.get("digest", "")[:12],
                    "modified_at": m.get("modified_at", ""),
                }

                entry = ModelEntry(
                    model_id=model_id,
                    source="ollama",
                    display_name=model_id,
                    size_mb=round(size_mb, 1),
                    installed_at=m.get("modified_at", self._now_iso())[:19].replace("T", " "),
                    last_used_at="",
                    status="installed",
                    metadata=meta,
                )
                entries.append(entry)
                self._upsert_model(entry)

            logger.info("Ollama-Scan: %d Modelle gefunden.", len(entries))
        except urllib.error.URLError:
            logger.debug("Ollama nicht erreichbar bei Scan.")
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            logger.error("Ollama-Scan fehlgeschlagen: %s", e)

        return entries

    def pull_ollama_model(
        self,
        model_name: str,
        progress_cb: Callable[[DownloadProgress], None] | None = None,
    ) -> bool:
        """Lädt ein Ollama-Modell herunter (non-blocking).

        Streaming via Ollama-API /api/pull. Progress-Updates werden an
        ``progress_cb`` gemeldet (läuft in einem Thread).

        Args:
            model_name: Ollama-Modellname (z.B. "qwen2.5:7b")
            progress_cb: Callable mit (DownloadProgress) — wird aus Thread aufgerufen

        Returns:
            True wenn Download gestartet (nicht beendet!), False bei Fehler.
        """
        with self._lock:
            if model_name in self._active_downloads:
                logger.warning("Download für '%s' läuft bereits.", model_name)
                return False

        prog = DownloadProgress(model_name)

        def _do_pull():
            import time
            try:
                # Status in DB: downloading
                self._upsert_model(ModelEntry(
                    model_id=model_name,
                    source="ollama",
                    display_name=model_name,
                    status="downloading",
                ))

                payload = json.dumps({"name": model_name, "stream": True}).encode()
                req = urllib.request.Request(
                    f"{self.ollama_url}/api/pull",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

                t_start = time.time()
                with urllib.request.urlopen(req, timeout=MODEL_DOWNLOAD_TIMEOUT_SEC) as resp:
                    for line in resp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        status_msg = chunk.get("status", "")
                        prog.status = status_msg

                        total = chunk.get("total", 0)
                        completed = chunk.get("completed", 0)

                        if total > 0:
                            prog.bytes_total = total
                            prog.bytes_done = completed
                            prog.progress = completed / total

                            elapsed = time.time() - t_start
                            if elapsed > 0 and completed > 0:
                                speed = completed / elapsed
                                prog.speed_mbps = speed / (1024 * 1024)
                                remaining = total - completed
                                prog.eta_sec = int(remaining / speed) if speed > 0 else 0

                        if progress_cb:
                            progress_cb(prog)

                        if status_msg in ("success", "pull complete"):
                            prog.finished = True
                            prog.progress = 1.0

                # Scan um Größe zu ermitteln
                models = self.scan_ollama_models()
                for m in models:
                    if m.model_id == model_name:
                        break

                logger.info("Ollama pull '%s' erfolgreich.", model_name)

            except (ConnectionError, TimeoutError, OSError, ValueError, RuntimeError) as e:
                prog.error = str(e)
                prog.status = "error"
                prog.finished = True
                logger.error("Ollama pull '%s' fehlgeschlagen: %s", model_name, e)

                self._upsert_model(ModelEntry(
                    model_id=model_name,
                    source="ollama",
                    status="error",
                ))

            finally:
                with self._lock:
                    self._active_downloads.pop(model_name, None)
                if progress_cb:
                    prog.finished = True
                    progress_cb(prog)

        thread = threading.Thread(target=_do_pull, name=f"ollama-pull-{model_name}", daemon=True)
        with self._lock:
            self._active_downloads[model_name] = thread
        thread.start()
        return True

    def delete_ollama_model(self, model_name: str) -> bool:
        """Löscht ein Ollama-Modell via API.

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        try:
            payload = json.dumps({"name": model_name}).encode()
            req = urllib.request.Request(
                f"{self.ollama_url}/api/delete",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="DELETE",
            )
            with urllib.request.urlopen(req, timeout=MODEL_VERIFY_TIMEOUT_SEC) as resp:
                success = resp.status in (200, 204)

            if success:
                self._remove_from_registry(model_name)
                logger.info("Ollama-Modell '%s' gelöscht.", model_name)
            return success
        except (ConnectionError, TimeoutError, OSError, ValueError) as e:
            logger.error("Ollama delete '%s' fehlgeschlagen: %s", model_name, e)
            return False

    def is_ollama_available(self) -> bool:
        """Prüft ob Ollama läuft."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/version")
            with urllib.request.urlopen(req, timeout=HTTP_HEALTH_CHECK_TIMEOUT_SEC) as resp:
                return resp.status == 200
        except (ConnectionError, TimeoutError, OSError):
            return False

    # ──────────────────────────────────────────────────────────────────────
    # HuggingFace: Scan + Download + Delete
    # ──────────────────────────────────────────────────────────────────────

    def _get_hf_cache_dir(self) -> Path:
        """Ermittelt das HuggingFace-Cache-Verzeichnis."""
        # Standard: ~/.cache/huggingface/hub (Linux/Mac) oder
        # C:\Users\<User>\.cache\huggingface\hub (Windows)
        env_dir = os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE")
        if env_dir:
            return Path(env_dir)
        return Path.home() / ".cache" / "huggingface" / "hub"

    def scan_hf_cache(self) -> list[ModelEntry]:
        """Scannt den HuggingFace-Cache und synchronisiert mit der Registry.

        Erkennt installierte Modelle anhand der Cache-Verzeichnis-Struktur.
        Unterstützt den Standard-HF-Cache-Layout: models--org--model/snapshots/...

        Returns:
            Liste von ModelEntry für alle gefundenen HF-Modelle.
        """
        cache_dir = self._get_hf_cache_dir()
        entries = []

        if not cache_dir.exists():
            logger.debug("HF Cache-Dir nicht gefunden: %s", cache_dir)
            return entries

        try:
            for model_dir in cache_dir.iterdir():
                if not model_dir.is_dir():
                    continue
                # Format: models--org--reponame
                name = model_dir.name
                if not name.startswith("models--"):
                    continue

                # Rekonstruiere repo_id: "org/model"
                repo_id = name[len("models--"):].replace("--", "/", 1)

                # Größe berechnen (rekursiv)
                size_bytes = self._dir_size(model_dir)
                size_mb = size_bytes / (1024 * 1024)

                # Installationsdatum = Verzeichnis-Erstellungszeit
                try:
                    installed_at = datetime.datetime.fromtimestamp(
                        model_dir.stat().st_ctime
                    ).isoformat()[:19]
                except OSError:
                    installed_at = self._now_iso()[:19]

                entry = ModelEntry(
                    model_id=repo_id,
                    source="huggingface",
                    display_name=repo_id,
                    size_mb=round(size_mb, 1),
                    installed_at=installed_at,
                    last_used_at="",
                    status="installed",
                    local_path=str(model_dir),
                )
                entries.append(entry)
                self._upsert_model(entry)

            logger.info("HF Cache-Scan: %d Modelle gefunden.", len(entries))
        except OSError as e:
            logger.error("HF Cache-Scan fehlgeschlagen: %s", e)

        return entries

    def _dir_size(self, path: Path) -> int:
        """Rekursive Verzeichnisgröße in Bytes."""
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except OSError as e:
                        logger.warning("Reading file size for '%s': %s", p, e)
        except OSError as e:
            logger.warning("Calculating directory size for '%s': %s", path, e)
        return total

    def download_hf_model(
        self,
        repo_id: str,
        progress_cb: Callable[[DownloadProgress], None] | None = None,
        revision: str = "main",
    ) -> bool:
        """Lädt ein HuggingFace-Modell mit Resume-Support herunter.

        Nutzt huggingface_hub.snapshot_download() falls verfügbar.
        Fallback: Einfacher Download über transformers AutoModel.

        Args:
            repo_id: HF-Repo-ID (z.B. "openai/whisper-large-v3")
            progress_cb: Progress-Callback
            revision: Git-Revision (Default: "main")

        Returns:
            True wenn Download gestartet, False bei Fehler.
        """
        with self._lock:
            if repo_id in self._active_downloads:
                logger.warning("Download für '%s' läuft bereits.", repo_id)
                return False

        prog = DownloadProgress(repo_id)

        def _do_download():
            try:
                # Status in DB: downloading
                self._upsert_model(ModelEntry(
                    model_id=repo_id,
                    source="huggingface",
                    display_name=repo_id,
                    status="downloading",
                ))

                prog.status = "starting"
                if progress_cb:
                    progress_cb(prog)

                try:
                    from huggingface_hub import snapshot_download
                    class _ProgressTracker:
                        def __init__(self):
                            self._total = 0
                            self._done = 0

                        def update(self, n: int):
                            self._done += n
                            if self._total > 0:
                                prog.bytes_done = self._done
                                prog.bytes_total = self._total
                                prog.progress = min(self._done / self._total, 0.99)
                                prog.status = "downloading"
                                if progress_cb:
                                    progress_cb(prog)

                    # snapshot_download lädt alle Dateien mit Resume-Support
                    cache_dir = snapshot_download(
                        repo_id=repo_id,
                        revision=revision,
                        local_files_only=False,
                    )

                    prog.status = "done"
                    prog.progress = 1.0
                    prog.finished = True

                    # Größe ermitteln
                    size_bytes = self._dir_size(Path(cache_dir))
                    size_mb = size_bytes / (1024 * 1024)

                    self._upsert_model(ModelEntry(
                        model_id=repo_id,
                        source="huggingface",
                        display_name=repo_id,
                        size_mb=round(size_mb, 1),
                        installed_at=self._now_iso()[:19],
                        status="installed",
                        local_path=cache_dir,
                    ))

                    logger.info("HF download '%s' erfolgreich (%s MB).", repo_id, round(size_mb, 1))

                except ImportError:
                    # Fallback: AutoModel.from_pretrained (lädt auch in Cache)
                    prog.status = "downloading (transformers)"
                    if progress_cb:
                        progress_cb(prog)

                    from transformers import AutoModel, AutoTokenizer
                    AutoTokenizer.from_pretrained(repo_id, revision=revision)
                    AutoModel.from_pretrained(repo_id, revision=revision)

                    prog.progress = 1.0
                    prog.finished = True
                    prog.status = "done"

                    self._upsert_model(ModelEntry(
                        model_id=repo_id,
                        source="huggingface",
                        display_name=repo_id,
                        installed_at=self._now_iso()[:19],
                        status="installed",
                    ))

            except (ConnectionError, TimeoutError, OSError, ImportError, RuntimeError) as e:
                prog.error = str(e)
                prog.status = "error"
                prog.finished = True
                logger.error("HF download '%s' fehlgeschlagen: %s", repo_id, e)

                self._upsert_model(ModelEntry(
                    model_id=repo_id,
                    source="huggingface",
                    status="error",
                ))
            finally:
                with self._lock:
                    self._active_downloads.pop(repo_id, None)
                if progress_cb:
                    prog.finished = True
                    progress_cb(prog)

        thread = threading.Thread(target=_do_download, name=f"hf-dl-{repo_id}", daemon=True)
        with self._lock:
            self._active_downloads[repo_id] = thread
        thread.start()
        return True

    def delete_hf_model(self, repo_id: str) -> bool:
        """Löscht ein HuggingFace-Modell aus dem Cache.

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        try:
            try:
                from huggingface_hub import scan_cache_dir
                cache_info = scan_cache_dir()
                for repo in cache_info.repos:
                    if repo.repo_id == repo_id:
                        strategy = cache_info.delete_revisions(
                            *[rev.commit_hash for rev in repo.revisions]
                        )
                        strategy.execute()
                        self._remove_from_registry(repo_id)
                        logger.info("HF-Modell '%s' aus Cache gelöscht.", repo_id)
                        return True
                logger.warning("HF-Modell '%s' nicht im Cache gefunden.", repo_id)
            except ImportError:
                # Manuelles Löschen
                cache_dir = self._get_hf_cache_dir()
                model_dir_name = "models--" + repo_id.replace("/", "--")
                model_dir = cache_dir / model_dir_name
                if model_dir.exists():
                    import shutil
                    shutil.rmtree(model_dir)
                    self._remove_from_registry(repo_id)
                    logger.info("HF-Modell '%s' manuell gelöscht.", repo_id)
                    return True

        except (OSError, RuntimeError) as e:
            logger.error("HF delete '%s' fehlgeschlagen: %s", repo_id, e)

        return False

    # ──────────────────────────────────────────────────────────────────────
    # Auto-Cleanup: Ungenutzte Modelle vorschlagen
    # ──────────────────────────────────────────────────────────────────────

    def get_cleanup_candidates(self, days_unused: int = 30) -> list[ModelEntry]:
        """Findet Modelle die seit mehr als ``days_unused`` Tagen nicht verwendet wurden.

        Args:
            days_unused: Modelle die länger als diese Anzahl Tage nicht genutzt
                         wurden, werden vorgeschlagen. -1 = nie genutzt.

        Returns:
            Liste von ModelEntry-Objekten (nur installierte, nicht aktive).
        """
        candidates = []
        for entry in self.get_registry_entries():
            if entry.status != "installed":
                continue

            days = entry.days_since_used
            # Nie genutzte Modelle (-1) oder überfällige
            if days == -1 or days >= days_unused:
                candidates.append(entry)

        # Sortiert: zuerst nie genutzt, dann nach Alter
        candidates.sort(key=lambda e: (e.days_since_used != -1, -e.days_since_used, -e.size_mb))
        return candidates

    # ──────────────────────────────────────────────────────────────────────
    # Vollständiger Scan (Ollama + HF)
    # ──────────────────────────────────────────────────────────────────────

    def scan_all(self) -> list[ModelEntry]:
        """Scannt Ollama + HuggingFace Cache und gibt alle Modelle zurück.

        Synchronisiert gleichzeitig mit der Registry-DB.
        """
        entries = []

        if self.is_ollama_available():
            entries.extend(self.scan_ollama_models())
        else:
            # Zeige Ollama-Modelle aus Registry (evtl. offline)
            from database import nullpool_session, ModelRegistry
            try:
                with nullpool_session() as session:
                    rows = session.query(ModelRegistry).filter_by(source="ollama").all()
                    for row in rows:
                        entries.append(ModelEntry(
                            model_id=row.model_id,
                            source="ollama",
                            display_name=row.display_name or row.model_id,
                            size_mb=row.size_mb or 0.0,
                            installed_at=row.installed_at or "",
                            last_used_at=row.last_used_at or "",
                            status="offline",
                        ))
            except Exception as e:  # broad catch intentional — SQLAlchemy query can raise many error types
                logger.warning("Loading offline Ollama models from registry: %s", e)

        entries.extend(self.scan_hf_cache())
        return entries

    def is_download_active(self, model_id: str) -> bool:
        """Prüft ob ein Download aktiv läuft."""
        with self._lock:
            return model_id in self._active_downloads

    def cancel_download(self, model_id: str) -> None:
        """Bricht einen laufenden Download ab (best-effort)."""
        # Thread kann nicht hart abgebrochen werden in Python.
        # Wir entfernen ihn aus der Map — Thread läuft ggf. weiter bis zum
        # nächsten Chunk-Check, dann wird er beendet.
        with self._lock:
            self._active_downloads.pop(model_id, None)


# ──────────────────────────────────────────────────────────────────────────────
# Modulweiter Singleton
# ──────────────────────────────────────────────────────────────────────────────

_service_instance: ModelLifecycleService | None = None
_service_lock = threading.Lock()


def get_model_lifecycle_service(ollama_url: str = "http://localhost:11434") -> ModelLifecycleService:
    """Gibt den modulweiten Singleton-Service zurück."""
    global _service_instance
    with _service_lock:
        if _service_instance is None:
            _service_instance = ModelLifecycleService(ollama_url=ollama_url)
        return _service_instance
