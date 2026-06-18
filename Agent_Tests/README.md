# Agent_Tests — GUI-Test-Skripte für PB Studio

Modulares Set fester Anweisungen für einen KI-Test-Agenten. Jede Datei ist ein
eigenes Dokument. Der Agent bekommt immer zuerst die Grundregeln und dann genau
EIN Stufen-Skript — so springt er nicht planlos umher.

## Eiserne Regel

**Jeder Test läuft über die sichtbare GUI im Vordergrund** (`start_pb_studio.bat`),
damit du live zusehen kannst. Kein Offscreen, kein Headless, kein reiner pytest.

## Dateien

| Datei | Zweck |
|---|---|
| `00_Basis_Regeln.md` | Grundregeln + eiserne GUI-Vordergrund-Regel + Beweis-Pflicht. Immer mitgeben. |
| `01_Setup_und_Parameter.md` | Fragt bei JEDEM Lauf nach Audio-Pfad, Video-Ordner, Projektname; prüft; startet App sichtbar. |
| `02_Test_Projekt_und_Import.md` | PROJEKT anlegen + Audio + ~150 Clips importieren. Bug-Check B-498. |
| `03_Test_Audio_Analyse.md` | Waveform, Beat-Detection, Demucs-Stems. Bug-Checks B-507/B-510/B-524, B-331. |
| `04_Test_Video_Analyse.md` | Proxies, Szenen, Motion, SigLIP über ~150 Clips. Bug-Checks B-505, B-508/B-NEU-4, B-336. |
| `05_Test_Schnitt_AutoEdit.md` | SCHNITT: Preset → Auto-Edit, Timeline, Locks, Re-Generate. Bug-Checks B-NEU-1, B-NEU-7. |
| `06_Test_Export.md` | EXPORT: Render NVENC/LUFS. Bug-Check B-504 (Umlaut + Trim). |
| `07_Test_End2End.md` | Kompletter Durchlauf Projekt → Import → Analyse → Auto-Edit → Export. |

## So benutzt du es (Eingabe in den Chat deines Test-Agenten)

Einzelner Teil-Test, z. B. Audio:

```text
Lies die Datei "Agent_Tests/00_Basis_Regeln.md".
Führe danach exakt die Anweisungen aus "Agent_Tests/03_Test_Audio_Analyse.md" aus.
Frage mich zuerst nach den drei Parametern. Teste alles über die sichtbare GUI
im Vordergrund. Mache nichts anderes.
```

Kompletter End-2-End-Test:

```text
Lies die Datei "Agent_Tests/00_Basis_Regeln.md".
Führe danach exakt die Anweisungen aus "Agent_Tests/07_Test_End2End.md" aus.
Frage mich zuerst nach den drei Parametern. Teste alles über die sichtbare GUI
im Vordergrund. Mache nichts anderes.
```

Empfohlene Reihenfolge bei einem frischen Durchlauf: `02 → 03 → 04 → 05 → 06`,
oder direkt `07` für den ganzen Ablauf am Stück.

## Ergebnisse

Der Agent legt Screenshots, Log-Auszüge und einen `report.md` unter
`Test-ergebniss/<JJJJ-MM-TT>_<kurzname>/` ab — im selben Format wie die
bisherigen Live-Verifikations-Reports.
