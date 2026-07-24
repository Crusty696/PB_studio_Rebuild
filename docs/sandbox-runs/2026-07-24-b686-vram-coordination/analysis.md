# Analysis: b686-vram-coordination

Phase 3 (analyze). Read-only. Kein Produktivcode geaendert. Alle Zeilen unten am echten Worktree-Code verifiziert (Branch sandbox/b686-vram-coordination).

## Goal

Zwei getrennte VRAM-Eigentuemer auf der 6-GB-GTX-1060 teilen sich kein gemeinsames Residency-Budget: der ModelManager (main-Slot SigLIP-so400m ~2.5 GB + aux-Slot RAFT ~0.1 GB) und die persistenten Brain-V3-Embedder-Singletons (_VIDEO_EMBEDDER SigLIP-2 ~0.35 GB + _AUDIO_EMBEDDER CLAP ~0.74 GB). Beim Medien-Import laufen Embedding-Scheduler (submit_path) und ModelManager-Analyse (Batch-/Pipeline-Worker) parallel. Peak-Residenz (~2.6 GB ModelManager + ~1.1 GB Embedder + CUDA-Context + Fragmentierung) kann das 6-GB-Budget sprengen -> CUDA OOM. Der OOM-Schutz des ModelManagers (_handle_oom_prevention / _ensure_vram_for_model) kann nur die EIGENEN Slots entladen, nicht die Embedder. Ziel: Embedder-Residenz waehrend der schweren ModelManager-Analyse kontrolliert freigeben -- beweisbar ohne neue Lock-Inversion.

## Acceptance criteria

- [ ] Waehrend laufender ModelManager-Video-Analyse (Batch/Pipeline) sind die persistenten Brain-V3-Embedder NICHT VRAM-resident.
- [ ] Kein neuer Lock-Inversions-Pfad: GPU_LOAD_LOCK -> GPU_EXECUTION_LOCK darf niemals entstehen, solange die Gegenkante GPU_EXECUTION_LOCK -> GPU_LOAD_LOCK (oom_recovery) existiert.
- [ ] Bestandsfixes intakt: B-684 (Serializer im Embedder-unload), B-679 (oom_recovery unload_scope=aux), B-554 (persistente Embedder), B-194 (aux-Slot), AUD-35 / H-25 (Batch-Lock-Struktur).
- [ ] GPU-Hartregel: nur GTX 1060 / cuda:0, kein neuer GPU-Backend.
- [ ] Concurrency-Stress-Test (paralleler Embed-Submit + Batch-Analyse) laeuft wiederholt ohne Deadlock/Timeout durch.

## Current state

### Lock-Inventar (verifiziert)

| Lock | Typ | Ort | Semantik |
|---|---|---|---|
| GPU_LOAD_LOCK | RLock | model_manager.py:33 | serialisiert Modell-Load/Unload |
| GPU_EXECUTION_LOCK | RLock | model_manager.py:38 | serialisiert GPU-Inferenz |
| ModelManager._swap_lock | RLock | model_manager.py:311 | Slot-State (main/aux) |
| GpuSerializer._lock | Lock (non-reentrant) | gpu_serializer.py:54 | Brain-V3 GPU-Workloads |
| _EMBEDDER_CACHE_LOCK | Lock | embedding_scheduler.py:61 | Embedder-Singleton lazy-init |

Bruecke: GpuSerializer.acquire() nimmt ZUERST den legacy GPU_EXECUTION_LOCK (gpu_serializer.py:76-82), DANN den eigenen non-reentranten _lock (:84). D.h. jeder Embedder-Pfad (embed + unload) laeuft effektiv unter GPU_EXECUTION_LOCK.

### Kanonische Lock-Ordnung im Bestand

- gpu_resource_lease (model_manager.py:108-117): EXECUTION dann LOAD -- bewusst stabile Reihenfolge.
- ensure_loaded (model_manager.py:1022): gpu_resource_lease -> load_*.
- generate_embeddings (video_analysis_service.py:527): nimmt NUR GPU_LOAD_LOCK um load_siglip; Inferenz (:564) unter GPU_EXECUTION_LOCK.
- oom_recovery (model_manager.py:232): nimmt beim Retry GPU_LOAD_LOCK. Dekoriert generate_embeddings (:485) und _raft_motion_score (:175), die UNTER GPU_EXECUTION_LOCK laufen -> Kante EXECUTION -> LOAD.

