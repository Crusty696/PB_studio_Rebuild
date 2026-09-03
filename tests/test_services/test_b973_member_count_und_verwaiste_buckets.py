"""B-973 / B-974 — zwei Befunde aus dem Live-Rundgang durch das Studio Brain.

Gefunden am 2026-09-03 im Loop-7-Live-Lauf: der Struktur-Tab zeigte dutzende
Buckets mit je `(1)` Clip neben der Statistik „Aktive Stil-Cluster: 3". Der
Widerspruch war in der DB des Projekts `Erstlauf_Test_2026-08-30` messbar.

**B-973 — `member_count` widerspricht der Zuordnung:**

    Bucket 127: gespeichert  105, tatsaechlich  66   Abweichung +39
    Bucket 128: gespeichert   11, tatsaechlich  11   Abweichung  +0
    Bucket 129: gespeichert   29, tatsaechlich  22   Abweichung  +7

Ursache: beim Insert wird der Zähler aus `labels` berechnet — der Beschriftung
über `fit_matrix`, also über **alle** Embeddings der Library. Zugeordnet werden
aber nur die `enrichable_scenes` des jeweiligen Laufs. Danach korrigierte den
Wert niemand. `ui/studio_brain/structure_tab.py:329` zeigt ihn direkt an.

**B-974 — 48 von 147 Szenen zeigen auf abgeschaltete Cluster:**

    Szenen gesamt mit Tag:      147
    davon an AKTIVEN Buckets:    99
    davon an INAKTIVEN Buckets:  48
    ohne Bucket:                  0

Ursache: `UPDATE struct_style_bucket SET active = 0` schaltet vor jedem
Clusterlauf alle alten Buckets ab, aber `struct_clip_tags.style_bucket_id`
bleibt auf der alten ID stehen. Für Szenen, die im neuen Lauf nicht
angereichert werden, gibt es kein Umschreiben.

B-974 ist hier **nur dokumentiert, nicht repariert**: ob verwaiste Zuordnungen
neu berechnet oder die Szenen erneut angereichert werden sollen, ist eine
Produktentscheidung.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _quelle(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _nur_code(text: str) -> str:
    """Kommentare weg — Wächter-Regel aus Loop 6.

    Viermal in Loop 6 traf ein Guard die Bug-ID im Kommentar statt im Code.
    """
    return "\n".join(z.split("#", 1)[0] for z in text.splitlines())


# ---------------------------------------------------------------------------
# B-973 — member_count wird nachgezogen
# ---------------------------------------------------------------------------

def test_b973_member_count_wird_nach_der_zuordnung_neu_berechnet():
    """Der Kern des Fixes: ein UPDATE nach der Tag-Schleife."""
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))

    assert "UPDATE struct_style_bucket SET member_count" in quelle, (
        "member_count wird nach der Zuordnung nicht mehr nachgezogen"
    )


def test_b973_der_zaehler_kommt_aus_struct_clip_tags():
    """Aus der tatsächlichen Zuordnung, nicht aus `labels`."""
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))
    ab = quelle.index("UPDATE struct_style_bucket SET member_count")
    danach = quelle[ab:ab + 400]

    assert "FROM struct_clip_tags t" in danach
    assert "t.style_bucket_id = struct_style_bucket.id" in danach


def test_b973_nur_aktive_buckets_werden_nachgezogen():
    """Inaktive Buckets sind Historie — ihr alter Zähler bleibt stehen.

    Sie zu überschreiben würde die Zahlen früherer Läufe verfälschen, und der
    Struktur-Tab liest ohnehin nur `active = 1`
    (`services/brain/legacy_sqlite.py:343`).
    """
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))
    ab = quelle.index("UPDATE struct_style_bucket SET member_count")
    danach = quelle[ab:ab + 400]

    assert "WHERE active = 1" in danach


def test_b973_das_update_steht_vor_dem_commit():
    """Nach dem Commit wäre es eine zweite Transaktion."""
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))

    update = quelle.index("UPDATE struct_style_bucket SET member_count")
    commit = quelle.index("session.commit()", update)

    assert update < commit


def test_b973_der_insert_setzt_weiterhin_einen_startwert():
    """Die Spalte ist `nullable=False` — der Insert braucht einen Wert.

    Das Nachziehen ersetzt den Startwert, es macht ihn nicht überflüssig.
    """
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))

    assert '"member_count": member_count' in quelle
    assert "member_count = int((labels == label_id).sum())" in quelle


def test_b973_die_ui_liest_genau_diesen_wert():
    """Beleg, dass der falsche Zähler sichtbar war."""
    quelle = _quelle("ui/studio_brain/structure_tab.py")

    assert "bucket['member_count']" in quelle


def test_b973_die_leseabfrage_filtert_auf_aktive_buckets():
    quelle = _quelle("services/brain/legacy_sqlite.py")
    ab = quelle.index("FROM struct_style_bucket ")
    umgebung = quelle[ab:ab + 200]

    assert "WHERE active = 1" in umgebung


def test_b973_das_sql_ist_ein_gueltiges_korrelierte_unterabfrage(tmp_path):
    """Verhaltensbeleg gegen echtes SQLite, ohne die Projekt-DB anzufassen."""
    import sqlite3

    db = tmp_path / "probe.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE struct_style_bucket (
            id INTEGER PRIMARY KEY, member_count INTEGER NOT NULL, active INTEGER
        );
        CREATE TABLE struct_clip_tags (
            scene_id INTEGER PRIMARY KEY, style_bucket_id INTEGER
        );
        INSERT INTO struct_style_bucket VALUES (1, 105, 1), (2, 11, 1), (3, 99, 0);
        INSERT INTO struct_clip_tags VALUES (10, 1), (11, 1), (12, 2), (13, 3);
        """
    )
    con.execute(
        "UPDATE struct_style_bucket SET member_count = ("
        "  SELECT COUNT(*) FROM struct_clip_tags t"
        "  WHERE t.style_bucket_id = struct_style_bucket.id"
        ") WHERE active = 1"
    )
    con.commit()

    werte = dict(con.execute(
        "SELECT id, member_count FROM struct_style_bucket ORDER BY id").fetchall())
    con.close()

    assert werte[1] == 2, "aktiver Bucket wurde nicht korrigiert"
    assert werte[2] == 1
    assert werte[3] == 99, "inaktiver Bucket wurde faelschlich ueberschrieben"


