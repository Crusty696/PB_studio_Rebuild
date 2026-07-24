# Risks: b686-vram-coordination (Variant C)

Adversarial Review Phase 5. Read-only. Alle Fundstellen am Worktree-Code
(Branch sandbox/b686-vram-coordination) gegen echte Callsites verifiziert.

## Verdict

**iterate -> DONE (Phase 4 erneut durchlaufen).** P1 (Refcount) + P2 (resume-Reihenfolge) gefixt; P2-Tests ergaenzt; P2-Batch-Worker-Pause vom User autorisiert ("beide Worker"). Restrisiken <= P3. Ein P1 (nested/concurrent Pause ohne
Refcount) hebt den OOM-Schutz unter realistischer User-Aktion wieder auf und
kann exakt den OOM-Crash reproduzieren, den das Feature verhindern soll.
Deadlock-Sicherheit (Kern-Constraint) ist dagegen sauber — keine neue
LOAD->EXECUTION-Kante gefunden.

---

## P0 — blockers

Keine. Die Deadlock-Falle (LOAD->EXECUTION) ist statisch nicht verletzt: beide
Pause-Aufrufe liegen VOR jeder GPU-Lease (video.py:146 Batch, video.py:282
Pipeline), der Free (`_reset_embedder_cache` -> Serializer/EXECUTION) wird
vollstaendig released, bevor die erste Lease genommen wird. `_await_gate`
haelt keinen Lock (asyncio.sleep-Poll). Bestaetigt.

---

## P1 — silent regressions (zurueck zu Phase 4)

- **Nested/concurrent Pause auf gemeinsamem Binaer-Flag ohne Refcount** —
  `services/brain/embedding_scheduler.py:292-296` (`pause_embeddings`/
  `resume_embeddings` = blankes `threading.Event.set()/clear()`, kein Zaehler)
  — `workers/video.py:146` (Batch-Worker pause) + `:194` finally resume;
  `workers/video.py:282` (Pipeline pause) + `:597` finally resume.
  **Failure-Szenario (silent, nur real/parallel):** `_pause_event` ist EIN
  globales Binaer-Flag fuer den Singleton-Scheduler. Zwei Analyse-Worker
  koennen gleichzeitig laufen — der Dispatcher serialisiert NICHT
  (`ui/controllers/worker_dispatcher.py:34-37`: jeder Worker bekommt eine
  eigene QThread, sofort gestartet). Konkrete Pfade:
  1. Pipeline laeuft (langer SigLIP/RAFT-Lauf). User klickt "Video
     analysieren" -> `VideoBatchAnalysisWorker` (video_analysis.py:81); dessen
     Button ist unabhaengig, NICHT vom Pipeline-Lauf gesperrt. Batch macht nur
     Metadaten/Proxy (schnell), sein `finally` (video.py:194) ruft
     `resume_after_analysis()` -> `_pause_event.clear()` -> Gate offen, obwohl
     der Pipeline-Worker noch mitten in der Analyse steckt.
  2. Zweiter Pipeline-Entry-Point umgeht die Button-Sperre komplett:
     `ui/workspaces/media_workspace.py:1557`
     (`VideoAnalysisPipelineWorker(batch=[(video_id, title)])`) vs.
     `ui/controllers/video_analysis.py:214`. Zwei Pipeline-Worker koennen so
     ueberlappen -> erster fertiger resume oeffnet das Gate fuer den zweiten.
  Folge: gequeuete Embed-Jobs passieren das Gate, laden Embedder (~1.1 GB SigLIP-2
  + CLAP) neu resident, waehrend SigLIP-so400m + RAFT (~2.6 GB) des noch
  laufenden Workers liegen -> genau das Peak-Residenz-Szenario aus analysis.md
  -> CUDA OOM. Im Test unsichtbar (kein Concurrency-Test, keine echten Modelle).
  **Fix:** Refcount statt Binaer-Flag — Pause-Zaehler unter Lock
  (`pause` inkrementiert + set, `resume` dekrementiert, `clear` erst bei 0),
  ODER Pause aus dem Batch-Worker entfernen (siehe P2 "Plan-Deviation"; der
  Batch-Worker laedt gar kein SigLIP, analysis.md:51) UND einen App-weiten
  "nur-eine-Analyse"-Guard fuer die zwei Pipeline-Entry-Points.

