# 99 — Offene Klaerungs-Punkte

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Verifikation
> Status: living document · 2026-05-19

## Architektur

- [ ] Audio-aus-Video extraktion: nutzt V2-Pipeline durch Audio-Track-Extract + dann V2-Pipeline starten, oder bleibt separat?
- [ ] Cross-Modal-Service: heuristischer Fallback bei fehlendem Reasoner vs Stage failed?

## Modelle

- [ ] SigLIP-Variant Default (so400m vs base)
- [ ] RAFT large vs small auf 1060 — Quality vs Speed
- [ ] VLM-Modell-Choice bleibt Plan-B-Auto-Selector?

## Storage

- [ ] Proxy bleibt auch nach Pipeline-Cleanup? (User-Setting)
- [ ] Embeds Format f16 ok oder f32?
- [ ] Keyframes JPEG-Quality 95 ok?

## Performance

- [ ] 4 h Video-Pipeline tatsaechliche Laufzeit auf 1060 — Messung Pflicht vor Production-Use
- [ ] RAFT-Batch-Groesse optimieren
- [ ] NVDEC + NVENC gleichzeitig moeglich?

## UI

- [ ] Status-Panel pro Video oder konsolidiert?
- [ ] Multi-File-Batch-Queue: Default Reihenfolge (FIFO / Size-asc / User-defined)?

## Cross-Plan

- [ ] Plan B Backend muss verfuegbar sein fuer echte VLM-Captions. Stub-Mode ausreichend fuer Plan-A-Live-Verify?
- [ ] V2 muss Audio-Outputs liefern fuer Cross-Modal. Wann ist V2 ready?