# ---------------------------------------------------------------------------
# B-974 — verwaiste Zuordnungen (dokumentiert, nicht repariert)
# ---------------------------------------------------------------------------

def test_b974_der_clusterlauf_schaltet_alle_alten_buckets_ab():
    """Belegt die Ursache: das `active = 0` trifft alle, ohne Umschreiben."""
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))

    assert "UPDATE struct_style_bucket SET active = 0" in quelle


def test_b974_es_gibt_kein_umschreiben_verwaister_zuordnungen():
    """Festhalten, dass die Lücke offen ist.

    Schlägt dieser Test fehl, wurde B-974 behoben — dann gehört der Test
    umgeschrieben, statt ihn zu löschen.
    """
    quelle = _nur_code(_quelle("workers/structure_enrichment.py"))

    assert "UPDATE struct_clip_tags SET style_bucket_id" not in quelle, (
        "es gibt jetzt ein Umschreiben — B-974 ist behoben, Test anpassen"
    )


def test_b974_die_fremdschluessel_beziehung_bleibt_ohne_cascade():
    """Die Migration nennt den Grund ausdrücklich.

    Ohne `CASCADE` behalten gelöschte Buckets ihre Tag-Zeilen — genau das
    erzeugt die verwaisten Zuordnungen, ist aber Absicht.
    """
    treffer = list((REPO_ROOT / "database" / "alembic" / "versions").glob(
        "*add_struct_layer_tables.py"))
    assert treffer, "Migration nicht gefunden"
    quelle = treffer[0].read_text(encoding="utf-8", errors="replace")

    assert "without CASCADE" in quelle


@pytest.mark.parametrize("marker,pfad", [
    ("B-973", "workers/structure_enrichment.py"),
])
def test_die_stelle_behaelt_ihren_marker(marker, pfad):
    assert marker in _quelle(pfad)
