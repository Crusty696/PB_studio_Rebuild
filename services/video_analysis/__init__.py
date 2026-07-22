"""video_analysis — Hilfspakete fuer services/video_analysis_service.py.

AUFRAEUM B2 (konservativer God-Object-Split): entkoppelte, NICHT-GPU
Leaf-Helper werden hierher ausgelagert. Der GPU-/Modell-/Pipeline-Kern
(SigLIP, RAFT, Scene-Detection, Captioning-Loop, VectorDB) bleibt in
services/video_analysis_service.py und wird NICHT verschoben.
"""