---

## P2 — quality

- **Resume-Reihenfolge im Pipeline-finally invertiert** —
  `workers/video.py:597` ruft `_resume_embeddings(_scheduler)` als ERSTE
  Anweisung im finally, VOR dem RAFT-Cleanup (`:599-610`) und dem
  `ModelManager().unload()` (`:611-616`). Fenster: resume oeffnet das Gate,
  ein Embed-Job kann den Embedder-Reload starten, waehrend SigLIP+RAFT noch
  resident sind (Cleanup noch nicht gelaufen). Niedrige Wahrscheinlichkeit
  (Embed-Reload ist async + Gate-Poll 0.1 s + Modell-Load ~2 s; der
  synchrone Cleanup gewinnt praktisch immer das Rennen), aber die Reihenfolge
  widerspricht dem Feature-Ziel. **Fix:** resume ans ENDE des finally, nach
  Modell-Cleanup.

- **Plan-Deviation: Pause im Batch-Worker war nicht beauftragt** —
  `workers/video.py:146` (`VideoBatchAnalysisWorker`). plan.md Step 4 nennt
  ausschliesslich `VideoAnalysisPipelineWorker.run`; analysis.md Open Question 1
  empfahl "nur Pipeline-Worker" (Batch = reine Metadaten/Proxy, kein
  SigLIP-Load, analysis.md:51). Die Impl fuegt Pause zusaetzlich im Batch-Worker
  ein — geringer Nutzen (kein torch-VRAM-Modell), aber Wurzel des P1-Bugs
  (zweiter resume-Owner auf demselben Flag). Verstoss gegen HARTREGEL "nur
  explizit angewiesene Aenderungen". **Fix:** Batch-Worker-Pause entfernen ODER
  explizit vom User freigeben lassen.

- **Deadlock-Stress-Test testet nur ein abstraktes Modell, nicht den
  echten Code** — `tests/test_services/test_b686_vram_coordination.py:162-241`.
  `test_safe_ordering_does_not_deadlock` / `test_control_bad_ordering_deadlocks`
  nutzen ISOLIERTE `threading.RLock/Lock` (Kommentar :153-160), NICHT
  `GpuSerializer` / `GPU_EXECUTION_LOCK` / `GPU_LOAD_LOCK`. Beweist die
  Lock-Ordnungs-Theorie, faengt aber KEINE Regression, bei der der reale Free
  versehentlich innerhalb einer Lease landet (z.B. wenn jemand die Pause-Zeile
  im Worker unter eine `gpu_resource_lease` verschiebt). Reiner Design-Proof.
  **Fix:** ein Integrationstest, der `pause_for_analysis` gegen die echten
  Serializer-/ModelManager-Locks fuehrt (ohne echte Modelle), plus ein Test,
  der die Pause-Position im Worker-Source relativ zur ersten Lease per
  `inspect.getsource` verankert (wie test_video_pipeline_metadata.py es fuer
  B-287 tut).

- **Test-Luecke: kein Test fuer den P1-Concurrency-Pfad** —
  `tests/test_services/test_b686_vram_coordination.py`. Keiner der Tests
  startet zwei Worker/zwei pause-Owner gegen denselben Scheduler. Der
  wichtigste Regressionspfad ist ungetestet. **Fix:** Test "zwei parallele
  pause -> ein resume -> Gate MUSS zu bleiben".

---

## P3 — notes

