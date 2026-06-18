# TEST-SKRIPT: TEIL 4 — SCHNITT & AUTO-EDIT

Beachte die Dateien `00_Basis_Regeln.md` und `01_Setup_und_Parameter.md`.
**EISERNE REGEL:** Alles über die sichtbare GUI im Vordergrund. Kein Headless.

---

## ZUERST: DIE DREI FRAGEN (siehe 01)

1. „Wie lautet der vollständige Pfad zur Audio-Datei (MP3/WAV/FLAC)?" → `AUDIO_PFAD`
2. „Wie lautet der Pfad zum Ordner mit den Video-Clips (MP4/MOV)?" → `VIDEO_ORDNER`
3. „Wie soll das Test-Projekt heißen?" → `PROJEKT_NAME`

Danach Parameter prüfen und App sichtbar starten (Schritte B + C aus `01`).

---

## ZIEL

Teste ausschließlich den **SCHNITT-Tab**: Auto-Edit über ein Preset, die
InteractiveTimeline mit Lock-Icons, die Sub-Tabs (Schnitt / Pacing & Anker /
Audio / RL & Notes) und Re-Generate. Voraussetzung: Audio- und Video-Analyse
sind bereits gelaufen (Teile 2 + 3).

---

## VORBEREITUNG

1. PB Studio ist sichtbar gestartet, Projekt `PROJEKT_NAME` geöffnet.
2. Beat/Stems (Teil 2) und Video-Analyse (Teil 3) sind fertig.

---

## TEST-SCHRITTE (Der Reihe nach, alles in der GUI)

1. Öffne den Tab **SCHNITT**. Im Empty-State erscheinen Preset-Buttons.
   - Erwartet: Buttons **Techno / Cinematic / House / Festival** sind sichtbar.
   - Klicke ein Preset (z. B. **Techno**), um den Auto-Edit auszulösen.
   - Erwartet: Loading-State zeigt Worker-Stufen-Fortschritt; danach Editor-State.
   - Screenshot: `05_autoedit-fertig.png`.

2. Prüfe im Sub-Tab **Schnitt** die **InteractiveTimeline** + Preview (640×360).
   - Erwartet: Clips sind beat-synchron auf der Timeline platziert; Preview und
     Transport funktionieren (Play/Pause).
   - Setze bei 1–2 Clips das **Lock-Icon** (Gold-Rahmen) per Klick.
   - Screenshot: `05_locks-gesetzt.png`.

3. Wechsle in den Sub-Tab **Pacing & Anker**.
   - Erwartet: PacingCurve sichtbar; Cut-Rate / Style / Reactivity / Vibe regelbar;
     Anchor-Liste vorhanden.
   - Klicke **Re-Generate**.
   - Erwartet: **Confirm-Dialog** erscheint. Bestätige.
   - Erwartet: Neuer Auto-Edit läuft; **gelockte Clips bleiben unverändert**
     erhalten.
   - Screenshot: `05_regenerate-locks-erhalten.png`.

4. Prüfe Sub-Tab **Audio**: Waveform + Beatgrid + Struktur-Marker, Stems-Mixer,
   LUFS + Tonart im Header sichtbar.

5. Prüfe Sub-Tab **RL & Notes**: 👍/👎-Feedback klickbar; Notiz-Editor speichert
   automatisch (ca. 1 s Debounce).
   - Erwartet: Notiz bleibt nach Tab-Wechsel erhalten.

---

## BEKANNTE SCHWACHSTELLEN PRÜFEN (PFLICHT)

- **B-NEU-1 (Inspector-Trim zerstört Timeline):** Wähle einen Clip, öffne den
  ClipInspectorPanel (rechte Spalte) und **trimme** den Clip (z. B. Dauer von
  10 s auf 5 s).
  - Erwartet (Soll): Timeline-Ansicht bleibt korrekt und vollständig dargestellt.
  - Bekannt fehlerhaft: Inspector-Trim zerstörte 2× reproduzierbar die
    Timeline-Ansicht. Melde genau, ob die Darstellung intakt bleibt. Screenshot
    vor/nach: `05_trim-vorher.png`, `05_trim-nachher.png`.

- **B-NEU-7 (Undo bei Drags):** Verschiebe einen Clip per Drag auf der Timeline
  und drücke danach **Strg+Z**.
  - Erwartet (Soll): Strg+Z macht die **Verschiebung** rückgängig.
  - Bekannt fehlerhaft: Drags landeten nicht im Undo-Stack; Strg+Z entfernte
    stattdessen Clip-Hinzufügungen. Melde genau, was Strg+Z rückgängig macht.
    Beweis: `05_undo-verhalten.txt` + Screenshot.

---

## ABSCHLUSS

Wenn Auto-Edit, Timeline/Locks, alle Sub-Tabs und Re-Generate geprüft und die
Bug-Checks (B-NEU-1, B-NEU-7) dokumentiert sind, gib aus:

„Teil 4 (Schnitt & Auto-Edit) erfolgreich getestet. Keine weiteren Aktionen nötig."

Bei Fehler stattdessen: „FEHLER in Teil 4: [Schritt + Beobachtung]" und STOPP.
