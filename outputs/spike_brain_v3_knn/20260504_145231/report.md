# Brain V3 — Phase-2-KNN-Scaling-Spike

**Generiert:** 2026-05-04T15:19:09.862944

## Umgebung
- **python**: 3.10.20
- **n_vectors**: 16000
- **n_queries**: 100
- **sqlite_vec**: installed

## Ergebnisse
| Bench | N vectors | Insert tot. | Insert/vec | KNN median | p95 | min | max | Plan-DoD <50 ms |
|---|---|---|---|---|---|---|---|---|
| `audio_16000` | 16000 | 771.7s | 48.23ms | **63.48ms** | 75.17ms | 51.61ms | 77.54ms | **MISSED** |
| `video_16000` | 16000 | 808.5s | 50.53ms | **108.03ms** | 145.49ms | 81.65ms | 234.42ms | **MISSED** |