# Glossar

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19`

| Begriff | Bedeutung |
|---|---|
| **source_sha256** | Content-Hash der Quelldatei (Audio oder Video). Identitaets-Anker. |
| **Provenance** | "Wer hat was wann gemacht" — analysis_jobs + analysis_artifacts. |
| **Dedup** | Schritt mit gleichem (source_sha, step_id, step_version, params_hash) wird nicht erneut ausgefuehrt. |
| **Adapter** | Schicht die alte Pfade (`storage/stems/<track_id>/`) auf neuen globalen Lookup mappt ohne V2-Code anzufassen. |
| **Junction** | Windows-NTFS-Verzeichnis-Link, ohne Admin-Rechte. Linux: Symlink. |
| **Cross-Project-Reuse** | Datei in mehreren Projekten → Analyse-Ergebnisse wiederverwendet. |
| **File-Tracking-Repair** | Source-Datei verschoben → App findet via SHA wieder + repariert Pfade-Felder. |
| **Project-Bundle** | Export-Format mit Artefakten + Project-Metadaten. |
