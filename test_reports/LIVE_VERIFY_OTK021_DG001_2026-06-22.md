# PB Studio Live-Verify OTK-021 / DG-001 — 2026-06-22

status: BLOCKED
branch: codex/OTK-021-source-consolidation-2026-06-22

## Auftrag

Autonome Vordergrund-GUI-/GPU-Live-Verifikation nach grüner Nicht-Live-Suite.

## Preflight

| Prüfung | Ergebnis |
|---|---|
| Python | Conda `pb-studio`, Python 3.10 |
| PyTorch | `1.12.1+cu113` |
| `torch.cuda.is_available()` | `False` |
| GTX 1060 PnP | `Status: Unknown`, `CM_PROB_PHANTOM` |
| Intel UHD 620 | `OK`, bewusst nicht verwendet |
| `nvidia-smi` | keine nutzbare NVIDIA-GPU |
| FFmpeg | 6.1.1 |
| `h264_nvenc` | `CUDA_ERROR_NO_DEVICE`, Exit `-1313558101` |
| `hevc_nvenc` | `CUDA_ERROR_NO_DEVICE`, Exit `-1313558101` |

## Verdikt

`BLOCKED — GTX 1060 aktuell physisch/logisch nicht präsent.`

App-/GUI-Kampagne nicht gestartet. Grund:

- Pflichtcheckliste verlangt CUDA `cuda:0`, GTX 1060 und NVENC.
- Projekt-Hartregel verbietet Intel-iGPU, andere GPU-Backends und
  Ersatzbehauptungen über CPU.
- System-Check hätte roten GPU-Fehler; damit Vorbedingungen nicht erfüllt.

## Nicht getestet

- Projekt/Import/Analyse/SCHNITT/Export als neuer durchgehender GUI-Lauf.
- DG-001 H1/H3.
- NVENC-Export.

## Erforderliche externe Aktion

Surface-Book-2-GPU-Base/GTX1060 wieder verfügbar machen, z. B. physisch korrekt
verbinden oder Windows-/Treiberzustand durch User/Administrator reparieren.
Danach Preflight erneut:

1. `Get-PnpDevice` → GTX 1060 `OK`, `CM_PROB_NONE`
2. `torch.cuda.is_available()` → `True`
3. `nvidia-smi` → GTX 1060 / 6144 MiB
4. H.264-/HEVC-NVENC-Smoke → Exit 0

Erst dann GUI-Kampagne fortsetzen.
