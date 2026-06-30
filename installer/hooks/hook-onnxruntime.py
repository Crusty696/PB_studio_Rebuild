# installer/hooks/hook-onnxruntime.py
# PB Studio uses ONNX Runtime CUDAExecutionProvider, not TensorRT.

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs


binaries = [
    entry for entry in collect_dynamic_libs('onnxruntime')
    if Path(str(entry[0])).name != 'onnxruntime_providers_tensorrt.dll'
]
