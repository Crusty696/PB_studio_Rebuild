"""B-834: Nutzungs-Cap erlaubte Wiederholungen trotz Materialueberschuss.

Livebefund 2026-08-14 aus ``projects/123454321/pb_studio.db`` nach einem
Auto-Edit-Lauf: 121 Clips im Projekt, 93 Timeline-Segmente — also mehr Clips
als Schnitte. Verwendet wurden trotzdem nur 51 verschiedene Clips, 70 blieben
ungenutzt, 42 Clips kamen doppelt vor.

Ursache war die Cap-Formel::

    max_uses_per_video = ceil(n_slots / n_videos) + 1

Bei 93 Slots und 121 Videos ergibt ``ceil(0.77)`` bereits 1; das ``+1`` hob das
Limit auf 2 an. Damit durfte der Scorer seinen Favoriten ein zweites Mal
nehmen, obwohl 70 unbenutzte Clips bereitstanden. Das Cap ist eine Obergrenze,
kein Streuzwang — was es erlaubt, wird auch genommen.

User-Anweisung 2026-08-14: "jeder clip nur einmal solange material reicht".

Der Cap bleibt eine Obergrenze; bei echtem Materialmangel muss er weiterhin
mitwachsen, sonst haette die Pipeline fuer die letzten Slots keine Kandidaten
mehr.
"""

from __future__ import annotations

import pytest

from services.pacing_service import berechne_max_uses


class TestGenugMaterial:
    """Mehr Clips als Slots — jeder Clip darf dann nur einmal vorkommen."""

    def test_livebefund_121_clips_93_slots(self):
        assert berechne_max_uses(n_slots=93, n_videos=121) == 1, (
            "B-834: 121 Clips auf 93 Schnitte — es gibt keinen Grund, einen "
            "Clip zweimal zu verwenden."
        )

    def test_genau_gleich_viele(self):
        assert berechne_max_uses(n_slots=50, n_videos=50) == 1

    def test_ein_clip_mehr_als_noetig(self):
        assert berechne_max_uses(n_slots=49, n_videos=50) == 1


class TestKnappesMaterial:
    """Weniger Clips als Slots — der Cap muss mitwachsen, sonst Sackgasse."""

    def test_doppelt_so_viele_slots(self):
        assert berechne_max_uses(n_slots=100, n_videos=50) == 2

    def test_rest_wird_aufgerundet(self):
        # 93 Slots auf 30 Videos = 3.1 -> 4, sonst fehlen Kandidaten fuer die
        # letzten Slots.
        assert berechne_max_uses(n_slots=93, n_videos=30) == 4

    def test_ein_einziger_clip(self):
        assert berechne_max_uses(n_slots=40, n_videos=1) == 40

    def test_cap_deckt_immer_alle_slots_ab(self):
        """Kapazitaet (Videos x Cap) darf nie kleiner als die Slotzahl sein."""
        for n_slots in (1, 7, 50, 93, 500):
            for n_videos in (1, 3, 30, 121, 400):
                cap = berechne_max_uses(n_slots, n_videos)
                assert n_videos * cap >= n_slots, (
                    f"{n_videos} Videos x Cap {cap} = {n_videos * cap} deckt "
                    f"{n_slots} Slots nicht ab — die Pipeline muesste das Cap "
                    f"aussetzen und wieder Clips haeufen."
                )


class TestRandfaelle:
    def test_niemals_null(self):
        """Cap 0 wuerde in der Pipeline als 'kein Cap' gelesen werden."""
        for n_slots in (0, 1):
            for n_videos in (0, 1, 10):
                assert berechne_max_uses(n_slots, n_videos) >= 1

    def test_keine_division_durch_null(self):
        assert berechne_max_uses(n_slots=10, n_videos=0) >= 1


def test_alter_reserve_aufschlag_ist_weg():
    """Gegenprobe: die alte Formel haette hier 2 geliefert, nicht 1."""
    import numpy as np

    n_slots, n_videos = 93, 121
    alt = int(np.ceil(n_slots / max(1, n_videos))) + 1
    neu = berechne_max_uses(n_slots, n_videos)
    assert alt == 2 and neu == 1, (
        f"alte Formel {alt}, neue {neu} — der Reserve-Aufschlag muss bei "
        "Materialueberschuss verschwunden sein."
    )


@pytest.mark.parametrize("n_videos", [121, 200, 1000])
def test_ueberschuss_bleibt_bei_eins(n_videos):
    assert berechne_max_uses(n_slots=93, n_videos=n_videos) == 1
