"""PB Studio v0.5 Theme — Gold Accent Dark Theme.

Basierend auf dem UI-Redesign Prototyp (docs/ui_redesign_v2.html).
Aktiviert via: app.setStyleSheet(get_stylesheet()) oder widget.setStyleSheet(get_stylesheet())
"""

# Color palette
BG0 = "#0a0d12"
BG1 = "#0f1318"
BG2 = "#161c26"
BG3 = "#1e2632"
BG4 = "#283040"
ACCENT = "#d4a44a"
ACCENT_BRIGHT = "#f0c866"
ACCENT_DIM = "#a07830"
OK = "#4ade80"
WARN = "#fbbf24"
ERR = "#f87171"
INFO = "#60a5fa"
T1 = "#e8e6e3"
T2 = "#9ca3af"
T3 = "#6b7280"

def get_stylesheet() -> str:
    return f"""
    /* === GLOBAL === */
    QWidget {{
        background-color: {BG0};
        color: {T1};
        font-family: 'Segoe UI', 'Inter', sans-serif;
        font-size: 12px;
    }}

    QMainWindow {{
        background-color: {BG0};
    }}

    /* === BUTTONS === */
    QPushButton {{
        background-color: {BG3};
        color: {T2};
        border: 1px solid rgba(255,255,255,15);
        border-radius: 6px;
        padding: 4px 12px;
        font-weight: 600;
        font-size: 11px;
        min-height: 28px;
    }}
    QPushButton:hover {{
        background-color: {BG4};
        color: {T1};
        border: 1px solid rgba(255,255,255,25);
    }}
    QPushButton:pressed {{
        background-color: {ACCENT_DIM};
        color: {BG0};
    }}
    QPushButton:disabled {{
        background-color: {BG2};
        color: {T3};
        border: 1px solid rgba(255,255,255,8);
    }}

    /* Primary gold buttons (objectName="btn_primary" or "btn_accent") */
    QPushButton[objectName="btn_accent"],
    QPushButton[objectName="btn_primary"] {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {ACCENT_DIM});
        color: {BG0};
        border: none;
        font-weight: 700;
    }}
    QPushButton[objectName="btn_accent"]:hover,
    QPushButton[objectName="btn_primary"]:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_BRIGHT}, stop:1 {ACCENT});
    }}

    /* Danger buttons */
    QPushButton[objectName="btn_danger"] {{
        background-color: {BG3};
        color: {ERR};
        border: 1px solid rgba(248,113,113,77);
    }}
    QPushButton[objectName="btn_danger"]:hover {{
        background-color: rgba(248,113,113,38);
        color: #ff9999;
    }}

    /* === LABELS === */
    QLabel {{
        background: transparent;
        color: {T1};
    }}

    /* === INPUTS === */
    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {BG1};
        color: {T1};
        border: 1px solid rgba(255,255,255,15);
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 11px;
        min-height: 24px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {ACCENT};
    }}

    /* === COMBOBOX === */
    QComboBox {{
        background-color: {BG1};
        color: {T1};
        border: 1px solid rgba(255,255,255,15);
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 11px;
        min-height: 24px;
    }}
    QComboBox:hover {{
        border: 1px solid rgba(255,255,255,25);
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {T3};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG2};
        color: {T1};
        border: 1px solid rgba(255,255,255,15);
        selection-background-color: rgba(212,164,74,38);
        selection-color: {ACCENT_BRIGHT};
        outline: none;
    }}

    /* === TABLES === */
    QTableWidget, QTreeWidget {{
        background-color: {BG1};
        alternate-background-color: {BG2};
        color: {T2};
        border: 1px solid rgba(255,255,255,10);
        border-radius: 6px;
        gridline-color: rgba(255,255,255,6);
        font-size: 11px;
    }}
    QTableWidget::item, QTreeWidget::item {{
        padding: 4px 8px;
        border-bottom: 1px solid rgba(255,255,255,3);
    }}
    QTableWidget::item:selected, QTreeWidget::item:selected {{
        background-color: rgba(212,164,74,38);
        color: {T1};
    }}
    QTableWidget::item:hover, QTreeWidget::item:hover {{
        background-color: {BG3};
    }}
    QHeaderView::section {{
        background-color: {BG2};
        color: {T3};
        border: none;
        border-bottom: 1px solid rgba(255,255,255,10);
        border-right: 1px solid rgba(255,255,255,5);
        padding: 5px 8px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
    }}

    /* === SCROLLBARS === */
    QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BG4};
        border-radius: 3px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {T3};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BG4};
        border-radius: 3px;
        min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {T3};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* === PROGRESS BAR === */
    QProgressBar {{
        background-color: {BG1};
        border: none;
        border-radius: 3px;
        text-align: center;
        color: {T2};
        font-size: 11px;
        min-height: 16px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_DIM}, stop:1 {ACCENT_BRIGHT});
        border-radius: 2px;
    }}

    /* === SLIDERS === */
    QSlider::groove:horizontal {{
        background: {BG1};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {ACCENT};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {ACCENT_BRIGHT};
    }}

    /* === TABS === */
    QTabWidget::pane {{
        background-color: {BG1};
        border: 1px solid rgba(255,255,255,10);
        border-radius: 6px;
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {T3};
        padding: 6px 16px;
        font-weight: 600;
        font-size: 11px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {ACCENT_BRIGHT};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover:!selected {{
        color: {T2};
        background-color: {BG3};
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
        padding: 6px 10px;
        font-weight: 600;
        font-size: 11px;
        border-bottom: 1px solid rgba(255,255,255,10);
    }}

    /* === TEXTEDIT (Console, Log) === */
    QTextEdit {{
        background-color: {BG0};
        color: {T2};
        border: 1px solid rgba(255,255,255,10);
        border-radius: 4px;
        font-family: 'Cascadia Code', 'Consolas', monospace;
        font-size: 11px;
        padding: 6px;
    }}

    /* === GROUPBOX === */
    QGroupBox {{
        background-color: {BG2};
        border: 1px solid rgba(255,255,255,10);
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 16px;
        font-weight: 600;
        color: {T3};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 2px 8px;
        color: {T3};
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}

    /* === FRAMES (Cards) === */
    QFrame[objectName="card"] {{
        background-color: {BG2};
        border: 1px solid rgba(255,255,255,10);
        border-radius: 8px;
    }}

    /* === SPLITTER === */
    QSplitter::handle {{
        background-color: rgba(255,255,255,6);
    }}
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    QSplitter::handle:vertical {{
        height: 1px;
    }}

    /* === STATUSBAR === */
    QStatusBar {{
        background-color: {BG0};
        color: {T3};
        border-top: 1px solid rgba(255,255,255,6);
        font-size: 10px;
    }}
    QStatusBar::item {{
        border: none;
    }}

    /* === TOOLTIP === */
    QToolTip {{
        background-color: {BG3};
        color: {T1};
        border: 1px solid rgba(255,255,255,15);
        border-radius: 4px;
        padding: 4px 8px;
        font-size: 11px;
    }}

    /* === MENU === */
    QMenu {{
        background-color: {BG2};
        color: {T1};
        border: 1px solid rgba(255,255,255,15);
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 24px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: rgba(212,164,74,38);
        color: {ACCENT_BRIGHT};
    }}

    /* === CHECKBOX === */
    QCheckBox {{
        color: {T2};
        spacing: 6px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255,255,255,20);
        border-radius: 3px;
        background-color: {BG1};
    }}
    QCheckBox::indicator:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
    }}
    """
