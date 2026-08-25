# STAB-4 / B-774 Current-Evidenzbewertung

Datum: 2026-08-26
Status: agent-complete; rare real fault branch unobserved

## Fixstand

- `a63784e`: CUDA-Kontexttod stoppt Video-Batch statt Kaskadencrash.
- `016bdb6`: Audio-/Demucs-Pfad markiert denselben Kontexttod und zeigt
  Neustartmeldung.
- Current gezielt: 9 Tests bestanden in 4.67 s.

## Realer Post-Fix-Dauerlastbeleg

App-Log 2026-08-24: mindestens 100 echte RAFT-/SigLIP-GPU-Clips, danach
weitere erfolgreiche Clips. VRAM-Diagnose:

- 25 Clips: allocated 1727.4 MiB, reserved 1936 MiB
- 50 Clips: allocated 1762.5 MiB, reserved 2342 MiB
- 75 Clips: allocated 1762.5 MiB, reserved 2342 MiB
- 100 Clips: allocated 1762.5 MiB, reserved 2094 MiB

Mehrere Power-Resume-Probes wurden signalisiert; folgende CUDA-Inferenzen
blieben erfolgreich. Lauf endete durch nativen App-Shutdown, nicht durch
CUDA-Fehler.

## Ehrliche Grenze

Ein echter gestorbener CUDA-Kontext trat nach Fix nicht wieder auf. Dieser
Fehler kann ohne riskanten Treiber-/Hardware-Reset nicht sicher erzwungen
werden. Deshalb kein neuer Agent-`fixed`-Claim. Belegt sind Dauerlast ohne
Regression sowie deterministische Fault-Injection des Schutzpfads.
