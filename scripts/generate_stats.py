#!/usr/bin/env python3
"""Générateur de statistiques et de visuels du portfolio.

Lit l'historique Git réel du dépôt (aucun appel réseau), calcule des
statistiques d'activité et de composition, puis produit :

  - assets/banner-{light,dark}.svg     bannière d'accueil
  - assets/activity-{light,dark}.svg   commits par semaine (26 semaines)
  - assets/languages-{light,dark}.svg  répartition des langages (octets)
  - assets/weekdays-{light,dark}.svg   répartition par jour de la semaine
  - README.md                          bloc chiffré entre les marqueurs AUTO-STATS

Exécuté par .github/workflows/portfolio.yml toutes les 48 h, ou à la main :

    python3 scripts/generate_stats.py
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"

FONT = "system-ui, 'Segoe UI', Ubuntu, Helvetica, Arial, sans-serif"

# Jetons de couleur (palette validée — voir scripts du skill dataviz) ---------

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "border": "rgba(11,11,11,0.10)",
        "accent": "#2a78d6",
        "slots": ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948"],
        "other": "#898781",
        "seq": ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "border": "rgba(255,255,255,0.10)",
        "accent": "#3987e5",
        "slots": ["#3987e5", "#199e70", "#c98500", "#008300", "#9085e9", "#e66767"],
        "other": "#898781",
        "seq": ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
    },
}

# Couleur par entité (jamais par rang) : un langage garde sa couleur
# d'une régénération à l'autre, même si son classement change.
LANG_SLOT = {
    "Python": 0,
    "Markdown": 1,
    "YAML": 2,
    "TOML": 3,
    "SVG": 4,
    "Texte": 5,
}

EXT_LANG = {
    "py": "Python",
    "md": "Markdown",
    "yml": "YAML",
    "yaml": "YAML",
    "toml": "TOML",
    "svg": "SVG",
    "txt": "Texte",
    "json": "JSON",
    "sql": "SQL",
    "ipynb": "Notebook",
    "sh": "Shell",
    "cfg": "Config",
    "ini": "Config",
}

SKIP_PREFIXES = ("assets/",)  # fichiers générés : exclus du comptage
SKIP_SUFFIXES = (".lock", ".png", ".jpg", ".gitignore", ".pre-commit-config.yaml")

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
MOIS_ABR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
            "août", "sept.", "oct.", "nov.", "déc."]
JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def fr_num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fr_pct(x: float) -> str:
    return f"{x:.1f}".replace(".", ",") + " %"


# ── Collecte ────────────────────────────────────────────────────────────────

def commit_dates() -> list[date]:
    out = sh("git", "log", "--pretty=%ad", "--date=format:%Y-%m-%d")
    return [date.fromisoformat(line) for line in out.splitlines() if line.strip()]


def tracked_files() -> list[Path]:
    out = sh("git", "ls-files")
    return [ROOT / line for line in out.splitlines() if line.strip()]


def language_bytes() -> list[tuple[str, int]]:
    sizes: Counter[str] = Counter()
    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(SKIP_PREFIXES) or rel.endswith(SKIP_SUFFIXES):
            continue
        lang = EXT_LANG.get(path.suffix.lstrip(".").lower())
        if lang is None or not path.exists():
            continue
        sizes[lang] += path.stat().st_size
    ranked = sizes.most_common()
    top, rest = ranked[:5], ranked[5:]
    if rest:
        top.append(("Autres", sum(n for _, n in rest)))
    return top


def python_lines() -> int:
    total = 0
    for path in tracked_files():
        if path.suffix == ".py" and path.exists():
            total += sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))
    return total


def test_count() -> int:
    total = 0
    for path in tracked_files():
        if path.suffix == ".py" and path.name.startswith("test") and path.exists():
            total += len(re.findall(r"^\s*def test_", path.read_text(encoding="utf-8", errors="ignore"), re.M))
    return total


def project_count() -> int:
    dirs = {p.relative_to(ROOT).parts[0] for p in tracked_files() if len(p.relative_to(ROOT).parts) > 1}
    return len(dirs - {".github", "assets", "scripts"})


def weekly_series(dates: list[date], weeks: int = 26) -> list[tuple[date, int]]:
    """Commits par semaine ISO (lundi comme clef), fenêtre glissante."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    per_week = Counter(d - timedelta(days=d.weekday()) for d in dates)
    return [(m, per_week.get(m, 0)) for m in (monday - timedelta(weeks=w) for w in range(weeks - 1, -1, -1))]


