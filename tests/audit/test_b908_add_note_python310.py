"""B-908 — ``add_note`` gibt es erst ab Python 3.11.

``tools/audit_runtime_evidence.py`` haengte Aufraeum-Kontext per
``error.add_note(...)`` an eine Ausnahme. Unter dem Projekt-Python 3.10.21
existiert die Methode nicht, und der Aufruf riss den Gate-Test mit
``AttributeError: 'ValueError' object has no attribute 'add_note'`` um.

Der Fix (Commit ``247a1e79``) prueft die Methode vor dem Aufruf. Ein Test
dazu fehlte: ``tools/commit_audit.py`` meldete am 2026-09-02, dass die
Commit-Nachricht von Tests spricht, der Diff aber keine Testdatei enthaelt.
"""

from __future__ import annotations

import sys
import unittest

from tools.audit_runtime_evidence import _add_exception_note


class B908AddNoteTests(unittest.TestCase):
    """Der Helfer muss auf 3.10 und auf 3.11+ funktionieren."""

    def test_haengt_die_notiz_an_wenn_die_methode_existiert(self):
        if not hasattr(BaseException, "add_note"):
            self.skipTest("add_note gibt es erst ab Python 3.11")
        fehler = ValueError("primaer")

        _add_exception_note(fehler, "Aufraeumen fehlgeschlagen")

        self.assertIn("Aufraeumen fehlgeschlagen", getattr(fehler, "__notes__", []))

    def test_ohne_add_note_passiert_nichts_schlimmes(self):
        """Der Kern des Befunds: kein AttributeError auf Python 3.10."""

        class OhneNote(Exception):
            """Verhaelt sich wie eine 3.10-Ausnahme — kennt add_note nicht."""

            def __getattr__(self, name):
                if name == "add_note":
                    raise AttributeError(name)
                raise AttributeError(name)

        fehler = OhneNote("primaer")

        # Darf nicht werfen.
        _add_exception_note(fehler, "Aufraeumen fehlgeschlagen")

    def test_die_primaere_ausnahme_bleibt_unveraendert(self):
        """Der Kontext wird angehaengt, nicht ersetzt."""
        fehler = ValueError("primaer")

        _add_exception_note(fehler, "zusaetzlicher Kontext")

        self.assertEqual(str(fehler), "primaer")

    def test_der_helfer_prueft_vor_dem_aufruf(self):
        """Quellcode-Guard gegen einen direkten ``error.add_note(...)``."""
        import inspect

        quelle = inspect.getsource(_add_exception_note)

        assert "getattr(" in quelle, "kein Zugriffsschutz vor add_note"
        assert "callable(" in quelle, "kein callable-Check vor dem Aufruf"

    def test_laeuft_unter_dem_projekt_python(self):
        """Belegt, dass der Fall real ist: das Projekt nutzt 3.10."""
        if sys.version_info >= (3, 11):
            self.skipTest("nur auf 3.10 aussagekraeftig")

        self.assertFalse(hasattr(BaseException, "add_note"))


if __name__ == "__main__":
    unittest.main()