### Die Deadlock-Falle (bestaetigt, DARF NICHT verletzt werden)

Naheliegender Fix "Embedder aus dem ModelManager-Load-Pfad freigeben" = Zwei-Thread-Deadlock:

- Thread A (Load): haelt GPU_LOAD_LOCK (generate_embeddings:527 / ensure_loaded), ruft Embedder-Free -> serializer.acquire -> GPU_EXECUTION_LOCK. Neue Kante LOAD -> EXECUTION.
- Thread B (Inferenz): haelt GPU_EXECUTION_LOCK (embed/RAFT-Inferenz), OOM -> oom_recovery nimmt GPU_LOAD_LOCK. Bestehende Kante EXECUTION -> LOAD.
- Gegenlaeufige Kanten in zwei Threads -> Deadlock im Modell-Lade-Pfad.

Zentrale Constraint: Jede Loesung muss beweisbar frei von der neuen Kante LOAD -> EXECUTION sein. Erreicht, indem der Embedder-Free AUSSERHALB jedes gehaltenen GPU-Locks passiert (weder LOAD noch EXECUTION gehalten, wenn der Free seinen Serializer/EXECUTION-Lock nimmt).

### Sichere Ankerpunkte (verifiziert)

- workers/video.py VideoAnalysisPipelineWorker.run() (Z.187): START haelt KEINEN GPU-Lock. Erste Lease erst Z.303 (gpu_resource_lease "video batch preload"), Batch-Loop-Lease Z.330 (gpu_execution_lease "video_analysis_batch"). Zwischen 326 und 330 kleine Lock-freie Luecke (Embed-Job koennte hier Serializer greifen + Embedder neu laden -> Fenster, das eine Pause schliesst).
- workers/video.py VideoBatchAnalysisWorker.run() (Z.111): reine Metadaten/Proxy-Analyse via VideoAnalyzer.analyze_and_store. Kein SigLIP/RAFT-Load, kein GPU-Lease am run()-Start. (Nur relevant, falls Koordination auch hier gewuenscht -- VRAM-kritischer Pfad ist der Pipeline-Worker.)
- embedding_scheduler.py: hat request_stop + submit_path, aber KEIN pause/resume. _reset_embedder_cache(unload=True) (Z.66) gibt beide Embedder frei (nimmt via emb.unload() -> B-684 den Serializer).
- Embedder-Residenz entsteht INNERHALB serializer.acquire: embed_clip (video_embedder.py:180) haelt den Serializer und ruft DANN _ensure_loaded (:181) -> Modell wird unter dem Serializer resident. Folge: solange ein anderer Thread GPU_EXECUTION_LOCK durchgehend haelt (Batch-Loop Z.330), kann kein Embed-Job den Embedder neu laden.

### Datenfluss beim Import (verifiziert)

import_media.py:_on_hash_registered_for_embedding (UI-Thread, QueuedConnection) -> scheduler.submit_path (embedding_scheduler.py:196) -> Job in asyncio-Queue im _SchedulerThread -> _execute_embedding (:310) -> run_in_executor -> _default_embedder_factory -> embed_clip/embed_mix unter Serializer. Parallel: video_analysis.py:_start_video_pipeline (:214) -> VideoAnalysisPipelineWorker.

## Variants

Alle drei platzieren den Embedder-Free am run()-Start VOR jeder GPU-Lease -- der gemeinsame, deadlock-entscheidende Kern.

### Variant A -- Nur Embedder-Free am run()-Start (kein Pause-Flag)

Approach: Am Anfang von VideoAnalysisPipelineWorker.run() (vor Z.303), solange noch kein GPU-Lock gehalten wird, _reset_embedder_cache(unload=True) aufrufen (best-effort). Kein finally-Zusatz. Embedder einmalig freigegeben; Scheduler kann sie danach jederzeit neu laden.

Files touched: workers/video.py (run()-Start). Optional Import embedding_scheduler._reset_embedder_cache.

