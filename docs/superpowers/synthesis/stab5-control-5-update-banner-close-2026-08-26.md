# STAB-5 Control #5 — Update-Banner Schliessen

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Sichtbarer Update-Banner → `QPushButton("✕")` →
`clicked.connect(banner.hide)` → Banner hidden.

## Ergebnis

- Echter Update-Handler zeigt den zuvor versteckten Banner.
- Elementgenau gefundener Close-Button versteckt ihn nach echtem Qt-Click.
- Ein späteres Update zeigt denselben Banner wieder; Dismiss ist kein
  dauerhafter Blocker.
- Fokussierter neuer Testfall: `1 passed in 4.19s`.
- Drei geführte Read-only-Prüfer fanden keinen Produktdefekt.
- Kein Produktcode geändert.

## Offen

- Kein echter PBWindow-/Release-Banner-Livepfad.
- Status bleibt deshalb `target-test-pass-live-pending`.
