"""Processing diagram of the GBIF data (what was downloaded, kept, set aside) with exact counts."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

INDIGO, GREEN, GREY = "#363D91", "#2E9E44", "#6B6F80"


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def processing_diagram(counts: dict, meta: dict, path: Path, primary: str = INDIGO) -> None:
    """Flow chart: download by slices -> quality control -> classification -> stakes -> report."""
    fig, ax = plt.subplots(figsize=(7.4, 4.3))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 60)
    ax.axis("off")

    def box(x, y, w, h, title, lines, color=primary, fc="white"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                    fc=fc, ec=color, lw=1.4))  # fmt: skip
        ax.text(x + w / 2, y + h - 2.0, title, ha="center", va="top", fontsize=7.0,
                fontweight="bold", color=color)  # fmt: skip
        ax.text(
            x + w / 2,
            y + h - 5.4,
            "\n".join(lines),
            ha="center",
            va="top",
            fontsize=6.0,
            color="#222222",
            linespacing=1.35,
        )

    def arrow(x1, y1, x2, y2):
        ax.annotate(
            "", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=GREY, lw=1.2)
        )

    a, d = counts.get("annee_min", ""), counts.get("annee_max", "")
    ann = meta.get("annoncees", counts["telecharge"])
    sans_rang = counts["avec_coordonnees"] - counts["rang_espece"]
    box(
        1,
        40,
        22,
        17,
        "1. Collecte GBIF",
        [
            "Rayon de 5 km",
            f"{_fmt(ann)} observations",
            f"de {a} à {d}",
            "toutes années",
        ],
    )
    box(
        27,
        40,
        23,
        17,
        "2. Téléchargement",
        [
            "Tranches par année,",
            "jeu de données et mois",
            f"{_fmt(counts['telecharge'])} téléchargées",
            f"{meta.get('pages_perdues', 0)} page perdue",
        ],
    )
    box(
        54,
        40,
        22,
        17,
        "3. Contrôle",
        [
            f"Sans rang espèce : {_fmt(sans_rang)}",
            f"Doublons : {_fmt(counts['doublons'])}",
            f"Imprécises (annexe B) : {_fmt(counts['imprecis'])}",
            f"Avant {counts.get('from_year', '')} : {_fmt(counts.get('avant_periode', 0))}",
        ],
        color=GREY,
    )
    box(
        79,
        40,
        20,
        17,
        "4. Retenues",
        [
            f"{_fmt(counts['retenues'])} précises",
            f"dont {_fmt(counts['historiques'])} d'avant 2010",
            "signalées comme historiques",
        ],
        color=GREEN,
    )
    box(
        79,
        20,
        20,
        17,
        "5. Classement",
        ["Groupe, protection,", "directives, liste rouge,", "sensibilité au solaire"],
    )
    box(
        54,
        20,
        22,
        17,
        "6. Croisement INPN",
        ["Zonages de protection", "ZNIEFF, Natura 2000", "distances aux parcelles"],
    )
    box(27, 20, 23, 17, "7. Enjeux", ["Fort, modéré, faible", "pour chaque observation"])
    box(
        1, 20, 22, 17, "8. Analyse sous R", ["Tableaux et graphiques", "par groupe et par distance"]
    )
    box(
        1,
        1,
        98,
        14,
        "9. Rapport",
        ["Habitats, espèces, incidences, zonages, mesures d'évitement et de réduction, annexes"],
        color=primary,
    )
    arrow(23.5, 48, 26.5, 48)
    arrow(50.5, 48, 53.5, 48)
    arrow(76.5, 48, 78.5, 48)
    arrow(89, 39.5, 89, 37.5)
    arrow(78.5, 28.5, 76.5, 28.5)
    arrow(53.5, 28.5, 50.5, 28.5)
    arrow(26.5, 28.5, 23.5, 28.5)
    arrow(12, 19.5, 12, 15.5)
    ax.set_title(
        "Traitement des données GBIF", fontsize=10, fontweight="bold", loc="left", color="#222222"
    )
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
