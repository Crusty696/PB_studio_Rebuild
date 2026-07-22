"""Praesentations-Konstanten des MEDIA-Workspace (QSS-Styles + Farb-Map).

AUFRAEUM B4: verbatim aus ``ui/workspaces/media_workspace.py`` ausgelagert.
Reine zustandslose Nicht-Qt-Daten (Strings + dict) — kein Qt-Import,
kein State, kein Logik-Change. Werden im Ursprungsmodul re-exportiert,
Public-API unveraendert.
"""

_MODE_BTN_STYLE = """
    QPushButton {
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 1px;
        padding: 8px 24px;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        background: #1e2632;
        color: #9ca3af;
    }
    QPushButton:checked {
        border: 1px solid #d4a44a;
        color: #f0c866;
        background: rgba(212, 164, 74, 0.12);
    }
    QPushButton:hover:!checked {
        background: #283040;
        color: #f9fafb;
    }
"""


_VIEW_TOGGLE_STYLE = """
    QPushButton {
        font-size: 13px;
        background: #1a2030;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 4px;
        color: #98a2b1;
    }
    QPushButton:checked {
        background: rgba(212,164,74,0.15);
        border: 1px solid #d4a44a;
        color: #f0c866;
    }
    QPushButton:hover:!checked {
        background: #222d40;
        color: #e5e7eb;
    }
"""

_CARD_STYLE = """
    QFrame {
        background: #161c26;
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
        padding: 10px;
    }
"""

_CARD_TITLE_STYLE = (
    "color: #d4a44a; font-weight: 700; font-size: 10px; "
    "letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px;"
)
_CARD_VALUE_STYLE = (
    "color: #f9fafb; font-size: 20px; font-weight: 800;"
)
_CARD_LABEL_STYLE = (
    "color: #98a2b1; font-size: 10px; font-weight: 500;"
)
_CARD_TAG_BASE = (
    "font-size: 9px; font-weight: 600; padding: 2px 6px; "
    "border-radius: 3px;"
)

_SEGMENT_COLORS = {
    "INTRO": "#4ade80",
    "BUILDUP": "#d4a44a",
    "DROP": "#ef4444",
    "BREAKDOWN": "#00e5ff",
    "OUTRO": "#bf40ff",
    "VERSE": "#60a5fa",
    "CHORUS": "#f97316",
    "BRIDGE": "#a78bfa",
}
