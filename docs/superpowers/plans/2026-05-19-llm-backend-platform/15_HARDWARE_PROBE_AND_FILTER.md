# 15 — Hardware-Probe + Modell-Filter

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

Hardware-Information liefern und Modelle filtern die nicht laufen.

## Scope

```python
# services/llm/hardware_probe.py
@dataclass
class HardwareInfo:
    gpu_vendor: str            # "NVIDIA"
    gpu_name: str              # "GTX 1060 6 GB"
    vram_total_gb: float
    vram_free_gb: float
    cuda_compute_capability: str
    cuda_version: str
    cpu_cores: int
    ram_gb: float
    backends_installed: list[str]
    lm_studio_detected: bool
```

- Quellen: `pynvml`, `psutil`, Windows-Registry-Probe fuer LM-Studio.

```python
# services/llm/filter.py
def is_usable(candidate, hw) -> tuple[bool, str]:
    if candidate.vram_gb > hw.vram_free_gb + 0.5: return False, "VRAM"
    if candidate.format == "MLX": return False, "MLX nur Apple"
    if candidate.format == "GGUF": return True, "ok"
    if candidate.format == "safetensors" and "lmstudio_external" not in hw.backends_installed:
        return False, "safetensors braucht LM-Studio"
    return True, "ok"
```

## UI-Konsequenz

- Modell-Browser zeigt nur passende Modelle
- Optionaler Toggle "Inkompatible anzeigen" mit Grund-Tooltip

## Out of Scope

- AMD/ROCm-Pfad (Hartregel D-040 NVIDIA-only).

## Verifikation

- HardwareInfo-Liefert plausible Werte auf GTX 1060
- Filter sortiert Marketing-Mid-Range-Modelle korrekt aus
- `pytest tests/test_services/test_llm_hardware.py -v` gruen
