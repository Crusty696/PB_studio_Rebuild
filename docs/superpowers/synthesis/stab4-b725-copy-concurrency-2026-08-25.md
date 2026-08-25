# STAB-4 / B-725 Copy-Konvertierung neben GPU-Arbeit

Datum: 2026-08-25
Status: agent-complete; kein neuer Codefix

## Echter Produktpfad

- PB-Studio-Dialog `Videos standardisieren` real geoeffnet.
- Container per UIA Value-Pattern exakt `mp4 (Kopieren/Copy)`; Controller-
  Mapping damit `vcodec='copy'`.
- Erster kompletter Realbatch: 109/112 lokale Quellen remuxt; drei Quellen
  fehlten bereits. Zwei Stichproben per ffprobe parsebar, Video-Codecs H.264
  und HEVC unveraendert.
- Zweiter Lauf: Copy-Batch gestartet, unmittelbar danach htdemucs-Stems auf
  GTX 1060/cuda:0 gestartet. Waehrend `Chunk 1/12` lief gleichzeitig echter
  FFmpeg PID 7732. Damit belegt: Copy-Pfad haelt GPU_EXECUTION_LOCK nicht.
- Beide laufenden Tasks ueber TASKS abgebrochen. TASKS zeigt Video Convert
  `Abbruch`; kein FFmpeg-Rest; Stem-Analysis kanonisch cancelled; App
  responsiv; DB quick_check ok.

## Kleinste Regression

`tests/test_workers/test_b725_cpu_codec_no_gpu_lock.py` plus
`tests/test_workers/test_b401_batch_convert_cancel.py`: `3 passed in 0.83s`.

## Lokale Testartefakte

Vor beiden Laeufen existierten 0 `_std.mp4`-Outputs. Loeschung wurde vom
Tool vor Ausfuehrung blockiert; deshalb 142 reine Testoutputs recoverable in
vier sibling-Quarantaeneverzeichnisse verschoben (`converted_b725_quarantine_*
20260825`), zusammen rund 1.4 GB. Aktive `converted/*_std.mp4`: 0. Quellen
unveraendert; nichts committed.

## Urteil

B-725-Verhalten agentseitig live belegt; Vault-Userstatus `fixed` blieb
unangetastet. STAB-4-Kalt-VRAM-Gesamtgate aus B-723 bleibt separat rot.

Naechster Task:
`STAB-4 / B-726 oeffentlichen RAFT-Direktpfad unter Execution-Lease live verifizieren`.
