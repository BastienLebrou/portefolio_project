"""The ScruTech look: the brand palette as a Qt style sheet.

Colours and type come from the brand folder (crème, papier, bordeaux, brique, olive, encre;
Bricolage Grotesque for titles, IBM Plex for the rest, with system fallbacks when a font is
not installed).
"""

from __future__ import annotations

CREME = "#F1E8D2"
PAPIER = "#FBF7EC"
BORDEAUX = "#661C1A"
BRIQUE = "#B23F2C"
OLIVE = "#5C6A30"
OLIVE_FONCE = "#37401D"
ENCRE = "#2B261D"
DOUX = "#6B6150"
TRAIT = "#D8D2BE"

TITRE = "'Bricolage Grotesque', 'Arial Black', Arial"
CORPS = "'IBM Plex Sans', 'Segoe UI', sans-serif"
MONO = "'IBM Plex Mono', Consolas, monospace"

QSS = f"""
QWidget {{ background: {CREME}; color: {ENCRE}; font-family: {CORPS}; font-size: 14px; }}
QLabel, QCheckBox {{ background: transparent; }}
QLabel#title {{ font-family: {TITRE}; font-size: 26px; font-weight: 800; color: {BORDEAUX}; }}
QLabel#subtitle {{ color: {DOUX}; font-family: {MONO}; font-size: 12px; }}
QLabel#section {{ font-family: {TITRE}; font-size: 17px; font-weight: 700; color: {BORDEAUX}; }}
QLabel#tileName {{ font-family: {TITRE}; font-size: 15px; font-weight: 700; color: {BORDEAUX}; }}
QLabel#tileText {{ color: {DOUX}; font-size: 12px; }}
QFrame#card, QFrame#tile {{ background: {PAPIER}; border: 1px solid {TRAIT}; border-radius: 12px; }}
QFrame#tile:hover {{ border: 1px solid {BRIQUE}; }}
QPushButton {{ background: {PAPIER}; border: 1px solid {TRAIT}; border-radius: 8px;
  padding: 7px 14px; }}
QPushButton:hover {{ border-color: {BRIQUE}; }}
QPushButton:disabled {{ color: {DOUX}; border-color: {TRAIT}; }}
QPushButton#primary {{ background: {BORDEAUX}; color: {PAPIER}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: {BRIQUE}; }}
QPushButton#primary:disabled {{ background: {TRAIT}; color: {DOUX}; }}
QPlainTextEdit, QTextEdit {{ background: {PAPIER}; border: 1px solid {TRAIT}; border-radius: 8px;
  font-family: {MONO}; font-size: 12px; }}
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit {{ background: {PAPIER}; border: 1px solid {TRAIT};
  border-radius: 6px; padding: 4px 6px; }}
QProgressBar {{ background: {PAPIER}; border: 1px solid {TRAIT}; border-radius: 8px; height: 16px;
  text-align: center; }}
QProgressBar::chunk {{ background: {OLIVE}; border-radius: 7px; }}
QScrollArea {{ border: none; }}
QToolTip {{ background: {PAPIER}; color: {ENCRE}; border: 1px solid {TRAIT}; }}
"""
