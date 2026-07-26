# PB Studio Bestands- und Qualitätsaufnahme — 2026-07-26

Status: Audit abgeschlossen, Produktcode unverändert, Findings offen
Baseline: `main` / `9a321dcbeb7b98febf1a13608e0ebca314228006`
Vorgängeraufnahme: `7eb4c5e`; Drift bis Baseline: 185 Dateien, +10.804/-3.080 Zeilen

## Urteil

App besitzt breite automatisierte Testabdeckung und aktuelle Default-Suite ist
grün. Releasefähigkeit ist trotzdem nicht gegeben: Current-HEAD-CI stoppt am
Linter, Hosted-Release-Pfad widerspricht Zielruntime und hat keine FFmpeg-Quelle.
Mehrere deterministisch reproduzierte Lifecycle-, Concurrency- und
Testisolation-Fehler bleiben offen. Echter kompletter Medienworkflow
Import → Analyse → SCHNITT → Export wurde mangels vorgeschriebener Medien nicht
neu live ausgeführt.

## Bestand

- 1.591 getrackte Dateien
- 1.070 Python, 386 Markdown, 50 JSON, 19 PowerShell
- 173.851 Python-Zeilen gesamt
- Runtime-Kern: 322 Python-Dateien / 101.603 LOC
- UI 103 Module; Services 181; DB 23; Worker 14; Agents 10
- Tests 639 Module; Scripts 47; Tools 19
- 19 direkte `QThread()`-Callsites
- Hotspots: `ui/timeline.py` 4.126 LOC; `main.py` 2.261 LOC,
  `main()` 804 Zeilen, `closeEvent()` 263; Pacing-Funktion 1.103 Zeilen

Hotspot-Zahlen sind Änderungsrisiko, kein Laufzeitfehler.

## Verifikation

| Gate | Ergebnis | Aussage |
|---|---:|---|
| Default-Suite | 3062 passed, 53 skipped, 3 deselected | grün; ohne live_gpu/e2e/slow |
| UI-Chunks | 647 passed | 148 Dateien, 4 Chunks, kein nativer Crash |
| UI-Fokus Agent | 15 passed | Navigation/Lifecycle-Fokus |
| Preview-Fokus | 3 passed, 1 skipped | Stale-Signal-Race nicht abgedeckt |
| Bandit `-ll` | Exit 0 | 0 Medium/High; 175 Low unter Schwellwert; Regeln ausgeschlossen |
| Ruff | 1 Fehler | F811 in `services/export_service.py:1317` |
| Migrationen | 20 passed | Alembic single head `e1f2a3b4c5d6` |
| DB/Core Fokus | 156 passed, 1 failed | stale Modelzähltest |
| GPU/Worker Fokus | 107 passed, 2 failed + 1 teardown | B-727 Testisolation |
| SigLIP Batch 8 live_gpu | PASS | GTX1060, ~698 MiB peak alloc, 22.52 s |

Current Default-Suite änderte reale ignorierte `pb_studio.db` durch B-727.
Integrity ist `ok`; Statuszeilen für Audio-IDs 99/5 wurden geschrieben.
Vorher-Snapshot fehlt, daher keine sichere Rücknahme.

## Priorisierte offene Findings

### Hoch

- B-709: Current CI rot durch Ruff F811.
- B-710: alter Preview-Thread stoppt neuen Stream; stale Frames akzeptiert.
- B-711/B-712: Python-/Clicklog-Launcher verlieren NVENC-Invarianten bzw.
  maskieren App-Exitcodes.
- B-718: Beat-This-Checkpoint ohne Hash vor torch-1.12-Deserialisierung;
  Supply-Chain-Pfad latent, keine Kompromittierung belegt.
- B-720: Release Python 3.11/cu124/abweichendes Lock; Spec verlangt ungetrackte
  FFmpeg-Binaries.
- B-722: parallele Audio-V2-Checkpoint-Writer → WinError 32, Stageverlust.
- B-723: GPU-Cleanup nach Lockfreigabe; Parallelstart reproduziert,
  nativer Crash latent.
- B-725: Copy-/CPU-Konvertierung hält globalen GPU-Lock.
- B-727: Audio-Worker-Tests schreiben reale Projekt-DB.

### Mittel

- B-713: Phantom-Task-ID nach `moveToThread`-Fehler.
- B-714: Schnitt-Worker-Ergebnis ohne Projektgeneration-Guard.
- B-715: synchrone DB-Kontextqueries im SCHNITT-Tabwechsel; Latenz ungemessen.
- B-719: Sigma-Script-Kontext/externes CDN ohne SRI/CSP; User-Payload-Pfad latent.
- B-721: Engine-/APP_ROOT-Swap trotz `create_all`-Fehler.
- B-724: spätes Worker-Error überschreibt `cancelled`.
- B-726: öffentlicher RAFT-Direktpfad ohne GPU-Execution-Lock; Hauptworker geschützt.

### Niedrig / bewusste Trade-offs

- B-716: Dock-X lässt Kontext-Toggle aktiv.
- B-717: Cockpit-SCHNITT-Pfad pusht Projekt doppelt.
- Topbar ist durch B-654 bewusst `NoFocus`; Maus/Shortcuts teilweise vorhanden,
  Tastaturzugang bleibt eingeschränkt.

## Zusätzliche bestätigte Qualitätslücken

- Audio-V2-Midstage-Cancel wird als generischer Fehler signalisiert.
- Pacing-Rerank-Fallback kann `used_brain_v3=true` protokollieren.
- `GpuSerializer.acquire_async()` besitzt Cancellation-Fenster nach
  executorbasiertem RLock-Acquire; keine Produkt-Callsite gefunden.
- Generic `"cuda"` statt explizitem `"cuda:0"` an mehreren Modellpfaden.
  Aktueller Ein-GPU-Host nutzt Gerät 0; Mehr-GPU-Fehlleitung latent.
- Dependabot ist deaktiviert; API lieferte 403. Lokales `pip-audit`/Poetry fehlt.
  OSV-Agentenanalyse wurde nicht vollständig verwertbar abgeschlossen.
- Bandit-Konfiguration schließt B101/B310/B615 aus und überspringt 11 Kandidaten.
  „Keine Schwachstellen“ wäre daraus nicht ableitbar.

## Live-Grenzen

Neu live: deterministische Qt-/Thread-/DB-/Lock-Probes, SigLIP Batch 8,
Default-/UI-/Fokustests. Historisch am 2026-07-20 sichtbar: Wizard und
Hauptfenster booteten, GTX1060/Ollama/FFmpeg bereit, sauberer Shutdown.

Nicht neu live: realer Mehrmedien-Import, Audio-V2 komplett, Videoanalyse,
Timeline/SCHNITT, Playback/Seek mit echter Datei, Export, Installer,
Clean-VM, Tag-Release. Entsprechend kein `fixed` und keine Release-Freigabe.

## Empfohlene Reihenfolge

1. B-727 Testisolation vor weiteren Vollsuiten.
2. B-709 CI und B-720 Release-Pfad.
3. B-710 Preview-Race.
4. B-722/B-723/B-725 GPU-/Concurrency-Kette.
5. B-711/B-712 Launcher.
6. Medium-/Low-Funde, danach echter Medien-E2E und Release-Gates.
