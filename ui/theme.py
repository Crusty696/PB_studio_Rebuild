"""PB Studio v0.5.1 — Premium Gold-Accent Theme.

A high-agency, 'anti-slop' theme based on the docs/ui_redesign_v2.html.
Uses a gold/amber palette with deep slate surfaces.
"""

# Color palette (Refined)
BG0 = "#0a0d12"  # Deep Canvas
BG1 = "#0f1318"  # Subtle Overlay
BG2 = "#161c26"  # Surface
BG3 = "#1e2632"  # Elevated Surface
BG4 = "#283040"  # Active/Hover Surface
ACCENT = "#d4a44a"  # Premium Gold
ACCENT_BRIGHT = "#f0c866" # Highlight Gold
ACCENT_DIM = "#a07830"  # Deep Gold
ACCENT_MUTED = "rgba(212, 164, 74, 38)" # Subtle Gold Wash (alpha 0.15 * 255 ≈ 38)

OK = "#4ade80"
WARN = "#fbbf24"
ERR = "#f87171"
INFO = "#60a5fa"
INFO_CYAN = "#00e5ff"    # CPU status bar
DANGER_BG = "#3a1010"   # Error-state progress bar background

T1 = "#f9fafb"  # High Contrast Text (Off-White)
T2 = "#9ca3af"  # Secondary Text
T3 = "#6b7280"  # Muted/Label Text
T4 = "#4b5563"  # Deep Muted Text

