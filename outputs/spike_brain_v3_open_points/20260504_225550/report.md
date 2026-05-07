# Brain V3 — Open-Points Validation Spike

**Generiert:** 2026-05-04T22:57:51.733563

## Ergebnisse
| Test | Status | Plan-DoD | Dauer | Anmerkung |
|---|---|---|---|---|
| `fmeasure` | **ok** | MET | 69.2s |  |
| `extrapolation_500` | **ok** | MET | 40.9s |  |
| `hnsw` | **partial** | MISSED | 0.1s | sqlite-vec 0.1.x ist primär Brute-Force. HNSW/ANN ist im Roadmap aber Stand 2026 |
| `demucs_coexistence` | **ok** | MET | 6.9s |  |
| `nvenc_coexistence` | **fail** | MISSED | 1.5s |  |
| `pyside6_baseline` | **ok** | MET | 0.6s | offscreen-Platform — echte App mit Display kann etwas mehr brauchen |

### `fmeasure` — ok
- Dauer: 69.2s
- Plan-DoD: **MET**
- ground_truth_boundaries_s: `[100.0, 200.0, 300.0, 400.0]`
- detected_boundaries_s: `[48.0, 211.0, 301.0, 396.0]`
- tolerance_s: `15.0`
- true_pos: `3`
- false_pos: `1`
- false_neg: `1`
- precision: `0.75`
- recall: `0.75`
- f1: `0.75`
- fallback_used: `False`
- duration_seconds: `500.0`

### `extrapolation_500` — ok
- Dauer: 40.9s
- Plan-DoD: **MET**
- n_audio_processed: `50`
- n_video_processed: `50`
- clap_total_s: `23.906039237976074`
- clap_avg_per_file_s: `0.4780266332626343`
- clap_first_file_s: `12.408744812011719`
- siglip_total_s: `14.51754641532898`
- siglip_avg_per_file_s: `0.2902504539489746`
- siglip_first_file_s: `5.191967010498047`
- extrapolated_500_clap_minutes: `3.983555277188619`
- extrapolated_500_siglip_minutes: `2.4187537829081216`
- extrapolated_500_total_minutes: `6.402309060096741`

### `hnsw` — partial
- Dauer: 0.1s
- Plan-DoD: **MISSED**
- sqlite_vec_version: `0.1.9`
- vec_functions: list[18] (gekürzt: ['vec_add', 'vec_bit', 'vec_debug'] ...)
- vec_modules: `['vec_each', 'vec0']`
- hnsw_supported: `False`
- brute_force_n1000_median_ms: `2.186050001910189`
- note: `sqlite-vec 0.1.x ist primär Brute-Force. HNSW/ANN ist im Roadmap aber Stand 2026 nicht offiziell verfügbar in vec0. Workaround für <50 ms KNN bei 16k: Pre-Filter via SQL (z.B. WHERE u.level='window') halbiert effektive Vektor-Anzahl.`

### `demucs_coexistence` — ok
- Dauer: 6.9s
- Plan-DoD: **MET**
- snapshots: `[{'label': 'baseline', 'alloc': 0.0, 'reserved': 0.0}, {'label': 'after_demucs_load', 'alloc': 161.8125, 'reserved': 184.0}, {'label': 'after_clap_loaded_with_demucs', 'alloc': 904.6005859375, 'reserved': 956.0}, {'label': 'after_demucs_inference', 'alloc': 921.96533203125, 'reserved': 1712.0}, {'label': 'after_cleanup', 'alloc': 14.0, 'reserved': 14.0}]`
- coexistence_possible: `True`
- demucs_inference_ok: `True`

### `nvenc_coexistence` — fail
- Dauer: 1.5s
- Plan-DoD: **MISSED**
- has_h264_nvenc: `True`
- has_hevc_nvenc: `True`
- nvenc_encode_5s_720p_duration_s: `0.20630908012390137`
- nvenc_encode_ok: `False`
- stderr_tail: `@ 00000248ee0fea00] Task finished with error code: -22 (Invalid argument)
[vost#0:0/h264_nvenc @ 00000248ee0fea00] Terminating thread with return code -22 (Invalid argument)
[out#0/mp4 @ 00000248ee072380] Nothing was written into output file, because at least one of its streams received no packets.
`

### `pyside6_baseline` — ok
- Dauer: 0.6s
- Plan-DoD: **MET**
- snapshots: `[{'label': 'before_qt', 'alloc': 0.00048828125, 'reserved': 16.0}, {'label': 'after_qt_window_shown', 'alloc': 0.00048828125, 'reserved': 16.0}, {'label': 'after_qt_idle', 'alloc': 0.0, 'reserved': 16.0}, {'label': 'after_qt_close_and_empty_cache', 'alloc': 0.0, 'reserved': 0.0}]`
- qt_platform: `offscreen`
- note: `offscreen-Platform — echte App mit Display kann etwas mehr brauchen`
