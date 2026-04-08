# PB Studio Error Handling Guide

## Overview

PB Studio uses a hierarchical exception system with domain-specific error types. All custom exceptions inherit from `PBStudioError`, which provides structured error context through the `details` dictionary.

## Exception Hierarchy

```
PBStudioError (base)
├── AudioError
│   ├── AudioLoadError
│   ├── StemSeparationError
│   └── BeatDetectionError
├── VideoError
│   ├── FrameExtractionError
│   ├── EmbeddingError
│   ├── SceneDetectionError
│   └── VideoAnalysisError
├── GPUError
│   ├── CUDANotAvailableError
│   ├── VRAMInsufficientError
│   └── CUDAOutOfMemoryError
├── MLError
│   ├── MLModelNotFoundError
│   └── MLUnavailableError
├── LLMError
│   └── OllamaError
│       ├── OllamaNotAvailableError
│       ├── OllamaModelNotFoundError
│       └── OllamaPausedError
├── DatabaseError
│   ├── DatabaseLockedError
│   └── MigrationError
├── ExportError
├── ConversionError
├── FFmpegError
│   └── FFmpegTimeoutError
├── TimelineError
├── ProjectError
└── WorkerError
```

## Best Practices

### 1. Use Specific Exceptions

**❌ Bad:**
```python
raise RuntimeError("Audio file not found")
raise ValueError("Invalid BPM")
```

**✅ Good:**
```python
raise AudioLoadError("Audio file not found", details={"path": audio_path})
raise BeatDetectionError("Invalid BPM", details={"bpm": bpm, "min": 20, "max": 300})
```

### 2. Include Context in `details`

The `details` dictionary provides structured error context for logging and debugging:

```python
raise VRAMInsufficientError(
    operation="SigLIP embedding",
    required_gb=4.0,
    available_gb=2.5
)
```

### 3. Chain Exceptions Properly

Use `from e` to preserve the exception chain:

```python
try:
    result = model.process(data)
except torch.cuda.OutOfMemoryError as e:
    raise CUDAOutOfMemoryError("Embedding generation") from e
```

### 4. Catch Specific Exceptions

**❌ Bad:**
```python
try:
    process_audio(track)
except Exception as e:  # Too broad!
    logger.error(f"Error: {e}")
```

**✅ Good:**
```python
try:
    process_audio(track)
except AudioLoadError as e:
    logger.error(f"Could not load audio: {e}")
    return Result.err(str(e))
except StemSeparationError as e:
    logger.warning(f"Stem separation failed, using original: {e}")
    return Result.fallback(original_audio, reason=str(e))
except CUDAOutOfMemoryError as e:
    logger.error(f"GPU out of memory: {e}")
    return Result.err("Insufficient GPU memory")
```

### 5. Use Result Pattern for Expected Failures

For operations that can fail as part of normal flow (e.g., optional ML features), use the `Result` pattern instead of exceptions:

```python
from services.errors import Result

def detect_beats(audio_path: str) -> Result[list[float]]:
    try:
        beats = beat_detector.analyze(audio_path)
        return Result.ok(beats)
    except BeatDetectionError as e:
        logger.warning(f"Beat detection failed: {e}")
        return Result.err(str(e))
```

## Error Recovery Patterns

### GPU Memory Recovery

```python
try:
    result = heavy_gpu_operation()
except CUDAOutOfMemoryError as e:
    logger.warning(f"GPU OOM, falling back to CPU: {e}")
    torch.cuda.empty_cache()
    result = cpu_fallback_operation()
```

### Model Availability Graceful Degradation

```python
try:
    embeddings = siglip_model.encode(frames)
except MLModelNotFoundError as e:
    logger.warning(f"SigLIP not available: {e}")
    raise MLUnavailableError(
        feature="visual_similarity",
        reason="SigLIP model not downloaded",
        fallback="scene_detection_only"
    )
```

### FFmpeg Error Handling

```python
try:
    convert_video(input_path, preset="master")
except FFmpegTimeoutError as e:
    logger.error(f"Conversion timeout: {e}")
    # Retry with lighter preset
    convert_video(input_path, preset="edit_proxy")
except FFmpegError as e:
    logger.error(f"FFmpeg failed (rc={e.returncode}): {e.stderr[:200]}")
    raise ConversionError(f"Video conversion failed: {e}", input_file=input_path)
```

## Migration from Generic Exceptions

### Phase 1: Extend hierarchy (✅ Complete)
- Added missing exception types: LLM, Migration, Worker, Timeline, Conversion

### Phase 2: Refactor services (✅ Complete)
- `ollama_client.py` → OllamaError hierarchy
- `database/migrations.py` → MigrationError
- `convert_service.py` → FFmpegError/ConversionError

### Phase 3: Remaining files
The following files still use generic exceptions and should be refactored:
- `workers/*.py` → WorkerError
- `services/video_service.py` → VideoError/VideoAnalysisError
- `services/timeline_service.py` → TimelineError
- `services/project_manager.py` → ProjectError
- `services/beat_analysis_service.py` → BeatDetectionError/AudioError

### Phase 4: Exception handler updates
Replace broad `except Exception:` blocks (14 files) with specific exception types.

## Testing Error Handling

When writing tests, verify both success and error paths:

```python
def test_audio_load_error():
    with pytest.raises(AudioLoadError) as exc_info:
        audio_service.load_track("nonexistent.wav")
    assert "not found" in str(exc_info.value).lower()
    assert exc_info.value.details["path"] == "nonexistent.wav"
```

## Logging Recommendations

Use appropriate log levels:
- `logger.error()` - Unexpected errors that require attention
- `logger.warning()` - Expected failures with fallbacks (e.g., NVENC → CPU)
- `logger.info()` - Successful recoveries
- `logger.debug()` - Detailed error context

Include exception details in logs:
```python
except MLModelNotFoundError as e:
    logger.error(
        "Model not found: %s (model_id=%s, hint=%s)",
        e, e.model_id, e.details.get("hint", "")
    )
```
