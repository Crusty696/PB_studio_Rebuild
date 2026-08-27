# B-908 — Audit Exception Notes unter Python 3.10

Status: `code-fix-pending-full-suite`

## Root Cause

`_PinnedGit.__enter__/__exit__` nutzte `BaseException.add_note` direkt. Diese
API existiert erst ab Python 3.11; PB-Studio-Testenv verwendet Python 3.10.21.
Cleanup-Kontext ersetzte dadurch Primarfehler mit `AttributeError`.

## Fix

- Lokaler `_add_exception_note`-Helper.
- Native `add_note`-API wenn vorhanden.
- `__notes__`-Fallback unter Python 3.10.
- Letzter Attribut-Fallback darf Primarfehler nie ersetzen.
- Drei belegte `_PinnedGit`-Callsites umgestellt.

## Verifikation

- Gesamtlauf RED: `1 failed, 162 passed, 260 subtests passed` bis Stop.
- Exakter frueherer Failure: `1 passed in 3.41s`.
- Betroffene Gruppe: `2 passed, 63 deselected in 2.98s`.
- Voller Gesamtlauf und App-Livepfad ausstehend.
