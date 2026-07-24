# Implementation plan: b686-vram-coordination (Variant C)

Ziel: Persistente Brain-V3-Embedder waehrend der ModelManager-Video-Analyse deadlock-sicher aus dem VRAM nehmen. Free am run()-Start (vor jeder GPU-Lease) + Pause/Resume-Gate im Scheduler. Phase 4 (implement) fuehrt das aus; dieses Dokument ist der geordnete Bauplan.

## Pre-checks

- [ ] Worktree unter .worktrees/b686-vram-coordination existiert, Branch sandbox/b686-vram-coordination, sauber (git status --short --branch).
- [ ] conda-Python: C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe verfuegbar, torch.cuda.is_available() == True (GTX 1060).
- [ ] Baseline erfasst in _sandbox_meta/baseline/: (a) aktueller Testlauf der Brain-V3-Scheduler-Tests gruen, (b) nvidia-smi VRAM-Idle-Snapshot.
- [ ] Session-Claim vor Edit: python tools\agent_session.py claim --agent claude --task b686 --files services/brain/embedding_scheduler.py workers/video.py

## Steps

1. **services/brain/embedding_scheduler.py::_SchedulerThread.__init__** -- Pause-Gate anlegen.
   - Warum: cross-thread Signal, dass Embeds pausieren sollen; haelt keinen GPU-Lock.
   - Code sketch:
     ```python
     self._pause_event = threading.Event()  # gesetzt = pausiert
     ```
   - Test: test_scheduler_pause_blocks_new_embeds (neu).

2. **services/brain/embedding_scheduler.py::_SchedulerThread** -- pause/resume + Gate-Wait.
   - Warum: neue Embeds duerfen die Factory/_ensure_loaded waehrend Pause NICHT erreichen; Warten haelt keinen Lock (Deadlock-sicher).
   - Code sketch (Gate-Check async, im _execute_embedding VOR run_in_executor):
     ```python
     def pause_embeddings(self) -> None:
         self._pause_event.set()

     def resume_embeddings(self) -> None:
         self._pause_event.clear()

     async def _await_gate(self) -> bool:
         # True = weiter, False = stop angefordert
         while self._pause_event.is_set() and not self._stop_event.is_set():
             await asyncio.sleep(0.1)
         return not self._stop_event.is_set()
     ```
   - In _execute_embedding (Z.310), direkt nach progress_cb(0.05,...):
     ```python
     if not await self._await_gate():
         progress_cb(1.0, "paused-stop")
         return None
     ```
   - Test: test_scheduler_pause_defers_then_resume.

3. **services/brain/embedding_scheduler.py::EmbeddingScheduler** -- Public pause()/resume(), die zusaetzlich die Embedder freigeben.
   - Warum: Koordinator (Worker) braucht eine einfache API; Free gekapselt hier, damit die Reihenfolge (Gate setzen -> Free) an einer Stelle garantiert ist.
   - Code sketch:
     ```python
     def pause_for_analysis(self) -> None:
         if self._thread is not None:
             self._thread.pause_embeddings()
         # Free residenter Embedder AUSSERHALB jeder GPU-Lease des Callers.
         # Nimmt via emb.unload() den Serializer (GPU_EXECUTION_LOCK) und
         # gibt ihn vollstaendig frei, bevor der Caller eine Lease nimmt.
         try:
             _reset_embedder_cache(unload=True)
         except Exception as exc:
             logger.warning("pause_for_analysis: Embedder-Free fehlgeschlagen: %s", exc)

     def resume_after_analysis(self) -> None:
         if self._thread is not None:
             self._thread.resume_embeddings()
     ```
   - Test: test_pause_for_analysis_unloads_embedders (mit Fake-Embedder, assert unload() gerufen).

