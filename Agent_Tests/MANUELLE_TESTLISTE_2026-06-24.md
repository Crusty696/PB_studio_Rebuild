# Manuelle Testliste — PB Studio (2026-06-24)

> Aufzeichnung läuft via `start_pb_studio_clicklog.bat` (PB_CLICK_LOG=1).
> Du musst NICHTS notieren — Klicks + Wirkung landen im Log, Agent wertet aus.
> Pro Punkt am Ende nur sagen: **ok** oder **komisch: <was>**.
> Kurze Fixtures, KEIN 4h-Test.

## Fixtures (kurz)
- Video (60s): `outputs/Live_OTK021_20260622/b563_proxy_retest_60s.mp4`
- Audio (8s):  `outputs/Live_OTK021_20260622/B565_Retest/Zyce,_Querox_-_Feel_Free_(Original)_142__(Trance_(Main_Floor))_Gb_Major_17_29.mp3`

---

## 0. Start
- [ ] Laufende App schließen (Strg+S falls Stand wichtig).
- [ ] `start_pb_studio_clicklog.bat` doppelklicken.
- [ ] Systemcheck-Dialog: zeigt er **NVENC** + **CUDA GTX 1060**? → „Weiter".

## 1. Projekt anlegen — achte auf **B-562**
- [ ] Tab „Projekt Workflow" → „+ Neues Projekt".
- [ ] Name z.B. `ManTest 20260624`, Speicherort unter `outputs\` (Pflichtfeld!), „Erstellen".
- [ ] **PRÜFEN B-562:** Zeigt IRGENDWO noch „Kein Projekt geladen", obwohl Titelleiste/Status den Projektnamen nennt? (Cockpit-Innenstatus vs. Statusleiste vergleichen.)

## 2. Audio importieren + analysieren — achte auf **B-567, B-568**
- [ ] Tab „Material und Analyse Workflow" → „Audio Modus".
- [ ] „Audio importieren" → die 8s-MP3 wählen.
- [ ] Audio-Track in der Liste anklicken (Checkbox/Zeile aktiv).
- [ ] „KOMPLETT-ANALYSE" starten. Durchlaufen lassen (BPM, Waveform, Tonart, LUFS, Mood, Spektral, Struktur, Stems).
- [ ] **PRÜFEN B-568:** Nach „Fertig" — springt das rechte Analyse-Panel auf 100% / alle 8 Schritte grün? Oder hängt es bei z.B. „1 von 8" / 12%?
- [ ] **PRÜFEN B-567:** Falls die Audio-Analyse abbricht/scheitert — kommt eine **sichtbare Fehlermeldung** (rot/Dialog)? Oder bleibt es stumm bei x% und Button springt zurück?

## 3. Video importieren + analysieren — achte auf **B-564, B-550**
- [ ] „Video Modus" → „Ordner importieren" → Ordner mit der 60s-MP4 wählen.
- [ ] **PRÜFEN B-550:** Beim ersten Wechsel in die **Kachel-/Grid-Ansicht** (⊞): sind die Thumbnails sofort da, oder ist Seite 1 leer/schwarz bis man auf Seite 2 und zurück geht?
- [ ] Video-Analyse läuft ggf. automatisch; sonst „Video komplett analysieren".
- [ ] **PRÜFEN B-564:** Nach Abschluss — zeigt das rechte Video-Panel 100% / 9 von 9? Oder hängt es bei „1 von 9" / 11% obwohl Footer „fertig" sagt?

## 4. SCHNITT / Auto-Edit — achte auf **BUG-A, B-569, B-553**
- [ ] Tab „Schnitt Workflow".
- [ ] Ein Auto-Edit-Preset klicken (z.B. „Techno"/„Cinematic"). Auto-Edit + Timeline generieren lassen.
- [ ] **PRÜFEN BUG-A:** Bleibt nach Auto-Edit der **leere Empty-State** stehen, bis du den SCHNITT-Tab ein **zweites Mal** anklickst? Oder lädt der Editor sofort?
- [ ] **PRÜFEN B-569:** Im SCHNITT — zeigt das **Audio-Dropdown** den **richtigen** Track (den in der A1-Lane), oder einen falschen (z.B. „Normalize"-Track statt dem importierten)?
- [ ] **PRÜFEN B-553:** Versuche einen **Clip in der Timeline per Drag zu verschieben**. Bewegt sich der Clip? Oder scrollt nur die Ansicht und der Clip bleibt? (Danach Strg+Z testen.)

## 5. Export — achte auf **B-552**
- [ ] Tab „Export Workflow" → „Aktualisieren" (Timeline-Status).
- [ ] „Quick-Preview rendern" ODER „Finales Video exportieren" (kurz).
- [ ] **PRÜFEN B-552:** Falls der Export scheitert/crasht — kommt **GUI-Feedback** (Dialog / rote Statuszeile)? Oder passiert sichtbar nichts (Fehler nur im Log)?

## 6. Storage-Browser — achte auf **B-547**
- [ ] Storage-/Speicher-Browser öffnen (falls im Menü/Workflow erreichbar).
- [ ] Eine Analyse-Quelle „Löschen".
- [ ] **PRÜFEN B-547:** Wird **Speicherplatz frei** (Dateien weg) oder verschwindet nur der DB-Eintrag und die Dateien bleiben? (Meldung mit „X MB freigegeben"?)

---

## Gesamt
- [ ] Lief der ganze Ablauf **ohne Crash/Freeze** durch? (Boot → Import → Analyse → Schnitt → Export)
- [ ] Irgendwo Hänger >paar Sekunden ohne Reaktion?

> Wenn fertig: sag **„fertig"** + grob pro Punkt ok/komisch. Rest hole ich aus Log + DB.
