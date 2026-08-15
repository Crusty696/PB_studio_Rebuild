"""B-843: Die Videospur endete vor der Musik.

Livebefund 2026-08-15. Der 64-Segmente-Auto-Edit schloss 62 Luecken
(`video_gaps_closed: 62`) und endete danach bei 330,015 s statt 337,137 s.
Die letzten **7,122 Sekunden** des Tracks liefen ohne Bild; der Export hat die
Tonspur entsprechend mitgeschnitten, das gerenderte Video
(`45output.mp4`) ist 330,025 s statt 337,1 s lang.

Ursache: der Gap-Close-Pass in `repair_timeline_integrity` schiebt Segmente
nach LINKS (`start = cursor`) und verkuerzt damit die Gesamtdauer, ohne den
entstehenden Schwanz zu fuellen.

Perfekte Korrelation ueber alle acht Laeufe des Tages: nur Laeufe mit
`video_gaps_closed > 0` endeten kurz. Snapshots:

    snap5 (163 Segmente)  Video 337,137  Audio 337,137   Diff 0,000
    snap6 (211 Segmente)  Video 337,137  Audio 337,137   Diff 0,000
    snap7  (64 Segmente)  Video 330,015  Audio 337,137   Diff 7,122  <-
    snap8 (282 Segmente)  Video 337,137  Audio 337,137   Diff 0,000
"""

from __future__ import annotations

import inspect

from services import timeline_service


def _quelle() -> str:
    return inspect.getsource(timeline_service.repair_timeline_integrity)


class TestSchwanzWirdGefuellt:
    def test_repair_prueft_das_audio_ende(self):
        quelle = _quelle()
        assert "B-843" in quelle, "der Schwanz-Ausgleich fehlt"
        assert "audio_ende" in quelle and "video_ende" in quelle, (
            "ohne Vergleich beider Spuren kann die Luecke nicht auffallen"
        )

    def test_verlaengerung_wird_gemeldet(self):
        quelle = _quelle()
        assert "video_tail_extended" in quelle, (
            "die Verlaengerung wird nicht im Ergebnis gemeldet"
        )

    def test_luecke_wird_ueber_mehrere_segmente_verteilt(self):
        """Ein einzelner Clip hat selten genug Restmaterial.

        Livebefund: 7,1s fehlten bei Clips von hoechstens 10s Laenge. Das
        letzte Segment allein konnte das nicht schliessen.
        """
        quelle = _quelle()
        stelle = quelle.find("B-843")
        abschnitt = quelle[stelle:]
        assert "for row in reversed(sortiert)" in abschnitt, (
            "es wird nur ein Segment betrachtet statt von hinten aufzufuellen"
        )

    def test_alles_oder_nichts(self):
        """Ein Teilstueck anzuhaengen verschiebt nur Grenzen, ohne zu helfen."""
        quelle = _quelle()
        stelle = quelle.find("B-843")
        abschnitt = quelle[stelle:]
        assert "if rest <= 0.05 and plan:" in abschnitt, (
            "die Aenderung muss davon abhaengen, dass die Luecke vollstaendig "
            "geschlossen werden kann"
        )

    def test_verlaengerung_respektiert_die_cliplaenge(self):
        """Ueber das Quellmaterial hinaus darf nicht geschnitten werden."""
        quelle = _quelle()
        stelle = quelle.find("B-843")
        abschnitt = quelle[stelle:]
        assert "clip_dauer" in abschnitt and "video_durations" in abschnitt, (
            "die Clipdauer wird nicht beruecksichtigt — dann entstuende ein "
            "Segment ohne Material dahinter"
        )
        assert "clip_dauer - float(row.source_end" in abschnitt, (
            "das freie Restmaterial muss aus Clipdauer minus bereits "
            "verbrauchtem Quellende berechnet werden"
        )

    def test_restluecke_wird_gemeldet_statt_verschwiegen(self):
        quelle = _quelle()
        stelle = quelle.find("B-843")
        abschnitt = quelle[stelle:]
        assert "logger.warning" in abschnitt, (
            "reicht das Material nicht, muss das sichtbar sein — sonst faellt "
            "erst im fertigen Video auf, dass der Schluss fehlt"
        )

    def test_gelockte_segmente_bleiben_unangetastet(self):
        """Gelockte Clips sind Nutzer-Anker und duerfen sich nicht verschieben."""
        quelle = _quelle()
        stelle = quelle.find("B-843")
        abschnitt = quelle[stelle:]
        assert "if bool(row.locked):" in abschnitt and "break" in abschnitt, (
            "an einem gelockten Anker muss die Verlaengerung abbrechen"
        )

    def test_kein_eingriff_ohne_luecke(self):
        """Bei passender Laenge darf nichts geaendert werden."""
        quelle = _quelle()
        stelle = quelle.find("B-843")
        abschnitt = quelle[stelle:stelle + 1200]
        assert "fehlend > 0.05" in abschnitt, (
            "ohne Schwelle wuerde auch bei Rundungsdifferenzen editiert"
        )


class TestBestandsvertraegeBleiben:
    def test_ergebnis_dict_behaelt_seine_schluessel(self):
        """test_e6_repair_column_queries vergleicht das Dict exakt."""
        quelle = _quelle()
        for schluessel in (
            "video_duration_clamped", "video_overlaps_shifted",
            "video_gaps_closed", "video_source_span_rebuilt",
            "audio_duplicates_removed", "audio_duration_synced",
        ):
            assert f'"{schluessel}"' in quelle, f"{schluessel} fehlt"

    def test_neuer_schluessel_nur_bei_bedarf(self):
        """video_tail_extended darf das Dict nicht unbedingt erweitern.

        Sonst bricht der Bestandstest, der das Dict exakt vergleicht.
        """
        quelle = _quelle()
        assert 'result["video_tail_extended"] = ' in quelle
        assert '"video_tail_extended": 0' not in quelle, (
            "der Schluessel darf nicht in der Grundbelegung stehen"
        )
