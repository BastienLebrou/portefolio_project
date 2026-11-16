"""Markdown report -> sober PDF in the ScruTech palette (core PDF fonts, no font files needed)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace


@dataclass(frozen=True)
class Brand:
    """Colours and cover style of one organisation (RGB tuples)."""

    name: str
    primary: tuple[int, int, int]  # titles, table headers
    accent: tuple[int, int, int]  # thin rules
    ink: tuple[int, int, int]  # body text
    grey: tuple[int, int, int]  # header / footer
    paper: tuple[int, int, int]  # zebra rows
    cover_bg: tuple[int, int, int] | None  # None: white cover with a primary colour band
    tagline: str = ""


BRANDS = {
    # ScruTech (brand/README.md): bordeaux, olive, cream cover.
    "scrutech": Brand(
        "ScruTech", (102, 28, 26), (92, 106, 48), (43, 38, 29), (110, 104, 92), (251, 247, 236),
        (241, 232, 210), "ScruTech : voir ce que l'oeil ne voit pas.",
    ),
    # OneMW: indigo and green taken from the logo.
    "onemw": Brand(
        "OneMW", (54, 61, 145), (124, 252, 90), (30, 30, 40), (90, 90, 100), (243, 244, 250), None
    ),
}  # fmt: skip
_ASCII = {
    "≤": "<=",
    "≥": ">=",
    "→": "->",
    "œ": "oe",
    "Œ": "OE",
    "’": "'",
    "‘": "'",
    "–": "-",
    "—": "-",
    "…": "...",
    "•": "-",
    "×": "x",
    "²": "2",
    "³": "3",
    "≈": "~",
    "⚠️": "[!]",
    " ": " ",
    "₂": "2",
    "ˇ": "",
}


def _latin1(text: str) -> str:
    for a, b in _ASCII.items():
        text = text.replace(a, b)
    return text.encode("latin-1", "replace").decode("latin-1")


def _plain(text: str) -> str:
    return re.sub(r"[*`]", "", _latin1(text)).replace("__", "")


def _inline(text: str) -> str:
    """Keep **bold**; turn *italic* into fpdf2's __italic__."""
    text = re.sub(r"^_(.+)_$", r"__\1__", _latin1(text))  # a whole-line _note_
    return re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"__\1__", text)


