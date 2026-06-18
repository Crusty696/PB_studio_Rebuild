# GRUNDREGELN FÜR DAS TESTEN VON PB STUDIO (STRIKT BEFOLGEN)

Diese Datei gilt für JEDES Test-Skript in diesem Ordner. Lies sie zuerst und
halte dich bei jedem Schritt daran. Sie ist nicht verhandelbar.

---

## 0. DIE EISERNE REGEL: TEST IMMER ÜBER DIE GUI IM VORDERGRUND

- Der Test wird **ausschließlich über die sichtbare grafische Oberfläche** von
  PB Studio durchgeführt. Der Nutzer muss live zusehen können.
- Starte die App **immer sichtbar** über `start_pb_studio.bat`
  (bzw. `python start_pb_studio.py`). Das Fenster muss im **Vordergrund** sein.
- **VERBOTEN:** `QT_QPA_PLATFORM=offscreen`, Headless-Modus, `--offscreen`,
  versteckte Fenster, oder das Ersetzen des GUI-Tests durch einen reinen
  `pytest`-Lauf. Auch `scripts/phase_e_smoke_boot.py` (Offscreen) ist KEIN
  Ersatz für den GUI-Test.
- Bediene die App per **echter Maus und Tastatur** (Computer-Use): Tabs
  anklicken, Buttons drücken, Dateien über die echten Dialoge auswählen.
- pytest/Logs/`ffprobe` sind **nur erlaubt als zusätzlicher Beweis** neben dem
  GUI-Test — niemals als Ersatz.
- Wenn die GUI nicht sichtbar gestartet werden kann: **STOPP**. Melde das und
  mache nicht headless weiter.

---

## 1. ALLGEMEINE TEST-DISZIPLIN

1. **SYSTEMATISCH VORGEHEN:** Teste nur das, was im aktuellen Aufgaben-Skript
   steht. Springe nicht in andere Bereiche.
2. **NICHT VON VORNE BEGINNEN:** Ignoriere vorherige Tests, es sei denn, das
   Skript verlangt es ausdrücklich. Fange nicht ungefragt eine neue Analyse an.
3. **KEINE ANNAHMEN MACHEN:** Verlasse dich nur auf echte Ausgaben, Screenshots,
   Logs und Fehlermeldungen. Behaupte nichts, was du nicht im Fenster oder Log
   gesehen hast. „Müsste funktionieren" ist kein Ergebnis.
4. **STOPP BEI FEHLER:** Wenn ein Schritt fehlschlägt oder die App hängt/abstürzt,
   brich den Test sofort ab. Melde den Fehler. Mache nicht weiter und
   versuche nicht, ihn still zu umgehen.
5. **100 % EHRLICHKEIT:** Melde Fehler genau so, wie sie passieren. Beschönige
   nichts. Ein TEIL-PASS ist ein TEIL-PASS, kein PASS.
6. **PROTOKOLLIERUNG:** Dokumentiere jeden erfolgreichen Schritt kurz mit
   „Erfolg: [Schrittname]". Bei Fehlern: „FEHLER: [Schrittname] — [was passierte]".

---

## 2. KONTEXT DIESER APP (damit du nicht rätst)

- **PB Studio v0.5.0** — ein **PySide6-Desktop-Programm** (beat-synchroner
  Video-Editor für DJs). Es ist KEINE Webseite und KEIN getrenntes
  Backend/Frontend — es ist EIN Programmfenster mit 4 Tabs:
  **PROJEKT · MATERIAL & ANALYSE · SCHNITT · EXPORT**.
- **Umgebung:** conda-env `pb-studio`, Python 3.10, **CUDA 11.3**, Ziel-GPU
  **NVIDIA GTX 1060 6 GB**. Die App als Ganzes benötigt CUDA; einzelne
  Bibliotheken ohne CUDA-Backend laufen gemäß `AGENTS.md` auf der CPU.
- **Datenbank:** SQLite `pb_studio.db` im Projekt-Stamm (wird automatisch
  angelegt).
- **Wichtige Log-Quellen für Beweise:**
  - Konsolen-Log des Starts: `outputs/app_run_<zeitstempel>.log`
  - laufendes App-Log: `logs/pb_studio.log`
- **Typische Testdaten:** 1 Audio-Mix (1–10 Minuten) + ca. 150 Video-Clips.

---

## 3. BEWEIS-SICHERUNG (PFLICHT)

Für jeden Test gilt — wie bei den bisherigen Test-Reports unter `Test-ergebniss/`:

1. Lege zu Beginn einen Ergebnis-Ordner an:
   `Test-ergebniss/<JJJJ-MM-TT>_<kurzname-des-tests>/`
2. Mache zu jedem wichtigen Schritt einen **Screenshot** der GUI und speichere
   ihn dort mit sprechendem Namen
   (z. B. `03_stems-fertig.png`, `03_abbruch-button-reset.png`).
3. Kopiere bei Bedarf den relevanten **Log-Auszug** in eine `.txt`-Datei.
4. Schreibe am Ende einen kurzen **`report.md`** im bewährten Format:
   - Kopf: Datum, App-Start, Test-Projekt, Test-Daten (Audio + Clip-Anzahl),
     Methode (GUI-Vordergrund / Computer-Use).
   - Tabelle: Anzahl PASS / TEIL-PASS / FAIL / BLOCKIERT.
   - Pro Schritt: **Aktion**, **Erwartet**, **Tatsächlich**, **Status**.
5. Bekannte Bugs werden mit ihrer **B-Nummer** benannt (siehe jeweiliges Skript).
   Neue Befunde markierst du als `B-NEU-<kurz>` und beschreibst sie genau.

---

## 4. STATUS-BEGRIFFE (einheitlich verwenden)

- **PASS** — Soll-Verhalten vollständig erfüllt, mit Beweis.
- **TEIL-PASS** — funktioniert grundsätzlich, aber mit konkretem Befund.
- **FAIL** — Soll-Verhalten nicht erfüllt.
- **BLOCKIERT** — Schritt nicht testbar (z. B. GUI-Funktion fehlt). Grund nennen.
