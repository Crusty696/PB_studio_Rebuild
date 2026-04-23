"""PB Studio Background Workers Package — lazy imports to avoid loading librosa at startup.

LOW-13 AUDIT: Verwendet __getattr__-basiertes Lazy-Import-Pattern.
Worker-Klassen werden erst bei erstem Zugriff importiert, was den
App-Start um ~3-5s beschleunigt (kein librosa/torch Import bei init).
Fuer IDE-Autocompletion: __all__ enthaelt alle verfuegbaren Klassen.
"""

# Lazy import mapping: class name -> submodule
_WORKER_MODULES = {
    "CancellableMixin": ".base",
    "AnalysisWorker": ".analysis",
    "WaveformAnalysisWorker": ".analysis",
    "VideoAnalysisWorker": ".video",
    "VideoBatchAnalysisWorker": ".video",
    "VideoAnalysisPipelineWorker": ".video",
    "VisionAnalysisWorker": ".video",
    "FrameExtractWorker": ".video",
    "StemSeparationWorker": ".audio",
    "AutoDuckingWorker": ".audio",
    "ExportWorker": ".import_export",
    "PreviewExportWorker": ".import_export",
    "FolderImportWorker": ".import_export",
    "BatchConvertWorker": ".import_export",
    "ProxyCreationWorker": ".import_export",
    "AutoEditWorker": ".edit",
    "SemanticSearchWorker": ".edit",
    "KeyDetectionWorker": ".audio_analysis",
    "LUFSAnalysisWorker": ".audio_analysis",
    "AudioClassifyWorker": ".audio_analysis",
    "SpectralAnalysisWorker": ".audio_analysis",
    "StructureDetectionWorker": ".audio_analysis",
}

__all__ = list(_WORKER_MODULES.keys())


def __getattr__(name: str) -> object:
    if name in _WORKER_MODULES:
        import importlib
        module = importlib.import_module(_WORKER_MODULES[name], __package__)
        return getattr(module, name)
    raise AttributeError(f"module 'workers' has no attribute {name!r}")