def render(
    md: str,
    out: Path,
    title: str,
    subtitle: str,
    logo: Path | None = None,
    brand: str = "scrutech",
    *,
    front: bool = True,
) -> None:
    """Write the PDF: cover (logo once), then the Markdown body with branded tables."""
    b = BRANDS[brand]

    class Doc(FPDF):
        def header(self) -> None:
            if self.page_no() == 1 and front:
                return
            self.set_font("Helvetica", size=8)
            self.set_text_color(*b.grey)
            self.set_y(8)
            self.cell(0, 4, _latin1(f"{b.name}  |  {title}"), new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*b.primary)
            self.set_line_width(0.3)
            self.line(15, 13, 195, 13)
            self.set_y(18)

        def footer(self) -> None:
            if self.page_no() == 1 and front:
                return
            self.set_y(-12)
            self.set_font("Helvetica", size=8)
            self.set_text_color(*b.grey)
            self.cell(0, 4, f"{b.name}  -  page {self.page_no() - (1 if front else 0)}", align="C")

    pdf = Doc()
    pdf.set_margins(15, 18, 15)
    pdf.set_auto_page_break(True, 16)

    if front:
        # cover
        pdf.add_page()
        if b.cover_bg:
            pdf.set_fill_color(*b.cover_bg)
            pdf.rect(0, 0, 210, 297, "F")
            if logo and logo.exists():
                pdf.image(str(logo), x=15, y=18, w=34)
            pdf.set_fill_color(*b.accent)
            pdf.rect(15, 100, 24, 1.6, "F")
            top = 108
        else:
            pdf.set_fill_color(*b.primary)
            pdf.rect(0, 0, 210, 78, "F")
            if logo and logo.exists():
                pdf.image(str(logo), x=15, y=14, w=24)
            pdf.set_fill_color(*b.accent)
            pdf.rect(15, 56, 24, 1.6, "F")
            pdf.set_xy(15, 62)
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(0, 6, "DOSSIER TECHNIQUE")
            top = 92
        pdf.set_xy(15, top)
        pdf.set_text_color(*b.primary)
        pdf.set_font("Helvetica", "B", 26)
        pdf.multi_cell(180, 11, _latin1(title), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=13)
        pdf.set_text_color(*b.grey)
        pdf.ln(3)
        pdf.multi_cell(180, 7, _latin1(subtitle), new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(250)
        pdf.set_font("Helvetica", size=9)
        note = (
            f"{time.strftime('%d/%m/%Y')}\n"
            "Analyse documentaire (GBIF, INPN), sans inventaire de terrain.\n"
            "Ne remplace ni l'étude d'impact ni les inventaires."
        )
        if b.tagline:
            note += "\n" + b.tagline
        pdf.multi_cell(180, 5, _latin1(note), new_x="LMARGIN", new_y="NEXT")

    def toc(doc: FPDF, outline: list) -> None:
        doc.set_font("Helvetica", "B", 14)
        doc.set_text_color(*b.primary)
        doc.set_xy(15, 20)
        doc.cell(0, 10, "Table des matieres", new_x="LMARGIN", new_y="NEXT")
        doc.ln(4)
        doc.set_font("Helvetica", size=10)
        doc.set_text_color(*b.ink)
        for s in outline:
            link = doc.add_link(page=s.page_number)
            doc.set_x(15 + 6 * s.level)
            doc.cell(150 - 6 * s.level, 6.5, _latin1(s.name), link=link)
            doc.cell(
                0, 6.5, str(s.page_number - 1), align="R", link=link, new_x="LMARGIN", new_y="NEXT"
            )

    if front:
        pdf.add_page()
        pdf.insert_toc_placeholder(toc, pages=1)
    else:
        pdf.add_page()
    pdf.set_text_color(*b.ink)
    pdf.set_font("Helvetica", size=9.5)
    lines, i = md.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("# ") or line.startswith("Généré le"):
            i += 1
            continue
        if line.startswith("## Table des matières"):  # the PDF builds its own, with page numbers
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not set(lines[i]) <= set("|- "):
                    rows.append([_plain(c.strip()) for c in lines[i].strip("|").split("|")])
                i += 1
            _table(pdf, rows, b)
            continue
        if m := re.match(r"!\[.*?\]\((.*?)\)", line):
            img = out.parent / m[1]
            if img.exists():
                pdf.ln(2)
                if m[1].startswith("R/") or "schema" in m[1]:
                    pdf.image(str(img), w=150, x=30)
                else:  # maps
                    pdf.image(str(img), w=84, x=63)
                pdf.ln(2)
        elif m := re.match(r"(#+) (.*)", line):
            level = len(m[1])
            pdf.start_section(_plain(m[2]), level=level - 2)
            pdf.ln(3 if level == 2 else 1.5)
            pdf.set_font("Helvetica", "B", {2: 13, 3: 10.5}.get(level, 10))
            pdf.set_text_color(*b.primary)
            pdf.multi_cell(0, 6.5, _plain(m[2]), new_x="LMARGIN", new_y="NEXT")
            if level == 2:
                pdf.set_fill_color(*b.accent)
                pdf.rect(15, pdf.get_y(), 14, 0.9, "F")
                pdf.ln(2)
            pdf.set_font("Helvetica", size=9.5)
            pdf.set_text_color(*b.ink)
        elif re.match(r"\s*- ", line):
            indent = (len(line) - len(line.lstrip())) / 2
            pdf.set_x(15 + 4 + 5 * indent)
            pdf.multi_cell(
                180 - 4 - 5 * indent,
                5,
                "- " + _inline(line.lstrip()[2:]),
                markdown=True,
                align="L",
                new_x="LMARGIN",
                new_y="NEXT",
            )
        elif line.strip():
            pdf.multi_cell(
                0, 4.5, _inline(line), markdown=True, align="J", new_x="LMARGIN", new_y="NEXT"
            )
            pdf.ln(0.8)
        i += 1
    pdf.output(str(out))


def _table(pdf: FPDF, rows: list[list[str]], b: Brand) -> None:
    n = len(rows[0])
    chars = [min(60, max(6, max(len(r[k]) for r in rows if k < len(r)))) for k in range(n)]
    widths = [w / sum(chars) * 180 for w in chars]
    pdf.set_font("Helvetica", size=7)
    pdf.set_text_color(*b.ink)
    pdf.set_fill_color(*b.paper)
    with pdf.table(
        col_widths=widths,
        text_align="LEFT",
        line_height=3.9,
        width=180,
        headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=b.primary),
        cell_fill_color=b.paper,
        cell_fill_mode="ROWS",
    ) as t:
        for r in rows:
            row = t.row()
            for k in range(n):
                row.cell(r[k] if k < len(r) else "")
    pdf.set_font("Helvetica", size=9.5)
    pdf.ln(2)