# ── Briques SVG ─────────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_doc(width: int, height: int, theme: dict, body: str, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(label)}" '
        f'font-family="{FONT}">\n'
        f'<title>{esc(label)}</title>\n'
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" '
        f'fill="{theme["surface"]}" stroke="{theme["border"]}"/>\n'
        f"{body}</svg>\n"
    )


def text(x: float, y: float, s: str, fill: str, size: int = 12, weight: int = 400,
         anchor: str = "start", extra: str = "") -> str:
    w = f' font-weight="{weight}"' if weight != 400 else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{x:g}" y="{y:g}" font-size="{size}" fill="{fill}"{w}{a}{extra}>{esc(s)}</text>\n'


def bar_rounded_top(x: float, y: float, w: float, h: float, fill: str, r: float = 4) -> str:
    """Barre à sommet arrondi (4 px), carrée à la ligne de base."""
    r = min(r, w / 2, h)
    if h <= 0.5:
        return ""
    if r <= 0.6:
        return f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}"/>\n'
    return (
        f'<path d="M {x:.2f} {y + h:.2f} V {y + r:.2f} Q {x:.2f} {y:.2f} {x + r:.2f} {y:.2f} '
        f'H {x + w - r:.2f} Q {x + w:.2f} {y:.2f} {x + w:.2f} {y + r:.2f} V {y + h:.2f} Z" '
        f'fill="{fill}"/>\n'
    )


