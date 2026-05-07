# Brain V3 — Phase-2-Embedder-Validation-Spike

**Generiert:** 2026-05-06T15:27:15.367054

## Umgebung
- **python**: 3.10.20
- **torch**: 1.12.1+cu113
- **cuda_available**: True
- **device_name**: NVIDIA GeForce GTX 1060
- **transformers**: 4.38.2

## Ergebnisse
| Step | Status | Dauer | Avg/File | 500-Clip-Hochrechnung | Re-Import-Hit-Rate |
|---|---|---|---|---|---|
| `clap_embedder` | **ok** | 0.3s | 0.04s | 0.3 min | 100% in 0.01s |
| `siglip_embedder` | **ok** | 0.2s | 0.03s | 0.3 min | 100% in 0.01s |

### `clap_embedder` — ok
- Dauer: 0.3s
- n_files: `1`
- model: `laion/larger_clap_music`
- files_processed: `1`
- per_file_times_s: `[0.04031848907470703]`
- avg_per_file_s: `0.04031848907470703`
- extrapolated_500_clips_minutes: `0.3359874089558919`
- cache_hits_first_pass: `1`
- cache_misses_first_pass: `0`
- re_import_hits: `1`
- re_import_total_s: `0.012651205062866211`
- re_import_hit_rate: `1.0`
- knn_self_match_distance: `None`

### `siglip_embedder` — ok
- Dauer: 0.2s
- n_files: `1`
- model: `google/siglip2-base-patch16-384`
- files_processed: `1`
- per_file_times_s: `[0.034990549087524414]`
- avg_per_file_s: `0.034990549087524414`
- extrapolated_500_clips_minutes: `0.29158790906270343`
- re_import_hits: `1`
- re_import_total_s: `0.006594181060791016`
- re_import_hit_rate: `1.0`
- knn_self_match_distance: `None`
