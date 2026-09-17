"""Biotrame — maillage hexagonal H3 de priorisation écologique.

Croise ce que ScruTech calcule (indicateurs satellite) et ce qui existe déjà (Natura 2000,
ZNIEFF, Trame Verte et Bleue) sur une grille d'hexagones, pour hiérarchiser les zones où
accélérer les mesures écologiques / de compensation, à partir d'une emprise seule.
"""

from biotrame.mesh import hex_grid
from biotrame.score import classify, priority_score, score_mesh

__all__ = ["classify", "hex_grid", "priority_score", "score_mesh"]
