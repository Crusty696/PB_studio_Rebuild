"""Brain V3 — Phase-0-Spike: GPU-Coexistenz + VRAM-Budget-Messung.

Zweck (NVIDIA-Plan, Phase 0): REAL messen, was die V3-Modelle (CLAP +
SigLIP-2) auf der vorhandenen NVIDIA-GPU an VRAM kosten — einzeln, in
Batch-Varianten, und kombiniert. Liefert die Datenbasis fuer die
Phase-2-DoD-Schwellen (Batch-Size, OOM-Punkt, sequenzieller vs.
paralleler Modell-Lifecycle).

KEINE Annahmen, keine Schoenung — was nicht messbar ist, wird als
"unmeasured" markiert. Bei OOM wird der Fehler eingefangen und mit
Last-Snapshot dokumentiert, statt das Skript abzubrechen.

Aufruf-Beispiele
----------------
    # Voller Lauf (alle Tests, default):
    python scripts/spike_brain_v3_gpu_coexistence.py

    # Nur Baseline + CLAP:
    python scripts/spike_brain_v3_gpu_coexistence.py --tests baseline,clap

    # Inkl. Bestands-SigLIP-1 (SoViT-400M aus V1/V2-Stack):
    python scripts/spike_brain_v3_gpu_coexistence.py --include-existing-siglip

    # Nur Coexistenz-Test (CLAP + SigLIP-2 gleichzeitig — OOM erwartet auf 6 GB):
    python scripts/spike_brain_v3_gpu_coexistence.py --tests coexistence

    # Anderes Output-Verzeichnis:
    python scripts/spike_brain_v3_gpu_coexistence.py --out-dir D:\spike_outputs

Outputs
-------
    outputs/spike_brain_v3_gpu/<timestamp>/
        snapshots.json     — alle VRAM-Snapshots, strukturiert
        report.md          — Markdown-Synthese, kopierbar in Vault
        run.log            — Roh-Log

Exit-Codes
----------
    0   Spike erfolgreich durchgelaufen (auch mit OOMs — die sind Daten,
        kein Fehler)
    2   Kein NVIDIA-CUDA-Device verfuegbar (Spike sinnlos)
    3   torch nicht installiert / nicht importierbar
    4   Argument-Fehler

Ehrlichkeits-Hinweis (CLAUDE.md OBERSTE REGEL)
----------------------------------------------
Dieses Skript ist GESCHRIEBEN, NICHT verifiziert auf der Ziel-Hardware
(GTX 1060 6 GB). Es muss VOM USER auf der echten Maschine ausgefuehrt
werden. Erst nach erfolgreichem Lauf darf der Spike als
"phase-0-complete" markiert werden.

Status: code-fix-pending-live-verification
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import platform
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

# --- Project-Root in PYTHONPATH ----------------------------------------------
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# --- Konstanten --------------------------------------------------------------
CLAP_MODEL_ID = "laion/larger_clap_music"
SIGLIP2_MODEL_ID = "google/siglip2-base-patch16-384"
SIGLIP_EXISTING_MODEL_ID = "google/siglip-so400m-patch14-384"  # V1/V2-Bestand

DEFAULT_TESTS = ["baseline", "clap", "siglip2", "coexistence"]
ALL_TESTS = DEFAULT_TESTS + ["siglip_existing", "demucs"]

DEFAULT_OUT_DIR = _ROOT / "outputs" / "spike_brain_v3_gpu"

# --- Logging-Setup -----------------------------------------------------------
logger = logging.getLogger("spike_brain_v3_gpu")


def _setup_logging(out_dir: Path) -> Path:
    log_path = out_dir / "run.log"
    fmt = "%(asctime)s [%(levelname)5s] %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    return log_path


# --- VRAM-Snapshot -----------------------------------------------------------
@dataclass
class Snapshot:
    label: str
    timestamp: str
    allocated_mb: Optional[float]
    reserved_mb: Optional[float]
    total_mb: Optional[float]
    free_mb: Optional[float]
    note: str = ""


def _take_snapshot(label: str, note: str = "") -> Snapshot:
    """Misst VRAM-Belegung. Verwendet vorhandenes services.gpu_info wenn
    moeglich, sonst direkt torch."""
    try:
        import torch  # type: ignore
        if not torch.cuda.is_available():
            return Snapshot(
                label=label,
                timestamp=datetime.now().isoformat(),
                allocated_mb=None,
                reserved_mb=None,
                total_mb=None,
                free_mb=None,
                note=f"{note} (cuda not available)".strip(),
            )

        allocated = torch.cuda.memory_allocated(0) / (1024 * 1024)
        reserved = torch.cuda.memory_reserved(0) / (1024 * 1024)
        total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)

        # mem_get_info gibt (free, total) in bytes — exakter als reserved
        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(0)
            free = free_bytes / (1024 * 1024)
        except Exception:
            free = total - reserved

        snap = Snapshot(
            label=label,
            timestamp=datetime.now().isoformat(),
            allocated_mb=round(allocated, 1),
            reserved_mb=round(reserved, 1),
            total_mb=round(total, 1),
            free_mb=round(free, 1),
            note=note,
        )
        logger.info(
            "SNAPSHOT %-50s  allocated=%7.1f MB  reserved=%7.1f MB  free=%7.1f MB",
            label,
            snap.allocated_mb or 0,
            snap.reserved_mb or 0,
            snap.free_mb or 0,
        )
        return snap
    except Exception as exc:
        logger.warning("Snapshot %s failed: %s", label, exc)
        return Snapshot(
            label=label,
            timestamp=datetime.now().isoformat(),
            allocated_mb=None,
            reserved_mb=None,
            total_mb=None,
            free_mb=None,
            note=f"{note} (snapshot error: {exc})".strip(),
        )


def _empty_cache() -> None:
    """Entlaedt PyTorch-Cache und triggert GC. Mehrfacher Aufruf bewusst."""
    try:
        import torch  # type: ignore
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
    except Exception as exc:
        logger.warning("empty_cache failed: %s", exc)


# --- Test-Container ----------------------------------------------------------
@dataclass
class TestResult:
    name: str
    started_at: str
    finished_at: str = ""
    status: str = "pending"  # pending | ok | oom | error | skipped
    snapshots: list[Snapshot] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def add(self, snap: Snapshot) -> None:
        self.snapshots.append(snap)


# --- Tests -------------------------------------------------------------------
def test_baseline() -> TestResult:
    """Was kostet ein leerer torch + cuda init?"""
    res = TestResult(name="baseline", started_at=datetime.now().isoformat())
    res.add(_take_snapshot("baseline_before_torch_init"))
    try:
        import torch  # type: ignore
        # Forciert CUDA-Context-Init durch echten Tensor-Alloc.
        # _check_cuda_or_exit() hat oben schon sichergestellt dass CUDA da ist,
        # daher kein Fallback noetig.
        sentinel = torch.zeros(1, device="cuda")
        res.add(_take_snapshot("baseline_after_cuda_init", "1-tensor allocated"))
        del sentinel
        _empty_cache()
        res.add(_take_snapshot("baseline_after_empty_cache"))
        res.status = "ok"
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("baseline failed: %s\n%s", exc, traceback.format_exc())
    res.finished_at = datetime.now().isoformat()
    return res


def _try_load_clap(device: str) -> Any:
    """Versucht CLAP zu laden. Wirft bei Fehler weiter."""
    from transformers import ClapModel, ClapProcessor  # type: ignore
    logger.info("Loading CLAP %s ...", CLAP_MODEL_ID)
    processor = ClapProcessor.from_pretrained(CLAP_MODEL_ID)
    model = ClapModel.from_pretrained(CLAP_MODEL_ID).to(device).eval()
    return model, processor


def test_clap(skip_inference: bool = False) -> TestResult:
    """CLAP laden, kurz inferieren, unloaden — VRAM-Peak messen."""
    res = TestResult(
        name="clap",
        started_at=datetime.now().isoformat(),
        metadata={"model": CLAP_MODEL_ID, "skip_inference": skip_inference},
    )
    try:
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            res.status = "skipped"
            res.error = "kein CUDA verfuegbar"
            res.finished_at = datetime.now().isoformat()
            return res

        res.add(_take_snapshot("clap_before_load"))
        model, processor = _try_load_clap(device)
        res.add(_take_snapshot("clap_after_load"))

        if not skip_inference:
            # Kurzes Audio-Stueck: 10 s @ 48 kHz random noise
            import numpy as np
            sr = 48000
            audio = np.random.randn(sr * 10).astype("float32") * 0.1
            inputs = processor(audios=audio, sampling_rate=sr, return_tensors="pt").to(device)
            res.add(_take_snapshot("clap_after_processor"))
            with torch.no_grad():
                features = model.get_audio_features(**inputs)
            res.add(_take_snapshot("clap_after_inference"))
            res.metadata["feature_shape"] = list(features.shape)
            res.metadata["feature_dim"] = int(features.shape[-1])
            del features, inputs

        del model, processor
        _empty_cache()
        res.add(_take_snapshot("clap_after_unload_and_empty_cache"))
        res.status = "ok"
    except Exception as exc:
        is_oom = ("OutOfMemory" in type(exc).__name__) or ("out of memory" in str(exc).lower())
        res.status = "oom" if is_oom else "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("clap failed (%s): %s", res.status, exc)
        try:
            res.add(_take_snapshot("clap_at_failure"))
        except Exception:
            pass
        _empty_cache()
    res.finished_at = datetime.now().isoformat()
    return res


def _try_load_siglip_vision(model_id: str, device: str, dtype: Any = None) -> Any:
    """Laedt nur den Vision-Tower von SigLIP/SigLIP-2.

    SPIKE-LAUF 2026-05-03 11:56: AutoProcessor scheiterte mit transformers
    4.38.2 weil der SigLIP-2-Tokenizer einen NoneType-vocab_file zurueckgibt.
    Wir brauchen fuer Brain V3 ohnehin nur Vision-Features → nutzen
    AutoImageProcessor, das laedt nur die Bild-Seite ohne Tokenizer.
    """
    from transformers import AutoModel, AutoImageProcessor  # type: ignore
    import torch  # type: ignore
    logger.info("Loading SigLIP vision %s (dtype=%s) ...", model_id, dtype or "default")
    processor = AutoImageProcessor.from_pretrained(model_id)
    full = AutoModel.from_pretrained(model_id, torch_dtype=dtype) if dtype else \
        AutoModel.from_pretrained(model_id)
    # Vision-Tower extrahieren (spart VRAM)
    vision = full.vision_model if hasattr(full, "vision_model") else full
    vision = vision.to(device).eval()
    del full  # Text-Tower freigeben falls vorhanden
    gc.collect()
    return vision, processor


def test_siglip(model_id: str, batch_sizes: list[int],
                test_label_prefix: str = "siglip2") -> TestResult:
    """SigLIP Vision-Tower: VRAM bei verschiedenen Batch-Sizes messen.

    Bricht bei OOM nicht ab — markiert die Batch-Stufe als oom und faehrt
    mit kleineren Batches fort (falls vorhanden).
    """
    res = TestResult(
        name=test_label_prefix,
        started_at=datetime.now().isoformat(),
        metadata={"model": model_id, "batch_sizes_tried": batch_sizes,
                  "batch_results": {}},
    )
    try:
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            res.status = "skipped"
            res.error = "kein CUDA verfuegbar"
            res.finished_at = datetime.now().isoformat()
            return res

        res.add(_take_snapshot(f"{test_label_prefix}_before_load"))
        vision, processor = _try_load_siglip_vision(model_id, device)
        res.add(_take_snapshot(f"{test_label_prefix}_after_load"))

        # Aufloesung ermitteln (fuer Random-Image).
        # processor.image_processor.size ist je nach Modell:
        #   - int                                 (alte HF-Versionen)
        #   - {"height": H, "width": W}           (SigLIP-2 base)
        #   - {"shortest_edge": N}                (manche Vision-Modelle)
        # Defensiv alle Faelle abfangen.
        img_size = 384
        try:
            sz = processor.image_processor.size
            if isinstance(sz, int):
                img_size = sz
            elif isinstance(sz, dict):
                img_size = sz.get("height") or sz.get("shortest_edge") or 384
        except Exception as exc:
            logger.debug("image_size detection failed: %s — using 384", exc)
        res.metadata["img_size_used"] = img_size

        from PIL import Image
        import numpy as np

        for bs in sorted(batch_sizes):
            label = f"{test_label_prefix}_batch_{bs}"
            try:
                images = [Image.fromarray((np.random.rand(img_size, img_size, 3) * 255).astype("uint8"))
                          for _ in range(bs)]
                inputs = processor(images=images, return_tensors="pt").to(device)
                with torch.no_grad():
                    out = vision(**inputs)
                snap = _take_snapshot(f"{label}_after_inference",
                                      note=f"bs={bs}")
                res.add(snap)
                feat = out.pooler_output if hasattr(out, "pooler_output") else \
                       (out.last_hidden_state.mean(dim=1) if hasattr(out, "last_hidden_state") else None)
                res.metadata["batch_results"][str(bs)] = {
                    "status": "ok",
                    "vram_allocated_mb": snap.allocated_mb,
                    "vram_reserved_mb": snap.reserved_mb,
                    "feature_shape": list(feat.shape) if feat is not None else None,
                }
                del out, feat, inputs, images
                _empty_cache()
            except Exception as exc:
                is_oom = ("OutOfMemory" in type(exc).__name__) or \
                         ("out of memory" in str(exc).lower())
                logger.warning("%s failed (%s): %s", label,
                               "OOM" if is_oom else "ERROR", exc)
                res.metadata["batch_results"][str(bs)] = {
                    "status": "oom" if is_oom else "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                try:
                    res.add(_take_snapshot(f"{label}_at_failure"))
                except Exception:
                    pass
                _empty_cache()
                if is_oom:
                    # Bei OOM hoehere Batch-Sizes ueberspringen
                    higher = [b for b in batch_sizes if b > bs]
                    for hb in higher:
                        res.metadata["batch_results"][str(hb)] = {
                            "status": "skipped_after_lower_oom"
                        }
                    break

        del vision, processor
        _empty_cache()
        res.add(_take_snapshot(f"{test_label_prefix}_after_unload"))
        res.status = "ok"
    except Exception as exc:
        is_oom = ("OutOfMemory" in type(exc).__name__) or ("out of memory" in str(exc).lower())
        res.status = "oom" if is_oom else "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("%s failed (%s): %s\n%s", test_label_prefix, res.status, exc,
                     traceback.format_exc())
        _empty_cache()
    res.finished_at = datetime.now().isoformat()
    return res


def test_coexistence_clap_siglip2() -> TestResult:
    """Beide Modelle gleichzeitig im VRAM — entscheidet ueber Architektur-
    Prinzip "sequenzieller Modell-Lifecycle" aus Plan-Doc 02 #21+#22.
    Auf 6 GB GTX 1060 wird OOM erwartet, das ist OK und liefert Daten."""
    res = TestResult(
        name="coexistence",
        started_at=datetime.now().isoformat(),
        metadata={"clap": CLAP_MODEL_ID, "siglip2": SIGLIP2_MODEL_ID},
    )
    try:
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            res.status = "skipped"
            res.error = "kein CUDA verfuegbar"
            res.finished_at = datetime.now().isoformat()
            return res

        res.add(_take_snapshot("coex_before_anything"))

        clap_model = clap_proc = None
        sig_vision = sig_proc = None
        try:
            clap_model, clap_proc = _try_load_clap(device)
            res.add(_take_snapshot("coex_after_clap_loaded"))
        except Exception as exc:
            res.metadata["clap_load"] = f"{type(exc).__name__}: {exc}"
            res.add(_take_snapshot("coex_clap_load_failed"))
            res.status = "error"
            res.error = "CLAP-Load fehlgeschlagen — Coexistenz-Test abgebrochen"
            res.finished_at = datetime.now().isoformat()
            _empty_cache()
            return res

        try:
            sig_vision, sig_proc = _try_load_siglip_vision(SIGLIP2_MODEL_ID, device)
            res.add(_take_snapshot("coex_after_siglip2_loaded"))
            res.metadata["siglip2_load"] = "ok"
            res.metadata["coexistence_possible"] = True
        except Exception as exc:
            is_oom = ("OutOfMemory" in type(exc).__name__) or \
                     ("out of memory" in str(exc).lower())
            res.metadata["siglip2_load"] = f"{type(exc).__name__}: {exc}"
            res.metadata["coexistence_possible"] = False
            res.metadata["siglip2_oom"] = is_oom
            res.add(_take_snapshot("coex_siglip2_load_failed"))
            res.status = "oom" if is_oom else "error"
            res.error = (
                "Coexistenz NICHT moeglich (OOM) — "
                "sequenzieller Modell-Lifecycle ist Pflicht (Plan-Doc 02 #21)"
                if is_oom else "Coexistenz-Test fehlgeschlagen, kein OOM"
            )

        # Aufraeumen
        if clap_model is not None:
            del clap_model, clap_proc
        if sig_vision is not None:
            del sig_vision, sig_proc
        _empty_cache()
        res.add(_take_snapshot("coex_after_cleanup"))

        if res.status == "pending":
            res.status = "ok"
    except Exception as exc:
        res.status = "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("coexistence failed: %s\n%s", exc, traceback.format_exc())
        _empty_cache()
    res.finished_at = datetime.now().isoformat()
    return res


def test_demucs() -> TestResult:
    """Misst VRAM-Peak von einem Demucs-Run (4-Stem). Nur sinnvoll wenn
    Demucs schon installiert + Modell gecached."""
    res = TestResult(
        name="demucs",
        started_at=datetime.now().isoformat(),
        metadata={},
    )
    try:
        import torch  # type: ignore
        device = "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cpu":
            res.status = "skipped"
            res.error = "kein CUDA verfuegbar"
            res.finished_at = datetime.now().isoformat()
            return res

        res.add(_take_snapshot("demucs_before_load"))
        try:
            from demucs.pretrained import get_model
            from demucs.apply import apply_model
            import numpy as np
        except ImportError as exc:
            res.status = "skipped"
            res.error = f"demucs nicht importierbar: {exc}"
            res.finished_at = datetime.now().isoformat()
            return res

        model = get_model(name="htdemucs")
        model.to(device).eval()
        res.add(_take_snapshot("demucs_after_load"))

        # 10 s Stereo-Audio @ 44.1 kHz
        sr = 44100
        audio = (np.random.randn(2, sr * 10).astype("float32") * 0.1)
        audio_t = torch.from_numpy(audio).unsqueeze(0).to(device)
        res.add(_take_snapshot("demucs_after_input_to_device"))
        with torch.no_grad():
            stems = apply_model(model, audio_t, split=True, overlap=0.0,
                                progress=False, device=device)
        res.add(_take_snapshot("demucs_after_apply"))
        res.metadata["stems_shape"] = list(stems.shape)
        del stems, audio_t, model
        _empty_cache()
        res.add(_take_snapshot("demucs_after_unload"))
        res.status = "ok"
    except Exception as exc:
        is_oom = ("OutOfMemory" in type(exc).__name__) or ("out of memory" in str(exc).lower())
        res.status = "oom" if is_oom else "error"
        res.error = f"{type(exc).__name__}: {exc}"
        logger.error("demucs failed (%s): %s", res.status, exc)
        _empty_cache()
    res.finished_at = datetime.now().isoformat()
    return res


# --- Synthese-Markdown -------------------------------------------------------
def _format_snap(s: Snapshot) -> str:
    if s.allocated_mb is None:
        return f"  - **{s.label}** — {s.note or 'no data'}"
    return (f"  - **{s.label}** — allocated={s.allocated_mb:.1f} MB, "
            f"reserved={s.reserved_mb:.1f} MB, free={s.free_mb:.1f} MB"
            + (f" ({s.note})" if s.note else ""))


def _build_markdown(env: dict, results: list[TestResult]) -> str:
    lines = []
    lines.append(f"# Brain V3 — Phase-0-Spike: GPU-Coexistenz")
    lines.append("")
    lines.append(f"**Generiert:** {datetime.now().isoformat()}  ")
    lines.append(f"**Skript:** `scripts/spike_brain_v3_gpu_coexistence.py`  ")
    lines.append(f"**Status:** code-fix-pending-live-verification — auf User-Hardware ausgefuehrt")
    lines.append("")
    lines.append("## Umgebung")
    lines.append("")
    for k, v in env.items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")

    lines.append("## Test-Ergebnisse")
    lines.append("")
    lines.append("| Test | Status | Anmerkung |")
    lines.append("|---|---|---|")
    for r in results:
        note = r.error if r.error else (str(r.metadata.get("coexistence_possible", "")) if r.name == "coexistence" else "")
        lines.append(f"| `{r.name}` | **{r.status}** | {note} |")
    lines.append("")

    for r in results:
        lines.append(f"### `{r.name}` — {r.status}")
        lines.append("")
        lines.append(f"- Start: {r.started_at}")
        lines.append(f"- Ende:  {r.finished_at}")
        if r.error:
            lines.append(f"- Fehler: `{r.error}`")
        if r.metadata:
            lines.append(f"- Metadata:")
            for k, v in r.metadata.items():
                lines.append(f"    - {k}: `{v}`")
        if r.snapshots:
            lines.append(f"- Snapshots:")
            for s in r.snapshots:
                lines.append(_format_snap(s))
        lines.append("")

    # Synthese / Empfehlung
    lines.append("## Synthese (automatisch generiert, Hypothese)")
    lines.append("")
    coex = next((r for r in results if r.name == "coexistence"), None)
    if coex is not None:
        if coex.metadata.get("coexistence_possible") is True:
            lines.append("- CLAP + SigLIP-2 **passen gleichzeitig** in den VRAM. "
                         "Plan-Doc-02-#21 (sequenzieller Lifecycle) bleibt empfohlen "
                         "fuer Reserve, ist aber nicht zwingend. Dennoch: "
                         "Demucs + RAFT + NVENC gleichzeitig nicht getestet.")
        elif coex.metadata.get("siglip2_oom"):
            lines.append("- **Coexistenz NICHT moeglich** (OOM bei SigLIP-2-Load nach CLAP). "
                         "Plan-Doc-02-#21 (sequenzieller Modell-Lifecycle) ist **bestaetigt** "
                         "und Pflicht — Modelle muessen sequentiell mit `del` + `empty_cache()` "
                         "gehandhabt werden.")
        else:
            lines.append("- Coexistenz-Test inkonklusiv (nicht-OOM-Fehler). "
                         "Manuelle Pruefung des Logs noetig.")

    sig2 = next((r for r in results if r.name == "siglip2"), None)
    if sig2 is not None and sig2.metadata.get("batch_results"):
        lines.append("")
        lines.append("- SigLIP-2 Batch-Stufen:")
        for bs, info in sig2.metadata["batch_results"].items():
            status = info.get("status", "?")
            vram = info.get("vram_allocated_mb", "?")
            lines.append(f"    - batch={bs}: {status} (VRAM allocated: {vram} MB)")
        # Empfehlung fuer Default-Batch
        ok_batches = [int(bs) for bs, info in sig2.metadata["batch_results"].items()
                      if info.get("status") == "ok"]
        if ok_batches:
            lines.append(f"- **Empfehlung Default-Batch SigLIP-2:** "
                         f"`batch={max(ok_batches)}` (groesste OK-Stufe), "
                         f"Auto-Tuning bei OOM-Risiko zu kleineren Stufen.")

    lines.append("")
    lines.append("## Vault-Pflege (CLAUDE.md-Pflicht)")
    lines.append("")
    lines.append("Diesen Report kopieren nach:")
    lines.append("```")
    lines.append("C:\\Brain-Bug\\projects\\pb-studio\\wiki\\synthesis\\")
    lines.append(f"    gpu-coexistence-spike-{datetime.now().strftime('%Y-%m-%d')}.md")
    lines.append("```")
    lines.append("")
    lines.append("Plus Eintrag in `log.md` mit Verweis auf diesen Spike + Konsequenz "
                 "fuer Phase-2-DoD (Default-Batch + Coexistenz-Verbot/-Erlaubnis).")
    return "\n".join(lines)


# --- Main --------------------------------------------------------------------
def _collect_env() -> dict[str, Any]:
    env = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
    }
    try:
        import torch  # type: ignore
        env["torch"] = torch.__version__
        env["torch.cuda"] = str(torch.version.cuda)
        env["cuda_available"] = str(torch.cuda.is_available())
        if torch.cuda.is_available():
            env["device_name"] = torch.cuda.get_device_name(0)
            env["device_capability"] = str(torch.cuda.get_device_capability(0))
            env["total_vram_mb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 1
            )
    except Exception as exc:
        env["torch"] = f"FAIL: {exc}"
    try:
        import transformers  # type: ignore
        env["transformers"] = transformers.__version__
    except Exception as exc:
        env["transformers"] = f"FAIL: {exc}"
    return env


def _check_cuda_or_exit() -> int:
    try:
        import torch  # type: ignore
    except ImportError:
        print("FEHLER: torch nicht installiert.", file=sys.stderr)
        return 3
    if not torch.cuda.is_available():
        print("FEHLER: torch.cuda.is_available() = False — Spike sinnlos ohne GPU.",
              file=sys.stderr)
        print("Pruefe: scripts/diagnose_cuda.py", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Brain V3 Phase-0-Spike: GPU-Coexistenz und VRAM-Budget."
    )
    parser.add_argument(
        "--tests",
        type=str,
        default=",".join(DEFAULT_TESTS),
        help=f"Comma-separated. Verfuegbar: {','.join(ALL_TESTS)}. "
             f"Default: {','.join(DEFAULT_TESTS)}",
    )
    parser.add_argument(
        "--include-existing-siglip",
        action="store_true",
        help="Zusaetzlich SigLIP-1 SoViT-400M aus V1/V2-Bestand messen.",
    )
    parser.add_argument(
        "--siglip2-batches",
        type=str,
        default="1,2,4,8",
        help="Comma-separated batch sizes fuer SigLIP-2 (default 1,2,4,8).",
    )
    parser.add_argument(
        "--clap-skip-inference",
        action="store_true",
        help="CLAP nur laden, keine Inferenz (schneller, weniger Aussage).",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=str(DEFAULT_OUT_DIR),
        help=f"Output-Verzeichnis (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args()

    rc = _check_cuda_or_exit()
    if rc != 0:
        return rc

    requested = [t.strip() for t in args.tests.split(",") if t.strip()]
    if args.include_existing_siglip and "siglip_existing" not in requested:
        requested.append("siglip_existing")

    unknown = [t for t in requested if t not in ALL_TESTS]
    if unknown:
        print(f"FEHLER: unbekannte Tests: {unknown}. Verfuegbar: {ALL_TESTS}",
              file=sys.stderr)
        return 4

    try:
        batches = [int(b) for b in args.siglip2_batches.split(",") if b.strip()]
    except ValueError:
        print(f"FEHLER: --siglip2-batches muss Zahlen sein, war: {args.siglip2_batches}",
              file=sys.stderr)
        return 4

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = _setup_logging(out_dir)
    logger.info("=" * 70)
    logger.info("Brain V3 GPU-Coexistenz-Spike gestartet")
    logger.info("Output: %s", out_dir)
    logger.info("Log:    %s", log_path)
    logger.info("Tests:  %s", requested)
    logger.info("=" * 70)

    env = _collect_env()
    logger.info("Umgebung: %s", env)

    results: list[TestResult] = []

    test_funcs: dict[str, Callable[[], TestResult]] = {
        "baseline": test_baseline,
        "clap": lambda: test_clap(skip_inference=args.clap_skip_inference),
        "siglip2": lambda: test_siglip(SIGLIP2_MODEL_ID, batches, "siglip2"),
        "siglip_existing": lambda: test_siglip(
            SIGLIP_EXISTING_MODEL_ID, batches, "siglip_existing"
        ),
        "coexistence": test_coexistence_clap_siglip2,
        "demucs": test_demucs,
    }

    for name in requested:
        logger.info("")
        logger.info("--- TEST: %s ---", name)
        t0 = time.time()
        try:
            r = test_funcs[name]()
        except KeyboardInterrupt:
            logger.warning("Test %s vom User abgebrochen.", name)
            r = TestResult(
                name=name,
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                status="error",
                error="KeyboardInterrupt",
            )
            results.append(r)
            break
        except Exception as exc:
            logger.error("Test %s warf unerwartet: %s\n%s",
                         name, exc, traceback.format_exc())
            r = TestResult(
                name=name,
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
        dt = time.time() - t0
        logger.info("Test %s: status=%s (%.1f s)", name, r.status, dt)
        results.append(r)
        # Inkrementeller Flush — falls naechster Test crasht, bleiben Daten
        _flush_outputs(out_dir, env, results)

    logger.info("")
    logger.info("=" * 70)
    logger.info("Spike abgeschlossen.")
    logger.info("JSON:    %s/snapshots.json", out_dir)
    logger.info("Report:  %s/report.md", out_dir)
    logger.info("Log:     %s", log_path)
    logger.info("=" * 70)
    print()
    print(f">>> Spike-Output: {out_dir}")
    print(f">>> Naechster Schritt: report.md durchsehen, in Vault kopieren.")
    return 0


def _flush_outputs(out_dir: Path, env: dict, results: list[TestResult]) -> None:
    """Schreibt JSON + Markdown nach jedem Test-Schritt — Crash-Safety."""
    try:
        json_path = out_dir / "snapshots.json"
        payload = {
            "generated_at": datetime.now().isoformat(),
            "environment": env,
            "results": [
                {
                    **{k: v for k, v in asdict(r).items() if k != "snapshots"},
                    "snapshots": [asdict(s) for s in r.snapshots],
                }
                for r in results
            ],
        }
        json_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        md_path = out_dir / "report.md"
        md_path.write_text(_build_markdown(env, results), encoding="utf-8")
    except Exception as exc:
        logger.warning("Output-Flush failed: %s", exc)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen vom User.", file=sys.stderr)
        sys.exit(130)