def get_stylesheet() -> str:
    return f"""
    /* === GLOBAL === */
    QWidget {{
        background-color: {BG0};
        color: {T1};
        font-family: 'Segoe UI Variable Text', 'Segoe UI', system-ui, -apple-system, sans-serif;
        font-size: 12px;
        outline: none;
    }}

    QMainWindow {{
        background-color: {BG0};
    }}

    /* === BUTTONS === */
    QPushButton {{
        background-color: {BG3};
        color: {T2};
        border: 1px solid rgba(255, 255, 255, 20);
        border-radius: 8px;
        padding: 5px 14px;
        font-weight: 600;
        font-size: 11px;
        min-height: 28px;
    }}
    QPushButton:hover {{
        background-color: {BG4};
        color: {T1};
        border: 1px solid rgba(255, 255, 255, 40);
    }}
    QPushButton:pressed {{
        background-color: {BG2};
        color: {ACCENT};
        padding-top: 6px;
        padding-bottom: 4px;
    }}
    QPushButton:disabled {{
        background-color: {BG1};
        color: {T4};
        border: 1px solid rgba(255, 255, 255, 10);
    }}

    /* Primary Gold / Accent Buttons */
    QPushButton[objectName="btn_accent"],
    QPushButton[objectName="btn_primary"],
    QPushButton#btn_accent,
    QPushButton#btn_primary {{
        background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_DIM});
        color: {BG0};
        border: none;
        font-weight: 700;
        /* letter-spacing not supported in Qt QSS */
    }}
    QPushButton[objectName="btn_accent"]:hover,
    QPushButton[objectName="btn_primary"]:hover {{
        background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_BRIGHT}, stop:1 {ACCENT});
    }}
    QPushButton[objectName="btn_accent"]:pressed,
    QPushButton[objectName="btn_primary"]:pressed {{
        background-color: {ACCENT_DIM};
    }}

    /* Secondary / Ghost Buttons */
    QPushButton[objectName="btn_secondary"] {{
        background-color: transparent;
        border: 1px solid {BG4};
    }}
    QPushButton[objectName="btn_secondary"]:hover {{
        background-color: {BG3};
        border-color: {T3};
    }}

    /* AI Learning / KI-Gedaechtnis Buttons */
    QPushButton[objectName="btn_learn_ai"],
    QPushButton[objectName="btn_ai"] {{
        background-color: {ACCENT_MUTED};
        border: 1px solid {ACCENT_DIM};
        color: {ACCENT_BRIGHT};
        font-weight: 700;
        font-size: 10px;
        /* letter-spacing not supported in Qt QSS */
        border-radius: 3px;
    }}
    QPushButton[objectName="btn_learn_ai"]:hover,
    QPushButton[objectName="btn_ai"]:hover {{
        background-color: rgba(212, 164, 74, 71);
        border-color: {ACCENT};
    }}
    QPushButton[objectName="btn_learn_ai"]:pressed,
    QPushButton[objectName="btn_ai"]:pressed {{
        background-color: {ACCENT_DIM};
        color: #0a0d12;
    }}

    /* === LABELS === */
    QLabel {{
        background: transparent;
        color: {T2};
    }}
    QLabel#title {{
        color: {T1};
        font-weight: 700;
        font-size: 14px;
    }}
    QLabel#subtitle {{
        color: {T3};
        font-size: 11px;
        /* text-transform not supported in Qt QSS — use Python .upper() */
        /* letter-spacing not supported in Qt QSS */
    }}

    /* === INPUTS === */
    QLineEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit {{
        background-color: {BG1};
        color: {T1};
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 11px;
        min-height: 26px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {ACCENT};
        background-color: {BG2};
    }}

    /* === COMBOBOX === */
    QComboBox {{
        background-color: {BG1};
        color: {T1};
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 11px;
        min-height: 26px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {T3};
        margin-right: 8px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG2};
        color: {T1};
        border: 1px solid {BG3};
        border-radius: 6px;
        selection-background-color: {ACCENT_MUTED};
        selection-color: {ACCENT_BRIGHT};
        outline: none;
    }}

    /* === TABLES & TREES === */
    QTableWidget, QTreeWidget, QListView {{
        background-color: {BG1};
        alternate-background-color: {BG2};
        color: {T2};
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 8px;
        gridline-color: rgba(255,255,255,0.03);
        font-size: 11px;
    }}
    QTableWidget::item, QTreeWidget::item {{
        padding: 6px 10px;
        border-bottom: 1px solid rgba(255,255,255,0.02);
    }}
    QTableWidget::item:selected, QTreeWidget::item:selected {{
        background-color: {ACCENT_MUTED};
        color: {T1};
        border-left: 3px solid {ACCENT};
    }}
    QHeaderView::section {{
        background-color: {BG2};
        color: {T3};
        border: none;
        border-bottom: 1px solid {BG3};
        padding: 6px 10px;
        font-size: 10px;
        font-weight: 700;
        /* text-transform not supported in Qt QSS — use Python .upper() */
        /* letter-spacing not supported in Qt QSS */
    }}

    /* === SCROLLBARS === */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {BG4};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {T3};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BG4};
        border-radius: 4px;
        min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {T3};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

    /* === PROGRESS BAR === */
    QProgressBar {{
        background-color: {BG1};
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 4px;
        text-align: center;
        color: {T1};
        font-weight: 700;
        font-size: 9px;
        height: 14px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_DIM}, stop:1 {ACCENT_BRIGHT});
        border-radius: 3px;
    }}

    /* === SLIDERS === */
    QSlider::groove:horizontal {{
        background: {BG2};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {ACCENT};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
        border: 2px solid {BG0};
    }}
    QSlider::handle:horizontal:hover {{
        background: {ACCENT_BRIGHT};
        transform: scale(1.1);
    }}

    /* === TABS === */
    QTabWidget::pane {{
        background-color: {BG1};
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 10px;
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {T3};
        padding: 8px 20px;
        font-weight: 700;
        font-size: 11px;
        border: none;
        border-bottom: 2px solid transparent;
        margin-right: 4px;
    }}
    QTabBar::tab:selected {{
        color: {ACCENT_BRIGHT};
        border-bottom: 2px solid {ACCENT};
        background-color: {ACCENT_MUTED};
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}
    QTabBar::tab:hover:!selected {{
        color: {T2};
        background-color: {BG2};
    }}

    /* === DOCK WIDGETS === */
    QDockWidget {{
        background-color: {BG2};
        color: {T1};
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }}
    QDockWidget::title {{
        background-color: {BG3};
        color: {T2};
        padding: 8px 12px;
        font-weight: 700;
        font-size: 11px;
        /* text-transform not supported in Qt QSS — use Python .upper() */
        /* letter-spacing not supported in Qt QSS */
        border-bottom: 1px solid rgba(255,255,255,0.05);
    }}

    /* === TEXTEDIT (Console, Log) === */
    QTextEdit, QPlainTextEdit {{
        background-color: {BG0};
        color: {T2};
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 8px;
        font-family: 'Cascadia Code', 'Consolas', 'JetBrains Mono', monospace;
        font-size: 11px;
        /* line-height not supported in Qt QSS */
        padding: 10px;
    }}

    /* === GROUPBOX === */
    QGroupBox {{
        background-color: {BG2};
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
        margin-top: 14px;
        padding-top: 20px;
        font-weight: 700;
        color: {ACCENT};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0px 10px;
        color: {T3};
        font-size: 10px;
        /* text-transform not supported in Qt QSS — use Python .upper() */
        letter-spacing: 1.5px;
    }}

    /* === FRAMES (Cards) === */
    QFrame[objectName="card"] {{
        background-color: {BG2};
        border: 1px solid rgba(255,255,255,0.05);
        border-radius: 12px;
    }}
    QFrame[objectName="card_active"] {{
        background-color: {BG2};
        border: 1px solid {ACCENT_MUTED};
        border-radius: 12px;
    }}

    /* === SPLITTER === */
    QSplitter::handle {{
        background-color: rgba(255,255,255,0.03);
    }}
    QSplitter::handle:hover {{
        background-color: {ACCENT_MUTED};
    }}

    /* === STATUSBAR === */
    QStatusBar {{
        background-color: {BG0};
        color: {T3};
        border-top: 1px solid rgba(255,255,255,0.03);
        font-size: 10px;
        min-height: 22px;
    }}

    /* === MENU === */
    QMenu {{
        background-color: {BG2};
        color: {T1};
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        padding: 5px;
    }}
    QMenu::item {{
        padding: 6px 28px;
        border-radius: 5px;
        margin: 1px;
    }}
    QMenu::item:selected {{
        background-color: {ACCENT_MUTED};
        color: {ACCENT_BRIGHT};
    }}
    QMenu::separator {{
        height: 1px;
        background: rgba(255,255,255,0.05);
        margin: 4px 10px;
    }}

    /* === CHECKBOX === */
    QCheckBox {{
        color: {T2};
        spacing: 8px;
        font-weight: 500;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 4px;
        background-color: {BG1};
    }}
    QCheckBox::indicator:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
        image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='4' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E");
    }}
    """
