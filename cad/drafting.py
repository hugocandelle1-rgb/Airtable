"""Moteur de mise en plan 2D (matplotlib) : vues orthographiques issues de la CAO (lignes cachées supprimées
par cadquery/OCC), cotation linéaire / diamètre, repères de référence, cadres de tolérancement (GD&T),
cartouche ISO 7200 simplifié.  Sortie : SVG et PDF vectoriels (1 mm de feuille = 1 unité).

Usage :
    s = Sheet("A3", titre=..., ref=..., matiere=..., masse_kg=..., echelle="2:1", tol_gen="ISO 2768-mK")
    v = s.view(shape, "dessus", centre=(100, 200), scale=2.0)
    v.dim_x((x0, y0), (x1, y0), off=-8)           # cotes dans le repère de la vue (mm pièce)
    s.save("cad/export/plans/ma_piece")
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Circle, Polygon  # noqa: E402

import cadquery as cq  # noqa: E402
from cadquery.occ_impl.exporters.svg import getSVG  # noqa: E402

from cad.common import _oriented  # noqa: E402

plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["font.family"] = "DejaVu Sans"
MM = 72.0 / 25.4                       # points par mm
FORMATS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594)}


def fmt(v: float, nd: int = 2) -> str:
    """Nombre au format français, zéros inutiles supprimés."""
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return (s if s not in ("-0", "") else "0").replace(".", ",")


def projected_segments(shape: cq.Workplane, kind: str, hidden: bool = False):
    """Segments (x1,y1,x2,y2) en mm pièce dans le repère de la vue (x à droite, y en haut)."""
    svg = getSVG(_oriented(shape, kind).val(), {"projectionDir": (0, 0, 1), "showHidden": hidden,
                                                "width": 1000, "height": 1000})
    head, _, solid = svg.partition("<!-- solid lines -->")

    def segs(txt):
        out = []
        for d in re.findall(r'<path d="([^"]+)"', txt):
            pts = [tuple(map(float, p.split(","))) for p in re.findall(r"[-\d.eE+]+,[-\d.eE+]+", d)]
            out += [(a[0], a[1], b[0], b[1]) for a, b in zip(pts[:-1], pts[1:])]
        return out
    return segs(solid), (segs(head) if hidden else [])


class View:
    def __init__(self, sheet: "Sheet", segs, hid, centre, scale, anchor):
        self.s, self.sc, self.c, self.a = sheet, scale, centre, anchor
        self.segs, self.hid = segs, hid

    def P(self, x: float, y: float) -> tuple[float, float]:
        """Point de la vue (mm pièce) -> coordonnées feuille."""
        return (self.c[0] + (x - self.a[0]) * self.sc, self.c[1] + (y - self.a[1]) * self.sc)

    def draw(self):
        ax = self.s.ax
        mp = lambda g: [(self.P(x1, y1), self.P(x2, y2)) for x1, y1, x2, y2 in g]
        if self.hid:
            ax.add_collection(LineCollection(mp(self.hid), colors="0.35", linewidths=0.18 * MM,
                                             linestyles=(0, (3, 1.5))))
        ax.add_collection(LineCollection(mp(self.segs), colors="k", linewidths=0.35 * MM))

    # --- cotation dans le repère de la vue ---------------------------------------------------------
    def dim(self, a, b, off, text=None, nd=2, suffix="", prefix="", side=None):
        self.s.dim_lin(self.P(*a), self.P(*b), off, text if text is not None else
                       prefix + fmt(math.hypot(b[0] - a[0], b[1] - a[1]), nd) + suffix)

    def dim_x(self, a, b, off, text=None, nd=2, prefix="", suffix=""):
        """Cote horizontale entre les abscisses de a et b ; ligne de cote à `off` mm feuille (off>0 : au-dessus de a)."""
        a, b = sorted((a, b), key=lambda t: t[0])
        y = a[1]
        self.s.dim_lin(self.P(a[0], y), self.P(b[0], y), off,
                       text if text is not None else prefix + fmt(abs(b[0] - a[0]), nd) + suffix,
                       ext_from=(self.P(*a), self.P(*b)))

    def dim_y(self, a, b, off, text=None, nd=2, prefix="", suffix=""):
        """Cote verticale entre les ordonnées de a et b ; off>0 : ligne de cote à gauche de a."""
        a, b = sorted((a, b), key=lambda t: t[1])
        x = a[0]
        self.s.dim_lin(self.P(x, a[1]), self.P(x, b[1]), off,
                       text if text is not None else prefix + fmt(abs(b[1] - a[1]), nd) + suffix,
                       ext_from=(self.P(*a), self.P(*b)))

    def dia(self, centre, r, ang, text, length=14.0):
        """Repère de diamètre : flèche sur le cercle (rayon r mm pièce) à l'angle `ang` + texte."""
        c = self.P(*centre)
        self.s.leader_circle(c, r * self.sc, ang, text, length)

    def note(self, p, text, dx=12.0, dy=8.0):
        self.s.leader(self.P(*p), text, dx, dy)

    def centerlines(self, centre, r, ext=3.0):
        c = self.P(*centre)
        rr = r * self.sc + ext
        self.s.cline((c[0] - rr, c[1]), (c[0] + rr, c[1]))
        self.s.cline((c[0], c[1] - rr), (c[0], c[1] + rr))

    def circle(self, centre, r, lw=0.35, ls="-"):
        c = self.P(*centre)
        self.s.ax.add_patch(Circle(c, r * self.sc, fill=False, ec="k", lw=lw * MM, ls=ls))

    def line(self, a, b, lw=0.35, ls="-", color="k"):
        p, q = self.P(*a), self.P(*b)
        self.s.ax.plot([p[0], q[0]], [p[1], q[1]], color=color, lw=lw * MM, ls=ls, solid_capstyle="butt")


