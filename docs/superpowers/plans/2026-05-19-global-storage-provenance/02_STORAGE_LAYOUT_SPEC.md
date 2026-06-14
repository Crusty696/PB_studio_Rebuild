# 02 — Storage-Layout-Spec (Content-Address)

> Plan: `GLOBAL-STORAGE-PROVENANCE-2026-05-19` — Tier 1
> Status: code-complete-tests-green · 2026-06-14

## Layout

```
%APPDATA%/PBStudio/storage/
├── by_sha/
│   └── <source_sha256[0:2]>/<source_sha256>/
│       ├── meta.json                     # original_path_seen + duration + format
│       ├── audio/                        # V2-Stems werden hier referenziert via Junction
│       │   ├── stems/vocals.flac
│       │   ├── beats.json
│       │   ├── sections.json
│       │   └── ...
│       └── video/                        # Plan-A-Outputs referenziert via Junction
│           ├── scenes.json
│           ├── keyframes/
│           ├── embeddings.npy
│           ├── motion.json
│           ├── captions.json
│           └── proxy.mp4
└── _legacy/
    └── ...                               # alte project-local Layouts (V2)
```

## Migrations-Strategie

- **Keine physische Verschiebung** von V2-Stems anfangs.
- Junction (Windows) / Symlink (POSIX) **von** `by_sha/<sha>/audio/stems/` **nach** `storage/stems/<track_id>/`.
- Pfad-Lookup via `analysis_artifacts.path`.
- Spaeter optional: physische Verschiebung als User-getriggerte Migration.

## Out of Scope

- Cloud-Storage (Hartregel D-026).

## Verifikation

- Junction-Resolution funktioniert (V2 schreibt project-lokal, by_sha-Pfad findet Datei via Junction)
- `pytest tests/test_services/test_storage_layout.py -v` gruen

## Progress 2026-06-14

- Implementiert `services/storage_provenance/layout.py`.
- `StorageLayout` erzeugt `by_sha/<prefix>/<source_sha256>/audio|video`.
- `create_directory_link()` nutzt Windows Junction (`mklink /J`) oder POSIX Symlink.
- Testpfad: `tests/test_services/test_storage_layout.py`.
- Verifiziert: fokussierte Provenance/Layout-Tests `6 passed`; py_compile gruen.
- Kein `fixed` Marker. Kein Produkt-Live-Verify.
