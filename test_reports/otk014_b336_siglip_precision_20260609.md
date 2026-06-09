# OTK-014/B-336 SigLIP Precision Benchmark

Date: 2026-06-09
Command:

```powershell
& 'C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe' tools\diag_b336_siglip_precision.py --batch 2
```

Hardware:

```text
GPU: NVIDIA GeForce GTX 1060
capability=(6, 1)
Model: google/siglip-so400m-patch14-384
batch=2
```

Result:

| dtype | shape | NaN | Inf | emb norm mean | peak alloc | peak reserved |
|---|---:|---:|---:|---:|---:|---:|
| fp16 | (2, 1152) | 0 | 0 | 22.2979 | 1.805 GB | 1.863 GB |
| fp32 | (2, 1152) | 0 | 0 | 22.3002 | 3.440 GB | 3.900 GB |

Conclusion:

```text
fp16: keine NaN/Inf.
fp16 saves ~1.635 GB allocated VRAM vs fp32 for this benchmark.
Existing fp16 + NaN-Guard + fp32 fallback is the verified B-336 policy.
```