class Sheet:
    def __init__(self, fmt_name: str, titre: str, ref: str, matiere: str, masse_kg: float | None,
                 echelle: str, tol_gen: str = "ISO 2768-mK", sous_titre: str = "", rugosite: str = "Ra 3,2 sauf indication",
                 auteur: str = "CAO (CadQuery) - à valider", indice: str = "A", date: str = ""):
        self.W, self.H = FORMATS[fmt_name]
        self.fig = plt.figure(figsize=(self.W / 25.4, self.H / 25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, self.W)
        self.ax.set_ylim(0, self.H)
        self.ax.set_aspect("equal")
        self.ax.axis("off")
        self.views: list[View] = []
        self.ax.add_patch(plt.Rectangle((0.5, 0.5), self.W - 1, self.H - 1, fill=False, ec="0.5", lw=0.2 * MM))
        self.ax.add_patch(plt.Rectangle((20, 10), self.W - 30, self.H - 20, fill=False, ec="k", lw=0.7 * MM))
        self._cartouche(titre, sous_titre, ref, matiere, masse_kg, echelle, tol_gen, rugosite, auteur, indice, date)

    # --- primitives ----------------------------------------------------------------------------------------
    def text(self, p, s, size=3.5, ha="left", va="center", rot=0.0, weight="normal", color="k"):
        self.ax.text(p[0], p[1], s, fontsize=size * MM, ha=ha, va=va, rotation=rot, weight=weight, color=color,
                     rotation_mode="anchor")

    def line(self, p, q, lw=0.25, ls="-", color="k"):
        self.ax.plot([p[0], q[0]], [p[1], q[1]], color=color, lw=lw * MM, ls=ls, solid_capstyle="butt")

    def cline(self, p, q):
        self.ax.plot([p[0], q[0]], [p[1], q[1]], color="k", lw=0.18 * MM, ls=(0, (8, 1.5, 1.5, 1.5)))

    def arrow(self, tip, frm):
        self.ax.annotate("", xy=tip, xytext=frm, arrowprops=dict(arrowstyle="-|>,head_length=0.35,head_width=0.12", lw=0.25 * MM,
                                                               color="k", shrinkA=0, shrinkB=0))

    def dim_lin(self, p, q, off, text, ext_from=None, size=3.0):
        """Cote linéaire entre p et q (feuille) ; ligne de cote décalée de `off` mm (normale à gauche de p->q si off>0)."""
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        a = (p[0] + nx * off, p[1] + ny * off)
        b = (q[0] + nx * off, q[1] + ny * off)
        srcs = ext_from if ext_from else (p, q)
        sg = 1.0 if off >= 0 else -1.0
        for src, end in ((srcs[0], a), (srcs[1], b)):
            # ligne d'attache : de la pièce (écart 1 mm) jusqu'à 2 mm au-delà de la ligne de cote
            vx, vy = end[0] - src[0], end[1] - src[1]
            n = math.hypot(vx, vy)
            if n < 1e-9:
                continue
            self.line((src[0] + vx / n * 1.0, src[1] + vy / n * 1.0), (end[0] + vx / n * 2.0, end[1] + vy / n * 2.0), lw=0.18)
        self.line(a, b, lw=0.25)
        if L > 6:
            self.arrow(a, b)
            self.arrow(b, a)
        else:                                     # cote courte : flèches à l'extérieur
            self.arrow(a, (a[0] - ux * 5, a[1] - uy * 5))
            self.arrow(b, (b[0] + ux * 5, b[1] + uy * 5))
        ang = math.degrees(math.atan2(uy, ux))
        if ang > 90 or ang < -90:
            ang += 180
        mid = ((a[0] + b[0]) / 2 + nx * sg * 1.6 * (1 if ang == math.degrees(math.atan2(uy, ux)) else 1),
               (a[1] + b[1]) / 2 + ny * sg * 1.6)
        # texte au-dessus de la ligne de cote (côté extérieur à la pièce)
        self.text(mid, text, size=size, ha="center", va="center", rot=ang)

    def leader(self, p, text, dx, dy, size=3.0):
        q = (p[0] + dx, p[1] + dy)
        self.line(p, q, lw=0.2)
        self.arrow(p, q)
        self.line(q, (q[0] + (6 if dx >= 0 else -6), q[1]), lw=0.2)
        self.text((q[0] + (7 if dx >= 0 else -7), q[1]), text, size=size, ha="left" if dx >= 0 else "right")

    def leader_circle(self, c, r, ang, text, length=14.0, size=3.0):
        a = math.radians(ang)
        p = (c[0] + r * math.cos(a), c[1] + r * math.sin(a))
        q = (c[0] + (r + length) * math.cos(a), c[1] + (r + length) * math.sin(a))
        self.line(p, q, lw=0.2)
        self.arrow(p, q)
        right = math.cos(a) >= 0
        self.line(q, (q[0] + (6 if right else -6), q[1]), lw=0.2)
        self.text((q[0] + (7 if right else -7), q[1]), text, size=size, ha="left" if right else "right")

    def gdt(self, p, cells, h=6.0, size=2.8, ha="left"):
        """Cadre de tolérancement. cells = liste de str ou ('flat'|'pos'|'sym', None) pour les symboles ;
        p = coin inférieur gauche. Retourne le coin supérieur droit."""
        x = p[0]
        for c in cells:
            w = h if isinstance(c, tuple) else max(h, 1.9 * len(c) * size / 3.0 + 3.0)
            self.ax.add_patch(plt.Rectangle((x, p[1]), w, h, fill=False, ec="k", lw=0.3 * MM))
            cx, cy = x + w / 2, p[1] + h / 2
            if isinstance(c, tuple):
                kind = c[0]
                if kind == "flat":
                    self.ax.add_patch(Polygon([(cx - 2.4, cy - 1.2), (cx + 1.2, cy - 1.2), (cx + 2.4, cy + 1.2), (cx - 1.2, cy + 1.2)],
                                              fill=False, ec="k", lw=0.3 * MM))
                elif kind == "pos":
                    self.ax.add_patch(Circle((cx, cy), 1.8, fill=False, ec="k", lw=0.3 * MM))
                    self.line((cx - 2.8, cy), (cx + 2.8, cy), lw=0.3)
                    self.line((cx, cy - 2.8), (cx, cy + 2.8), lw=0.3)
                elif kind == "parallel":
                    self.line((cx - 2, cy - 1.5), (cx + 1, cy + 1.5), lw=0.3)
                    self.line((cx - 1, cy - 1.5), (cx + 2, cy + 1.5), lw=0.3)
            else:
                self.text((cx, cy), c, size=size, ha="center")
            x += w
        return (x, p[1] + h)

    def datum(self, p, label, direction=(0, -1), size=3.5):
        """Repère de référence : triangle plein sur l'arête en p, tige et cadre portant la lettre."""
        dx, dy = direction
        tip = p
        base = (p[0] + dx * 3.5, p[1] + dy * 3.5)
        px, py = -dy, dx
        self.ax.add_patch(Polygon([tip, (base[0] + px * 1.6, base[1] + py * 1.6), (base[0] - px * 1.6, base[1] - py * 1.6)],
                                  closed=True, fc="k", ec="k", lw=0.2 * MM))
        end = (p[0] + dx * 9, p[1] + dy * 9)
        self.line(base, end, lw=0.25)
        c = (end[0] + dx * 3.0, end[1] + dy * 3.0)
        self.ax.add_patch(plt.Rectangle((c[0] - 3, c[1] - 3), 6, 6, fill=False, ec="k", lw=0.3 * MM))
        self.text(c, label, size=size, ha="center", weight="bold")

    def block(self, p, lines, size=2.8, title=None, width=None, lead=4.2):
        """Bloc de notes (coin supérieur gauche p)."""
        y = p[1]
        if title:
            self.text((p[0], y), title, size=size + 0.4, weight="bold")
            y -= lead
        for ln in lines:
            self.text((p[0], y), ln, size=size)
            y -= lead
        return y

    # --- vues ---------------------------------------------------------------------------------------------------
    def view(self, shape: cq.Workplane, kind: str, centre, scale: float, hidden: bool = False, anchor=None) -> View:
        segs, hid = projected_segments(shape, kind, hidden)
        if anchor is None:
            xs = [v for s in segs for v in (s[0], s[2])]
            ys = [v for s in segs for v in (s[1], s[3])]
            anchor = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        v = View(self, segs, hid, centre, scale, anchor)
        v.draw()
        self.views.append(v)
        return v

    def label(self, p, text, size=4.0):
        self.text(p, text, size=size, weight="bold", ha="center")

    # --- cartouche --------------------------------------------------------------------------------------------------------
    def _cartouche(self, titre, sous, ref, matiere, masse, echelle, tol_gen, rugo, auteur, indice, date):
        x1, y0 = self.W - 10, 10
        w, h = 180.0, 46.0
        x0 = x1 - w
        ax = self.ax
        ax.add_patch(plt.Rectangle((x0, y0), w, h, fill=False, ec="k", lw=0.5 * MM))
        rows = [10, 20, 28, 37]                                   # séparateurs horizontaux (depuis le bas)
        for r in rows:
            self.line((x0, y0 + r), (x1, y0 + r), lw=0.25)
        self.line((x0 + 90, y0), (x0 + 90, y0 + 37), lw=0.25)
        self.line((x0 + 135, y0), (x0 + 135, y0 + 28), lw=0.25)
        self.text((x0 + 3, y0 + 41.5), titre, size=4.6, weight="bold")
        if sous:
            self.text((x0 + 3, y0 + 33), sous, size=2.8)
        self.text((x0 + 3, y0 + 24), f"Matière : {matiere}", size=2.6)
        self.text((x0 + 93, y0 + 24), f"Masse : {fmt(masse, 3) + ' kg' if masse is not None else '-'}", size=2.6)
        self.text((x0 + 3, y0 + 15), f"Tolérances générales : {tol_gen}", size=2.6)
        self.text((x0 + 93, y0 + 15), f"Échelle : {echelle}", size=2.6)
        self.text((x0 + 138, y0 + 15), "Unités : mm", size=2.6)
        self.text((x0 + 3, y0 + 5), f"Réf. {ref}   Ind. {indice}", size=2.6)
        self.text((x0 + 93, y0 + 5), rugo, size=2.4)
        self.text((x0 + 138, y0 + 5), auteur, size=2.0)
        # symbole de projection (méthode européenne, vue de face + de gauche simplifiée)
        px, py = x0 + 150, y0 + 20.5
        self.text((px, py + 13.5), "Méthode E", size=2.0)
        self.ax.add_patch(Polygon([(px + 2, py + 3), (px + 8, py + 6), (px + 8, py + 10), (px + 2, py + 9)], fill=False, ec="k", lw=0.2 * MM))
        self.ax.add_patch(Circle((px + 20, py + 6.5), 3.5, fill=False, ec="k", lw=0.2 * MM))

    def save(self, base: Path | str, png: bool = False) -> list[str]:
        base = Path(base)
        base.parent.mkdir(parents=True, exist_ok=True)
        out = []
        for ext in ("svg", "pdf") + (("png",) if png else ()):
            p = base.with_suffix("." + ext)
            self.fig.savefig(p, format=ext, **({"dpi": 70} if ext == "png" else {}))
            out.append(p.name)
        plt.close(self.fig)
        return out
