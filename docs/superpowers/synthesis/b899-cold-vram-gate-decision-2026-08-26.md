# STAB-4 / B-899 Kalt-VRAM-Gate — Entscheidungsbeleg

Datum: 2026-08-26
Status: agent-complete-await-user-marker

## Reproduzierter Befund

GTX 1060/cuda:0, gepinnter PB-Studio-Conda-Stack, echter `htdemucs`-Load und
10-s-CUDA-Inferenz in isoliertem Prozess:

- Kalt: global 0 MiB.
- Peak: global 1548 MiB; Torch allocated 187,880,960 B, reserved 968,884,224 B.
- Cleanup: alle Modell-/Tensorreferenzen geloescht, GC, doppeltes
  `torch.cuda.empty_cache()`.
- Danach: global 624 MiB; Torch allocated 0 B, reserved 0 B.
- `torch.cuda.ipc_collect()` unveraendert 624 MiB.
- Gepinntes torch 1.12.1 besitzt `_cuda_clearCublasWorkspaces` nicht.
- Erst Prozessende: global 0 MiB.

App-B-723 hatte 338 -> 1151 MiB, also +813 MiB. Isolierter Lauf beweist:
mindestens 624 MiB stammen aus prozessgebundenem CUDA/cuDNN-Kontext ohne
lebende Torch-Allokationen. Das aktive +512-MiB-Gate ist unter In-Process-
Demucs nicht erreichbar.

## Entscheidung

1. Demucs-Out-of-Process: Prozessende gibt Kontext frei; groesserer Umbau von
   Worker-, Cancel-, Progress-, Fehler- und Outputvertrag.
2. In-Process-Gate an hardware-/stackgemessenen Kontextrest anpassen;
   Acceptance Criteria werden bewusst geaendert.

Agent entscheidet weder Architektur noch Gate selbst. B-774-Realbeleg bleibt
nach dieser Entscheidung separat offen.

## Userentscheidung

D-093: In-Process-Gate `Baseline +1024 MiB`; kein Demucs-Prozessumbau.
Zusatzkontrollen allocator/reserved 0/0, kein Wiederholungswachstum, keine
Zombies. Gezielter Wiederholungsbeleg folgt im naechsten Abschnitt.

## Wiederholungsbeleg

Zwei echte htdemucs-Zyklen im selben Prozess: Baseline 402 MiB, beide Peaks
1944 MiB, beide Cleanup-Werte 1020 MiB (+618). Torch allocated/reserved nach
beiden Zyklen 0/0; kein Wachstum. Prozessende: 396 MiB, keine passenden
Prozessreste. D-093-Gate agentseitig bestanden; Usermarker offen.