- **`paused-stop`-Job liefert `None`** — `embedding_scheduler.py:365-368`:
  bei Stop waehrend Pause `progress_cb(1.0, "paused-stop"); return None`.
  Nur beim App-Shutdown relevant; pruefen, dass der Caller `None` nicht als
  leeres Embedding in die VectorDB schreibt. Geringe Auswirkung (App schliesst).
- **Latenz am run()-Start** — `pause_for_analysis` blockiert den Worker-Start,
  bis ein in-flight Embed den Serializer freigibt (bei 149-MB-Audio-Mix
  potentiell mehrere Sekunden). Beobachtbarer Analyse-Start-Delay. Akzeptabel.
- **Reload-Kosten ~2 s je Modell** nach jeder Analyse fuer den ersten
  Folge-Embed (in analysis.md:123 anerkannt). Kein Thrashing-Schutz bei
  Analyse-Serien.

---

## Checked categories

- [x] Callsite coverage — pause/resume/`_reset_embedder_cache`/
  `get_default_scheduler`/`Video*Worker` vollstaendig gegrept. Neue API
  additiv, keine Signatur-Aenderung. 2 Worker-Callsites + 2 Pipeline-Entry-
  Points (video_analysis.py:214, media_workspace.py:1557) gefunden ->
  Concurrency-Pfad (P1).
- [x] Side effects shared state — `_reset_embedder_cache` bereits von 3
  Kontexten gerufen (Stop :484, Auto-Hygiene :434, jetzt Pause :213); alle
  ausserhalb GPU-Leases, kein neuer Lock-Pfad. Singleton-Scheduler global ->
  Pause pausiert AUCH Audio-Embeds (in analysis.md anerkannt, gewuenscht).
- [x] Behavioral drift — Embed-only-Nutzer unberuehrt (Pause nur durch
  Video-Worker getriggert). Reload-Kosten + Start-Latenz (P3).
- [x] Migration/compat — keine DB-/API-/Config-Aenderung. B-554 persistente
  Instanz: durch Pause bewusst entladen + lazy neu (Kern des Designs), Factory
  unveraendert (:100-131). B-684 unload-Pfad genutzt, nicht geaendert. B-679
  oom_recovery-Kante unangetastet. AUD-35/H-25 Batch-Lock-Struktur nicht
  angefasst.
- [x] Test gaps — Concurrency-Pfad ungetestet; Stress-Test nur abstrakt (P2).
- [x] Plan logical gaps — Batch-Worker-Pause nicht im Plan (P2-Deviation);
  Open Question 1 (nur Pipeline) in der Impl ignoriert.
- [x] PB-Studio-spezifisch — Pacing/Brain-V3-Grenzen respektiert (nur
  Scheduler-API + Worker-Start/finally). GPU-Hartregel: kein Backend-Wechsel,
  nur Free/Reload auf cuda:0.
- [x] Deadlock-Restrisiko — Free liegt beweisbar vor jeder Lease; keine
  LOAD->EXECUTION-Kante. `_await_gate` lock-frei. Sauber.

---

## Recommendations

1. **P1 fixen vor Phase 6:** Refcount statt Binaer-`_pause_event`, ODER
   Batch-Worker-Pause entfernen + App-weiter Single-Analysis-Guard fuer beide
   Pipeline-Entry-Points. Ohne das reproduziert das Feature den OOM, den es
   verhindern soll.
2. **P2 Resume-Ordering:** resume ans finally-Ende (nach Modell-Cleanup).
3. **P2 Plan-Konformitaet:** Batch-Worker-Pause vom User bestaetigen lassen
   oder streichen (HARTREGEL).
4. **P2 Test scharf machen:** Integrationstest gegen echte GpuSerializer-Locks
   + Concurrency-Test (zwei pause / ein resume).
5. Live-Verify (GTX 1060, echter Parallel-Import) bleibt Pflicht — statischer
   Deadlock-Beweis ersetzt keine reale VRAM-Messung.
