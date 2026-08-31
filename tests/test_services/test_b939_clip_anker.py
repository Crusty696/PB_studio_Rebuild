"""B-939 — Anker auf Clips ohne erkannte Szenen landeten auf einem Zufallsclip.

Der Anker-Dialog vergibt fuer Clips ohne Szenen die Form ``clip_<VideoClip.id>``
(`ui/controllers/edit_workspace.py:1060`). In ``auto_edit_phase3`` lief darauf
``int("clip_7")`` in einen ValueError; der Anker fehlte danach in
``anchor_scene_map``.

Die Folge war schlimmer als ein verworfener Anker: das Segment wurde weiterhin
als ``is_anchor=True`` markiert und traegt die scene_id — nur ``anchor_vid``
blieb None, sodass die normale Clip-Auswahl griff. Der Nutzer bekam also einen
Anker angezeigt, der auf ein beliebiges Video zeigt.

Der Sync-Pfad (`services/anchor_sync_service.py:68-75`) kennt dieselbe Form
seit jeher und loest sie korrekt auf.
"""

import inspect

from services.anchor_sync_service import _resolve_scene_id
from services.pacing_service import _auto_edit_phase3_inner


def test_die_vorausloesung_kennt_die_clip_form():
    """Quellcode-Guard — der Block sitzt in einer 900-Zeilen-Funktion.

    Ein echter Durchlauf braucht Audio, Video-Metadaten, Stems und die GPU;
    der Beleg dafuer ist der dokumentierte Durchstich an echten Projektdaten.
    Dieser Test haelt nur fest, dass die Sonderform nicht wieder herausfaellt.
    """
    src = inspect.getsource(_auto_edit_phase3_inner)
    block = src.split("anchor_scene_map: dict[str, int]", 1)[1].split("if scene_ids:", 1)[0]

    assert 'sid.startswith("clip_")' in block
    assert 'int(sid[len("clip_"):])' in block


def test_dieselbe_form_wie_im_sync_pfad():
    """Beide Wege muessen 'clip_7' gleich verstehen — sonst driften sie wieder."""
    assert _resolve_scene_id(None, "clip_7") == (7, 0.0)


def test_kaputte_clip_form_wird_nicht_stillschweigend_zur_szene():
    assert _resolve_scene_id(None, "clip_abc") is None


def test_leere_scene_id_bleibt_ohne_wirkung():
    assert _resolve_scene_id(None, "") is None
    assert _resolve_scene_id(None, "   ") is None
