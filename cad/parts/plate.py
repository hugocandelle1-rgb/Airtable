"""Plaque de travail perforée + inserts d'appui (Kelvin) + exports FAO (CSV, DXF).

Repère : origine au centre de la face supérieure, Z vers le haut (dessous = -épaisseur).
Chaque trou = perçage borgne Ø counterbore_d depuis le dessous (profondeur ép - voile)
+ orifice calibré Ø orifice_d dans le voile de orifice_length.
"""
from __future__ import annotations

import csv
import math
import time
from pathlib import Path

import cadquery as cq

from cad.common import COLORS, PartSpec, support_points


# -----------------------------------------------------------------------------
#  Réseau de trous
# -----------------------------------------------------------------------------
def _raw_lattice(P: dict) -> list[tuple[float, float]]:
    """Réseau (hex ou carré) centré sur l'origine, symétrique en x et y, dans la zone percée."""
    pl = P["plate"]
    p = pl["pitch_mm"]
    half = P["zones"]["perforated_square_mm"] / 2.0 - pl["edge_band_mm"]
    pts: list[tuple[float, float]] = []
    if pl["pattern"] == "hex":
        dy = p * math.sqrt(3.0) / 2.0
        nj = int(half // dy)
        for j in range(-nj, nj + 1):
            y = j * dy
            off = 0.0 if j % 2 == 0 else p / 2.0     # lignes impaires décalées d'un demi-pas
            ni = int((half + p) // p) + 1
            for i in range(-ni, ni + 1):
                x = i * p + off
                if abs(x) <= half + 1e-9 and abs(y) <= half + 1e-9:
                    pts.append((x, y))
    else:  # carré
        n = int(half // p)
        pts = [(i * p, j * p) for i in range(-n, n + 1) for j in range(-n, n + 1)]
    return pts


def hole_centers(P: dict) -> list[tuple[float, float]]:
    """Centres (x, y) en mm des trous : réseau dans la zone percée, bande de bord exclue,
    trous supprimés autour des logements d'appui (rayon logement + marge)."""
    pl = P["plate"]
    r_ex = pl["pocket_d_mm"] / 2.0 + pl["hole_exclusion_margin_mm"] + pl["counterbore_d_mm"] / 2.0
    sup = support_points(P)
    out = []
    for (x, y) in _raw_lattice(P):
        if any(math.hypot(x - s["x"], y - s["y"]) < r_ex for s in sup):
            continue
        out.append((x, y))
    return out


def witness_centers(P: dict) -> list[tuple[float, float]]:
    """Trous témoins du modèle léger : amas central de witness_holes trous."""
    pts = sorted(hole_centers(P), key=lambda c: (round(math.hypot(*c), 6), c))
    return pts[: P["plate"]["witness_holes"]]


def tap_positions(P: dict) -> list[tuple[float, float]]:
    """Trous taraudés de la bride du joint : carré de demi-côté tap_half, tap_per_side par côté."""
    pl = P["plate"]
    h, n = pl["tap_half_mm"], pl["tap_per_side"]
    step = 2 * h / (n - 1)
    pts = []
    for i in range(n):
        u = -h + i * step
        pts += [(u, -h), (u, h)]
        if 0 < i < n - 1:
            pts += [(-h, u), (h, u)]
    return pts


# -----------------------------------------------------------------------------
#  Modèle de la plaque
# -----------------------------------------------------------------------------
def _comb(pts, z0: float, d: float, depth: float) -> cq.Workplane:
    """Peigne de cylindres (un seul solide composé) : z de z0 à z0+depth."""
    return (cq.Workplane("XY").workplane(offset=z0).pushPoints(pts).circle(d / 2.0).extrude(depth))


def plate_blank(P: dict) -> cq.Workplane:
    """Plaque avec logements d'appui, taraudages et pions, SANS les trous du réseau."""
    pl = P["plate"]
    t = pl["thickness_mm"]
    L = pl["outer_square_mm"]
    w = cq.Workplane("XY").workplane(offset=-t).rect(L, L).extrude(t)      # z de -t à 0
    # logements d'inserts (dessous)
    sup = [(s["x"], s["y"]) for s in support_points(P)]
    w = w.cut(_comb(sup, -t, pl["pocket_d_mm"], pl["pocket_depth_mm"]))
    # taraudages (avant-trous) de la bride joint
    w = w.cut(_comb(tap_positions(P), -t, pl["tap_d_mm"], pl["tap_depth_mm"]))
    # pions de référence (borgnes, dessous)
    w = w.cut(_comb([tuple(p) for p in pl["pin_positions_mm"]], -t, pl["pin_d_mm"], pl["pin_depth_mm"]))
    return w


def build_plate(P: dict, mode: str = "light") -> cq.Workplane:
    """mode = 'light' (trous témoins) ou 'full' (tous les trous : un booléen composé par diamètre)."""
    pl = P["plate"]
    t = pl["thickness_mm"]
    voile = pl["orifice_length_mm"]
    w = plate_blank(P)
    pts = hole_centers(P) if mode == "full" else witness_centers(P)
    bore = _comb(pts, -t, pl["counterbore_d_mm"], t - voile)             # borgne depuis le dessous
    orif = _comb(pts, -voile, pl["orifice_d_mm"], voile)                  # orifice calibré dans le voile
    w = w.cut(bore).cut(orif)
    return w


def plate_hole_volume_mm3(P: dict) -> dict:
    """Volumes analytiques retirés par le réseau complet (pour la masse équivalente du modèle léger)."""
    pl = P["plate"]
    n = len(hole_centers(P))
    v_bore = math.pi * (pl["counterbore_d_mm"] / 2) ** 2 * (pl["thickness_mm"] - pl["orifice_length_mm"])
    v_or = math.pi * (pl["orifice_d_mm"] / 2) ** 2 * pl["orifice_length_mm"]
    return {"n_holes": n, "v_per_hole_mm3": v_bore + v_or, "v_total_mm3": n * (v_bore + v_or)}


# -----------------------------------------------------------------------------
#  Inserts d'appui (pastille + bille) — couplage de Kelvin cône / vé / plat
# -----------------------------------------------------------------------------
def insert_geometry(P: dict) -> list[dict]:
    """Pour chaque appui : pastille (cône, vé ou plat), centre de bille, haut de colonne."""
    pl = P["plate"]
    t = pl["thickness_mm"]
    R = pl["ball_d_mm"] / 2.0
    a = math.radians(pl["insert_half_angle_deg"])
    z_apex = -t + pl["insert_recess_depth_mm"]
    sup = support_points(P)
    cone = next((s for s in sup if s["type"] == "cone"), sup[0])
    out = []
    for s in sup:
        g = dict(s)
        if s["type"] in ("cone", "ve"):
            g["ball_zc"] = z_apex - R / math.sin(a)
        else:
            g["ball_zc"] = -t - R
        g["column_top"] = g["ball_zc"] - R
        # axe du vé : dirigé vers le cône
        ux, uy = cone["x"] - s["x"], cone["y"] - s["y"]
        n = math.hypot(ux, uy)
        g["axis_angle"] = math.degrees(math.atan2(uy, ux)) if n > 1e-9 else 0.0
        out.append(g)
    return out


def build_inserts(P: dict) -> list[PartSpec]:
    pl = P["plate"]
    t = pl["thickness_mm"]
    parts = []
    for g in insert_geometry(P):
        x, y, typ = g["x"], g["y"], g["type"]
        pad = cq.Workplane("XY").workplane(offset=-t).circle(pl["insert_d_mm"] / 2.0).extrude(pl["insert_t_mm"])
        z_apex = -t + pl["insert_recess_depth_mm"]
        al = math.radians(pl["insert_half_angle_deg"])
        if typ == "cone":
            h = z_apex - (-t - 1.0)
            cone = (cq.Workplane("XY").workplane(offset=-t - 1.0).circle(h * math.tan(al))
                    .workplane(offset=h).circle(0.01).loft(combine=True))
            pad = pad.cut(cone)
        elif typ == "ve":
            h = z_apex - (-t - 1.0)
            a_ = h * math.tan(al)
            L = pl["insert_d_mm"] + 2.0
            prism = (cq.Workplane("XZ").polyline([(-a_, -t - 1.0), (a_, -t - 1.0), (0, z_apex)]).close()
                     .extrude(L / 2.0, both=True))
            prism = prism.rotate((0, 0, 0), (0, 0, 1), g["axis_angle"] - 90.0)
            pad = pad.cut(prism)
        pad = pad.translate((x, y, 0))
        parts.append(PartSpec(f"insert_{typ}_{g['index'] + 1}", pad, COLORS["acier"], "acier", "plaque",
                              formats=("step",), commercial=False,
                              note=f"pastille d'appui {typ} (acier trempé), collée dans le logement"))
        ball = cq.Workplane("XY").sphere(pl["ball_d_mm"] / 2.0).translate((x, y, g["ball_zc"]))
        parts.append(PartSpec(f"bille_{g['index'] + 1}", ball, COLORS["acier"], "acier", "plaque",
                              commercial=True, note="bille acier/céramique de couplage de Kelvin"))
    return parts


def build(P: dict, mode: str = "light") -> list[PartSpec]:
    """Plaque + inserts + billes (coordonnées globales)."""
    plate = build_plate(P, mode)
    parts = [PartSpec("plaque", plate, COLORS["plaque"], "alu_5083", "plaque", formats=("step", "stl"),
                      note=f"modèle {mode}")]
    parts += build_inserts(P)
    return parts


# -----------------------------------------------------------------------------
#  Exports FAO : CSV et DXF 2D
# -----------------------------------------------------------------------------
def export_csv(P: dict, path: Path) -> int:
    pts = hole_centers(P)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "x_mm", "y_mm"])
        for i, (x, y) in enumerate(pts, 1):
            w.writerow([i, f"{x:.4f}", f"{y:.4f}"])
    return len(pts)


def export_dxf(P: dict, path: Path) -> dict:
    """DXF 2D vu de dessous (repère plaque) avec calques : contour, zone percée, trous borgnes
    Ø2, orifices Ø0,4, appuis (logements + axes), taraudages, pions, axes."""
    import ezdxf

    pl = P["plate"]
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for name, color in (("CONTOUR", 7), ("ZONE_PERCEE", 3), ("TROUS_BORGNES", 5), ("ORIFICES", 1),
                        ("APPUIS", 2), ("TARAUDAGES", 6), ("PIONS", 4), ("AXES", 8)):
        doc.layers.add(name, color=color)
    L = pl["outer_square_mm"]
    Z = P["zones"]["perforated_square_mm"]

    def square(c, layer):
        h = c / 2.0
        msp.add_lwpolyline([(-h, -h), (h, -h), (h, h), (-h, h)], close=True, dxfattribs={"layer": layer})

    square(L, "CONTOUR")
    square(Z, "ZONE_PERCEE")
    pts = hole_centers(P)
    for (x, y) in pts:
        msp.add_circle((x, y), pl["counterbore_d_mm"] / 2.0, dxfattribs={"layer": "TROUS_BORGNES"})
        msp.add_circle((x, y), pl["orifice_d_mm"] / 2.0, dxfattribs={"layer": "ORIFICES"})
    for s in support_points(P):
        msp.add_circle((s["x"], s["y"]), pl["pocket_d_mm"] / 2.0, dxfattribs={"layer": "APPUIS"})
        msp.add_text(f"{s['index'] + 1}-{s['type']}", height=4,
                     dxfattribs={"layer": "APPUIS", "insert": (s["x"] + 10, s["y"] + 10)})
    for (x, y) in tap_positions(P):
        msp.add_circle((x, y), pl["tap_d_mm"] / 2.0, dxfattribs={"layer": "TARAUDAGES"})
    for (x, y) in pl["pin_positions_mm"]:
        msp.add_circle((x, y), pl["pin_d_mm"] / 2.0, dxfattribs={"layer": "PIONS"})
    msp.add_line((-L / 2 - 10, 0), (L / 2 + 10, 0), dxfattribs={"layer": "AXES"})
    msp.add_line((0, -L / 2 - 10), (0, L / 2 + 10), dxfattribs={"layer": "AXES"})
    doc.saveas(str(path))
    return {"n_holes": len(pts), "n_circles": 2 * len(pts) + len(support_points(P)) + len(tap_positions(P))
            + len(pl["pin_positions_mm"])}


if __name__ == "__main__":
    from cad.common import get_params
    P = get_params()
    t0 = time.time()
    pts = hole_centers(P)
    print(len(pts), "trous", f"{time.time() - t0:.2f}s")
    w = build_plate(P)
    print(w.val().isValid(), w.val().Volume(), f"{time.time() - t0:.2f}s")