Lock-Ordering-Beweis: Free laeuft, BEVOR irgendeine Lease genommen wird. Er nimmt serializer.acquire -> GPU_EXECUTION_LOCK (acquire+release), gibt ihn vollstaendig frei, BEVOR gpu_resource_lease (EXECUTION->LOAD) genommen wird. Kein Zeitpunkt haelt LOAD, waehrend EXECUTION angefordert wird. Keine LOAD->EXECUTION-Kante. Deadlock-sicher.

Trade-offs: Schwacher OOM-Schutz. Residuales Fenster: nach dem Free kann ein gequeueter Embed-Job in der Luecke 326->330 den Serializer greifen und die Embedder (~1.1 GB) neu resident machen, waehrend SigLIP+RAFT (~2.6 GB) liegen -> OOM weiter moeglich. Kein Thrashing-Schutz. Minimal-invasiv (S).

Effort: S. Risk: P1 (loest OOM nicht zuverlaessig). Reversibel: easy.

### Variant B -- Pause/Resume-Gate im Scheduler

Approach: Neues pause()/resume() auf EmbeddingScheduler + _SchedulerThread via threading.Event (run-gate). _execute_embedding (async, :310) prueft das Gate VOR dem Dispatch an den Executor und wartet (asyncio-Poll, stop-unterbrechbar), solange pausiert -- Factory/_ensure_loaded wird nie erreicht, kein Embedder geladen. pause() setzt zusaetzlich _reset_embedder_cache(unload=True). resume() oeffnet das Gate. Aufruf aus run(): pause() am Start (vor jeder Lease), resume() im finally.

Files touched: services/brain/embedding_scheduler.py (pause/resume + Gate-Check), workers/video.py (run()-Start + finally).

Lock-Ordering-Beweis: pause() = Event.set/clear (kein GPU-Lock) + _reset_embedder_cache (serializer -> EXECUTION acquire+release, kein anderer Lock gehalten). Am run()-Start VOR jeder Lease -> wie A: kein LOAD gehalten. Gate im Scheduler-Thread wartet per asyncio.sleep, haelt dabei KEINEN Lock. Keine LOAD->EXECUTION-Kante. Deadlock-sicher.

Trade-offs: Schliesst das Residuum von A (Gate verhindert Neu-Laden waehrend der gesamten Analyse). Mehr Komplexitaet (neue API + Gate-Loop). Testbar via EmbeddingScheduler(embedder_factory=fake) (test_brain_v3_embedding_scheduler.py). Latenz: Embeddings pausieren fuer die Analyse-Dauer (gewuenscht). Risiko: wenn resume() im Fehlerpfad ausbleibt, verhungert die Embed-Queue (mitigierbar via striktem finally + optionalem Watchdog).

Effort: M. Risk: P2 (Resume-Vergessen). Reversibel: easy (additiv).

### Variant C -- Kombination: Free am run()-Start + Pause/Resume-Gate (EMPFOHLEN)

Approach: Wie B, aber Reihenfolge im Worker explizit: pause() (setzt Gate) -> Free residenter Embedder (in pause() gekapselt) -> Analyse -> finally: resume(). Free am Start beseitigt liegende Residenz sofort; Gate haelt sie fern bis resume(). Waehrend der gesamten schweren Analyse garantiert kein Embedder resident; die 326->330-Luecke geschlossen, weil gequeuete Jobs am Gate haengen statt den Serializer zu greifen.

Files touched: identisch zu B -- services/brain/embedding_scheduler.py + workers/video.py.

Lock-Ordering-Beweis: siehe B. Free und Gate-Setzen beide ausserhalb jeder GPU-Lease. Der einzige EXECUTION-Lock-Zugriff im Koordinationspfad (der Free) wird vollstaendig released, bevor die erste Lease (und damit je LOAD) genommen wird. Kein Thread haelt jemals LOAD, waehrend er EXECUTION anfordert. Keine neue Inversion.

Trade-offs: Staerkster OOM-Schutz bei gleicher Deadlock-Sicherheit. Minimal groesserer Diff als A. Gleiche Resume-Sorge wie B, mit finally beherrschbar.