def nice_max(v: int) -> int:
    for cap in (4, 8, 12, 16, 20, 28, 40, 60, 80, 120, 160, 240, 400):
        if v <= cap:
            return cap
    return ((v // 400) + 1) * 400


def column_chart(series: list[tuple[str, int]], theme: dict, *, width: int, height: int,
                 title: str, subtitle: str, label_indices: set[int],
                 tick_every: int = 1) -> str:
    pad_l, pad_r, pad_t, pad_b = 46, 20, 58, 34
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    top = nice_max(max((v for _, v in series), default=1))
    body = [
        text(24, 30, title, theme["ink"], 15, 600),
        text(24, 47, subtitle, theme["ink2"], 12),
    ]
    for i in range(5):  # lignes de grille 0..top, très en retrait
        val = top * i // 4
        y = pad_t + plot_h - plot_h * i / 4
        stroke = theme["axis"] if i == 0 else theme["grid"]
        body.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="{stroke}" stroke-width="1"/>\n')
        body.append(text(pad_l - 8, y + 4, str(val), theme["muted"], 11, anchor="end",
                         extra=' font-variant-numeric="tabular-nums"'))
    band = plot_w / len(series)
    bw = min(24.0, band * 0.62)
    for i, (lab, v) in enumerate(series):
        cx = pad_l + band * i + band / 2
        h = plot_h * v / top
        y = pad_t + plot_h - h
        body.append(bar_rounded_top(cx - bw / 2, y, bw, h, theme["accent"]))
        if v and i in label_indices:  # étiquettes directes sélectives (pic, dernier point)
            body.append(text(cx, y - 6, str(v), theme["ink"], 11, 600, anchor="middle"))
        if lab and i % tick_every == 0:
            body.append(text(cx, height - 12, lab, theme["muted"], 11, anchor="middle"))
    return "".join(body)


def activity_svg(weeks: list[tuple[date, int]], theme: dict) -> str:
    labels = []
    seen_month = None
    for monday, _ in weeks:
        if monday.month != seen_month:
            labels.append(MOIS_ABR[monday.month - 1])
            seen_month = monday.month
        else:
            labels.append("")
    values = [v for _, v in weeks]
    peak = max(range(len(values)), key=values.__getitem__) if any(values) else -1
    marked = {peak, len(values) - 1} if peak >= 0 else set()
    series = list(zip(labels, values))
    body = column_chart(series, theme, width=840, height=240,
                        title="Activité du dépôt",
                        subtitle="Commits par semaine — 26 dernières semaines",
                        label_indices=marked)
    return svg_doc(840, 240, theme, body,
                   "Histogramme des commits par semaine sur les 26 dernières semaines")


def weekdays_svg(dates: list[date], theme: dict) -> str:
    counts = Counter(d.weekday() for d in dates)
    values = [counts.get(i, 0) for i in range(7)]
    peak = max(range(7), key=values.__getitem__) if any(values) else -1
    body = column_chart(list(zip(JOURS, values)), theme, width=408, height=240,
                        title="Rythme hebdomadaire",
                        subtitle="Commits par jour de la semaine",
                        label_indices={peak} if peak >= 0 else set())
    return svg_doc(408, 240, theme, body, "Histogramme des commits par jour de la semaine")


def languages_svg(langs: list[tuple[str, int]], theme: dict) -> str:
    width, height = 408, 240
    total = sum(n for _, n in langs) or 1
    pad, strip_y, strip_h = 24, 92, 12
    strip_w = width - 2 * pad
    body = [
        text(pad, 30, "Langages", theme["ink"], 15, 600),
        text(pad, 47, "Part des octets sources suivis par Git", theme["ink2"], 12),
        f'<clipPath id="strip"><rect x="{pad}" y="{strip_y}" width="{strip_w}" height="{strip_h}" rx="6"/></clipPath>\n',
        f'<g clip-path="url(#strip)">\n',
    ]
    extra_slot = 0
    colors = {}
    for name, _ in langs:
        if name == "Autres":
            colors[name] = theme["other"]
        elif name in LANG_SLOT:
            colors[name] = theme["slots"][LANG_SLOT[name]]
        else:  # langage imprévu : premier emplacement libre, ordre fixe
            while extra_slot in LANG_SLOT.values():
                extra_slot += 1
            colors[name] = theme["slots"][extra_slot % len(theme["slots"])]
            extra_slot += 1
    x = float(pad)
    for i, (name, n) in enumerate(langs):
        w = strip_w * n / total
        gap = 2 if i < len(langs) - 1 else 0  # écart de 2 px couleur de surface
        body.append(f'<rect x="{x:.2f}" y="{strip_y}" width="{max(w - gap, 1.5):.2f}" '
                    f'height="{strip_h}" fill="{colors[name]}"/>\n')
        x += w
    body.append("</g>\n")
    col_w, row_h = (width - 2 * pad) / 2, 30
    for i, (name, n) in enumerate(langs):
        cx = pad + (i % 2) * col_w
        cy = strip_y + 42 + (i // 2) * row_h
        body.append(f'<rect x="{cx:g}" y="{cy - 10:g}" width="10" height="10" rx="3" fill="{colors[name]}"/>\n')
        body.append(text(cx + 17, cy, name, theme["ink2"], 12))
        body.append(text(cx + col_w - 14, cy, fr_pct(100 * n / total), theme["ink"], 12, 600, anchor="end"))
    return svg_doc(width, height, theme, "".join(body),
                   "Répartition des langages du dépôt en pourcentage d'octets")


def banner_svg(theme: dict) -> str:
    width, height = 840, 190
    body = [
        text(32, 78, "Bastien Lebrou", theme["ink"], 34, 700),
        text(32, 106, "Géomatique · Ingénierie de données géospatiales · Télédétection",
             theme["ink2"], 14),
    ]
    x = 32.0
    for chip in ("Python", "QGIS", "PostGIS", "DuckDB", "GeoParquet", "xarray", "Sentinel-2"):
        w = round(len(chip) * 6.6 + 22)
        body.append(f'<rect x="{x:g}" y="126" width="{w}" height="26" rx="13" '
                    f'fill="none" stroke="{theme["border"]}"/>\n')
        body.append(text(x + w / 2, 143, chip, theme["muted"], 12, anchor="middle"))
        x += w + 8
    # Motif décoratif : champ « NDVI » en points (rampe séquentielle, un seul ton)
    import math
    for i in range(9):
        for j in range(6):
            px, py = 610 + i * 24, 36 + j * 24
            v = 0.5 + 0.5 * math.sin(i * 0.8 + 1.1) * math.cos(j * 0.9 - 0.4)
            step = min(int(v * len(theme["seq"])), len(theme["seq"]) - 1)
            body.append(f'<circle cx="{px}" cy="{py}" r="3.6" fill="{theme["seq"][step]}" opacity="0.9"/>\n')
    pts = [(608, 172), (652, 166), (696, 168), (740, 156), (784, 150), (816, 142)]
    path = " ".join(f"{'M' if k == 0 else 'L'} {px} {py}" for k, (px, py) in enumerate(pts))
    body.append(f'<path d="{path}" fill="none" stroke="{theme["accent"]}" '
                f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>\n')
    ex, ey = pts[-1]
    body.append(f'<circle cx="{ex}" cy="{ey}" r="6.5" fill="{theme["surface"]}"/>\n')  # anneau de surface
    body.append(f'<circle cx="{ex}" cy="{ey}" r="4.5" fill="{theme["accent"]}"/>\n')
    return svg_doc(width, height, theme, "".join(body),
                   "Bannière du portfolio de Bastien Lebrou — géomatique et données géospatiales")


# ── Bloc README ─────────────────────────────────────────────────────────────

def paris_now() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Paris"))
    except Exception:
        return datetime.now(timezone.utc)


def stats_markdown(dates: list[date], langs: list[tuple[str, int]]) -> str:
    total_bytes = sum(n for _, n in langs) or 1
    lead_name, lead_bytes = langs[0] if langs else ("—", 0)
    now = paris_now()
    head = sh("git", "rev-parse", "--short", "HEAD").strip()
    rows = [
        ("📦 Commits", fr_num(len(dates))),
        ("📅 Jours actifs", fr_num(len(set(dates)))),
        ("🗂️ Projets", fr_num(project_count())),
        ("🐍 Lignes de Python", fr_num(python_lines())),
        ("✅ Tests automatisés", fr_num(test_count())),
        ("🥇 Langage principal", f"{lead_name} ({fr_pct(100 * lead_bytes / total_bytes)})"),
    ]
    tables = []
    for trio in (rows[:3], rows[3:]):
        tables.append(
            "| " + " | ".join(label for label, _ in trio) + " |\n"
            + "|" + ":---:|" * len(trio) + "\n"
            + "| " + " | ".join(f"**{value}**" for _, value in trio) + " |\n"
        )
    stamp = (f"*Dernière mise à jour automatique : {now.day} {MOIS[now.month - 1]} {now.year} "
             f"à {now:%H:%M} (heure de Paris) — commit `{head}`.*")
    return "\n" + "\n".join(tables) + "\n" + stamp + "\n"


def inject_readme(block: str) -> None:
    content = README.read_text(encoding="utf-8")
    pattern = re.compile(r"(<!-- AUTO-STATS:START -->).*?(<!-- AUTO-STATS:END -->)", re.S)
    if not pattern.search(content):
        raise SystemExit("Marqueurs AUTO-STATS introuvables dans README.md")
    README.write_text(pattern.sub(lambda m: m.group(1) + block + m.group(2), content),
                      encoding="utf-8")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    dates = commit_dates()
    langs = language_bytes()
    weeks = weekly_series(dates)
    for mode, theme in THEMES.items():
        (ASSETS / f"banner-{mode}.svg").write_text(banner_svg(theme), encoding="utf-8")
        (ASSETS / f"activity-{mode}.svg").write_text(activity_svg(weeks, theme), encoding="utf-8")
        (ASSETS / f"languages-{mode}.svg").write_text(languages_svg(langs, theme), encoding="utf-8")
        (ASSETS / f"weekdays-{mode}.svg").write_text(weekdays_svg(dates, theme), encoding="utf-8")
    inject_readme(stats_markdown(dates, langs))
    print(f"OK — {len(dates)} commits analysés, {len(langs)} langages, 8 SVG régénérés.")


if __name__ == "__main__":
    main()