4. **workers/video.py::VideoAnalysisPipelineWorker.run** -- Koordination am Start + finally.
   - Warum: run()-Start haelt KEINEN GPU-Lock -> hier ist der Free/pause inversions-frei. finally garantiert resume auch bei Fehler.
   - Ort: unmittelbar am Anfang von run() (vor DB-Resolve Z.195, jedenfalls VOR gpu_resource_lease Z.303). resume in einem umschliessenden try/finally, das den gesamten Analyse-Block umspannt (bis nach Z.586).
   - Code sketch:
     ```python
     _scheduler = None
     try:
         from services.brain.embedding_scheduler import get_default_scheduler
         _scheduler = get_default_scheduler()
         if _scheduler.is_running():
             _scheduler.pause_for_analysis()  # setzt Gate + free, KEIN GPU-Lock gehalten
     except Exception as exc:
         logger.warning("B-686: Embedding-Pause fehlgeschlagen (fahre fort): %s", exc)
     try:
         ... bestehender run()-Body (DB-Resolve, preload-lease, batch-lease) ...
     finally:
         if _scheduler is not None:
             try:
                 _scheduler.resume_after_analysis()
             except Exception as exc:
                 logger.warning("B-686: Embedding-Resume fehlgeschlagen: %s", exc)
     ```
   - Wichtig: pause_for_analysis() MUSS vor Z.303 (erste Lease) laufen. Der Free darf NICHT innerhalb gpu_resource_lease/gpu_execution_lease liegen -- sonst entsteht die verbotene LOAD->EXECUTION-Kante.
   - Test: Concurrency-Stress (siehe Test-Plan).

5. **services/brain/embedding_scheduler.py::request_stop / _SchedulerThread.request_stop** -- sicherstellen, dass stop das Gate-Warten aufloest.
   - Warum: falls pausiert und App schliesst, darf _await_gate nicht ewig blockieren. _stop_event wird bereits in request_stop gesetzt (Z.253-256) und im Gate-Loop geprueft -- verifizieren, kein zusaetzlicher Code noetig ausser dem is_set()-Check im Loop (Step 2).
   - Test: test_stop_during_pause_terminates (setze pause, dann request_stop, assert Thread endet < timeout).

## Test plan

Batch-Lauf (nicht pro Schritt einzeln), conda-Python.

- Unit (Scheduler, Fake-Embedder-Factory wie test_brain_v3_embedding_scheduler.py):
  - pause_embeddings -> submit_path -> Job wird NICHT ausgefuehrt (Fake-Factory NICHT aufgerufen) bis resume.
  - pause_for_analysis ruft emb.unload() auf beiden Fake-Embedder-Singletons.
  - resume_after_analysis -> gepufferter Job laeuft, Fake-Factory aufgerufen.
  - stop waehrend pause -> Thread endet innerhalb timeout_ms.
- Integration (deadlock, echte Locks, KEINE echten Modelle):
  - Stress-Test: N Iterationen, je 2 Threads -- Thread1 simuliert Worker (pause_for_analysis -> gpu_resource_lease EXEC->LOAD -> gpu_execution_lease -> resume), Thread2 simuliert Embed unter serializer.acquire + oom_recovery-artigen GPU_LOAD_LOCK-Zugriff. Assert: alle Iterationen < Wall-Clock-Deadline (z.B. 30 s), kein TimeoutError aus GpuSerializer, kein Hang. Baseline: gleiche Struktur OHNE Free-in-Lock (muss gruen), UND ein bewusst falscher Kontroll-Lauf (Free INNERHALB GPU_LOAD_LOCK) muss den Deadlock/Timeout reproduzieren -> beweist, dass der Test scharf ist.
- Live-Verify (Phase 5, echte GPU, GTX 1060):
  - Realer Import (Test-Datensatz: Video-Ordner Solo_Natur + Audio Crusty Progressive Psy Set2.mp3) parallel zu Pipeline-Analyse. nvidia-smi loggen. Assert: waehrend Analyse KEINE Embedder-Residenz (VRAM-Peak < OOM-Schwelle), kein CUDA OOM, Embeddings laufen nach Analyse-Ende weiter, Cache korrekt befuellt.

## Rollback

- Worktree-Branch verwerfen -- kein main-Impact. git worktree remove bzw. Branch loeschen.
- Aenderung ist additiv (neue Scheduler-API + zwei Worker-Stellen); kein Bestandsverhalten ueberschrieben, daher auch partieller Revert (nur Worker-Aufruf entfernen -> Scheduler-API bleibt ungenutzt/inert) moeglich.

## Done definition

- Alle Akzeptanzkriterien in verify_log.md gruen (Phase 5).
- Deadlock-Stress-Test wiederholt gruen; Kontroll-Lauf reproduziert Deadlock (Test scharf).
- Live-Import ohne OOM, Embedder waehrend Analyse nicht resident (nvidia-smi-Beleg).
- Skeptiker-Risiken <= P2. Offene Punkte: Resume-Vergessen (mit finally beherrscht), Executor-Starvation (Gate wartet async, blockiert keinen Executor-Thread).