Effort: M. Risk: P2. Reversibel: easy.

### Nicht empfohlen: Lease-Merge (Sub-Option)

gpu_execution_lease durchgehend von vor dem Preload bis Batch-Ende halten (Luecke 326->330 eliminieren). Deadlock-technisch ok, aber fasst die verifizierte AUD-35/H-25/B-684-Struktur an (hoeheres Regressionsrisiko) und schliesst das Fenster VOR der ersten Lease nicht. Verworfen zugunsten C.

## Recommendation

Variant C. Begruendung in Prioritaetsreihenfolge:

1. Deadlock-Sicherheit (oberstes Kriterium): identisch sicher wie A/B -- der Free liegt beweisbar ausserhalb jedes gehaltenen GPU-Locks, keine LOAD->EXECUTION-Kante. Einziger Weg, der die dokumentierte Falle nicht ausloest.
2. Wirksamkeit gegen OOM: nur C garantiert, dass waehrend der GESAMTEN Analyse kein Embedder resident wird (Free + Gate). A hat ein reales Residuum; B ohne expliziten Start-Free wuerde eine bereits laufende Residenz erst nach dem naechsten Job-Ende los.
3. Minimalitaet / Bestandsschutz: C aendert nur additive API im Scheduler und zwei Stellen im Worker (Start + finally). Kein Eingriff in ModelManager-Lock-Pfade, gpu_resource_lease, oom_recovery, Serializer oder die AUD-35/H-25-Batch-Struktur. B-684/B-679/B-554/B-194 bleiben unangetastet.

Ehrliche Einschraenkung: Kein Variant ist ohne Live-Verify fixed. Die Deadlock-Sicherheit ist statisch beweisbar (Lock-Ordering), aber der tatsaechliche OOM-Schutz haengt an realer VRAM-Messung auf der GTX 1060 unter echtem Parallel-Import -- gehoert in Phase 5 (verify).

### Acceptance-Kriterien vs. Variant C

- [x] Embedder nicht resident waehrend Analyse -- Free + Gate.
- [x] Keine neue Lock-Inversion -- Free ausserhalb aller Leases (statischer Beweis).
- [x] Bestandsfixes intakt -- nur additive Scheduler-API + Worker-Start/finally.
- [x] GPU-Hartregel -- keine Backend-Aenderung, nur Freigabe/Reload auf cuda:0.
- [~] Concurrency-Stress ohne Deadlock -- Design deadlock-frei; Nachweis via Stress-Test in Phase 5 (siehe plan.md).

## Cross-Team-Abhaengigkeiten

- ML/GPU: Kern der Aenderung. VRAM-Budget GTX 1060 6 GB. Embedder (SigLIP-2/CLAP) temporaer entladen + lazy neu geladen -> nach jeder Analyse zahlt der erste Embed-Job einen einmaligen Reload (~2 s je Modell, vgl. B-554). Akzeptabel gegen OOM-Crash.
- Threads: Scheduler-QThread (asyncio-Loop) + Worker-QThread. Gate cross-thread via threading.Event (thread-safe). request_stop muss Gate-Warten unterbrechen (stop hat Vorrang).
- Audio: CLAP-Embedder (_AUDIO_EMBEDDER) wird mit-entladen; Audio-Embeds pausieren waehrend Video-Analyse. Keine API-Aenderung an Audio-Pfaden.
- Video/Pacing/Platform: keine direkte Beruehrung.

## Open questions for user

1. Koordination NUR fuer VideoAnalysisPipelineWorker (SigLIP+RAFT), oder auch VideoBatchAnalysisWorker (reine Metadaten/Proxy, kein SigLIP-Load)? Empfehlung: nur Pipeline-Worker -- dort liegt das VRAM-Risiko.
2. resume() zusaetzlich mit Watchdog-Timeout (falls Fehlerpfad finally umgeht), oder reicht striktes try/finally im Worker? Empfehlung: finally genuegt, Watchdog optional.
3. Freigabe auch des CLAP-Audio-Embedders erwuenscht (~0.74 GB, groesserer Brocken)? Default in C: ja, beide via _reset_embedder_cache.
