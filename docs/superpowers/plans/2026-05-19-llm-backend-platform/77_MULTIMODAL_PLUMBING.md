# 77 — Multimodal-Plumbing (VLM + Omni)

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

VLM bekommt Bilder, Omni bekommt Audio-Chunks. Saubere Daten-Konvertierung.

## Scope

### VLM-Input
- Frame als JPEG/PNG-Bytes → base64 → API-Payload:
  ```json
  {
    "model": "minicpm-v:8b",
    "messages": [{"role":"user","content":"...","images":["base64..."]}]
  }
  ```
- Mehrere Bilder pro Request unterstuetzt (Modell-abhaengig).
- Vorab-Resize wenn Modell-spezifisches Max (z. B. 1344 px) ueberschritten.

### Omni-Input
- Audio-Chunk-Format: WAV PCM 16 kHz Mono, base64.
- Chunk-Groesse: 30 s max (Modell-spezifisch).
- Zeitstempel-Metadaten als Text-Begleit-Message.

### Datenfluss

- Caller liefert Path zu Frame / Audio.
- Plumbing-Layer:
  - liest Datei
  - normalisiert
  - encoded base64
  - baut Payload
- Streaming-Response wird normal verarbeitet.

## Out of Scope

- Frame-Extraction aus Video — gehoert in Plan A (Video-Pipeline).

## Verifikation

- VLM Caption-Test mit Test-Bild
- Omni Audio-Test mit Test-WAV (5 s)
- `pytest tests/test_services/test_llm_multimodal.py -v` gruen
