# Handoff — Ollama-Bundling + Release-Packaging (2026-07-09)

> Zustand beim Session-Ende. Nachfolge-Agent: dies + `log.md` im Vault zuerst lesen.
> `status: fixed` setzt NUR der User.

## ✅ ABGESCHLOSSEN + gepusht (`codex/OTK-021` @ `0bc2093`)

1. **2 video_caption-Tests** auf SCHNITT-FIXPLAN-Kontrakt nachgezogen (Commit `e4b2019`).
2. **7 Packaging-Gates grün** via echtem Build+Install+GUI-Proof (kein Fake):
   - NSISBI 7069-1 beschafft (SHA256 verifiziert) → `%LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1\nsis-binary-7069-1\makensis.exe`. Nutzung via Env `PB_NSISBI_MAKENSIS`.
   - Installer gebaut, user-scope Silent-Install (`%LOCALAPPDATA%\PB Studio`, kein Admin).
   - Installed-App-GUI-Proof: „PB_studio v0.5.0 — Director's Cockpit", responsive (Commit `0bc2093`).
   - `setup/setup_complete=True` in QSettings("PBStudio","PBStudio") gesetzt (Maschine real eingerichtet).
3. **Volle Suite:** 3051 passed / 34 skipped / **0 failed** (26,5 Min).

## 🔄 IN ARBEIT — Ollama-Bundling (task_6fd145fd), NICHT abgeschlossen

**Ziel (User-Auftrag):** Ollama in den Installer bündeln (private App, kein System-Ollama vorausgesetzt).

### KRITISCHER BEFUND — Version-Ceiling
- Aktuelles Ollama **0.30.10 = NUR CPU** auf GTX 1060 + Treiber 546.33:
  `cuda_compat.go "NVIDIA driver too old ... required_driver=570 or newer"` → CPU-Fallback.
- **Ollama 0.21.2 = GPU** (empirisch verifiziert 2026-07-09): `library=CUDA compute=6.1 cuda_v12`, `ollama ps: phi3/gemma3 100% GPU`. Alle Modelle (gemma3:4b/phi3:mini/moondream) laden.
- **Treiber-Update verboten** (GPU-Hartregel pinnt 546.33) → Bundle MUSS ≤0.21.2 sein.
- Siehe Memory `reference_ollama_gpu_incompat_sb2.md` (Version-Ceiling).

### Bereits erledigt
- `pb_studio.spec`: `redist/ollama.exe` + `redist/lib` in `project_datas` (App erwartet `{sys._MEIPASS}/redist/ollama.exe`, `services/ollama_service.py:95`). **UNCOMMITTED.**
- `.gitignore`: `redist/` ergänzt. **UNCOMMITTED.**
- `redist/` (gitignored, 2,5 GB) mit **Ollama 0.21.2** vendored — nur `cuda_v12` (rocm/vulkan/cuda_v13 entfernt = GPU-Regel + MAX_PATH-Fix). Auch nach `dist/pb_studio/_internal/redist/` gespiegelt.

### VERBLEIBENDE Schritte (rein lokal, ~10 Min)
1. Reuse-Build: `PB_SKIP_PYINSTALLER=1 PB_NSISBI_MAKENSIS=<pfad> cmd /c installer\build_installer.bat`
   (packt das aktualisierte `dist/pb_studio` neu; **wurde beim Stopp mitten im NSIS abgebrochen**).
2. Reinstall: `dist\pb_studio_setup_v0.5.0.exe /S`.
3. **Verify GPU:** System-Ollama stoppen (`taskkill /F /IM "ollama app.exe" /IM ollama.exe`), App starten, Startup-Log `_internal/logs/pb_studio.log` prüfen: „Starte Ollama von …\_internal\redist\ollama.exe" + `ollama ps` = 100% GPU + `nvidia-smi` zeigt Ollama-VRAM.
4. Packaging-Tests re-run (sollten grün bleiben; Hash-Paritäten aktualisieren sich).

### Vendoring-Rezept (für frischen Checkout — redist/ ist gitignored)
- Quelle: GitHub `https://github.com/ollama/ollama/releases/download/v0.21.2/ollama-windows-amd64.zip` (~1,97 GB).
- Extrahieren, nach `redist/` kopieren: `ollama.exe` + `lib/ollama/` (dann `cuda_v13` + `vulkan` löschen, nur `cuda_v12` behalten).
- Analog wie `bin/ffmpeg.exe` (auch gitignored, muss vor Build vendored werden).

## ⚠️ Governance / Dirty-State
- **vollintegration-Worktree dirty:** `M .gitignore`, `M pb_studio.spec` (autorisierte Ollama-Bundle-Änderung). Beim Handoff committet (siehe Commit-Message).
- **Fremdänderung** (früher): `main/pb_studio.spec` hatte unstaged Doku-Kommentar (nicht von mir, Parallel-Chat) — inzwischen extern verworfen, HEAD clean.
- **Datenverlust** `outputs/6262626`/`final-check`: extern/ungeklärt, nicht mein Code.

## Lokale Artefakte (gitignored, nicht in Git)
- `dist/pb_studio_setup_v0.5.0.exe` (aktuell 0.30.10-Build vom 19:24 — CPU-Ollama) + `.nsisbin`.
- `redist/` = Ollama 0.21.2 (cuda_v12) — bereit für den finalen Build.
- Installiert unter `%LOCALAPPDATA%\PB Studio` = aktuell 0.30.10 (CPU).
