"""
Centralised QSS theme. Keeping all styling in one place guarantees visual
consistency and makes the look easy to maintain.
"""

# Colour palette — a modern, dark "Fluent"-inspired theme.
COLORS = {
    "bg": "#1e1f26",
    "surface": "#2a2c37",
    "surface_alt": "#33353f",
    "border": "#3a3d4a",
    "text": "#e8e9ed",
    "text_dim": "#9aa0ad",
    "accent": "#4f8cff",
    "green": "#2ecc71",
    "red": "#ff5c5c",
}

STYLESHEET = f"""
QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}

#Card {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}

QLabel#Title {{
    font-size: 18px;
    font-weight: 600;
}}

QLabel#Subtitle {{
    color: {COLORS['text_dim']};
    font-size: 12px;
}}

QLabel#FieldLabel {{
    color: {COLORS['text_dim']};
    font-size: 12px;
}}

QLabel#FieldValue {{
    font-size: 13px;
    font-weight: 500;
}}

QComboBox {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 12px;
}}
QComboBox:hover {{ border-color: {COLORS['accent']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    selection-background-color: {COLORS['accent']};
    outline: none;
    padding: 4px;
}}

QPushButton {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{ border-color: {COLORS['accent']}; }}
QPushButton:pressed {{ background-color: {COLORS['border']}; }}

QPlainTextEdit {{
    background-color: {COLORS['surface_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
