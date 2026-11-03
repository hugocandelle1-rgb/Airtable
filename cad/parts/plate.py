"""Plaque de travail perforée 520 x 520 x 35 + billes de Kelvin ; exports FAO (CSV, DXF).

Cotes : [03] §8, [04] §7, [02] §13 (voir DEFAULTS dans cad/common.py).
Repère : origine au centre de la face supérieure, Z vers le haut (dessous = -épaisseur).
Chaque trou = lamage borgne Ø2 depuis le dessous (fond conique 118 deg, sommet à e - voile)
+ orifice calibré Ø0,30 dans le voile de 1,2 mm, débouchant en face supérieure.
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
    """Réseau hex (rangées selon x) ou carré, centré sur l'origine, dans la zone percée."""
    pl = P["plate"]
    p = pl["pitch_mm"]
    half = P["zones"]["perforated_square_mm"] / 2.0 - pl["edge_band_mm"]
    pts: list[tuple[float, float]] = []
    if pl["pattern"] == "hex":
        dy = p * math.sqrt(3.0) / 2.0
        nj = int(half // dy)
        for j in range(-nj, nj + 1):
            y = j * dy
            off = 0.0 if j % 2 == 0 else p / 2.0
            ni = int((half + p) // p) + 1
            for i in range(-ni, ni + 1):
                x = i * p + off
                if abs(x) <= half + 1e-9 and abs(y) <= half + 1e-9:
                    pts.append((x, y))
    else:
        n = int(half // p)
        pts = [(i * p, j * p) for i in range(-n, n + 1) for j in range(-n, n + 1)]
    return pts


def hole_centers(P: dict) -> list[tuple[float, float]]:
    """Centres (x, y) en mm : réseau dans la zone percée (bande de bord exclue). Les appuis
    et embases étant hors zone, aucun trou n'est supprimé ; le test d'exclusion reste actif
    si les points d'appui changent."""
    pl = P["plate"]
    r_ex = pl["ball_pocket_d_mm"] / 2.0 + pl["counterbore_d_mm"] / 2.0 + 2.0
    sup = support_points(P)
    return [(x, y) for (x, y) in _raw_lattice(P)
            if not any(math.hypot(x - s["x"], y - s["y"]) < r_ex for s in sup)]


def witness_centers(P: dict) -> list[tuple[float, float]]:
    """Trous témoins du modèle léger : amas central de witness_holes trous."""
    pts = sorted(hole_centers(P), key=lambda c: (round(math.hypot(*c), 6), c))
    return pts[: P["plate"]["witness_holes"]]


def tap_positions(P: dict) -> list[tuple[float, float]]:
    """32 x M5 de l'attache du caisson : carré de demi-côté tap_half, tap_per_side par côté, symétriques."""
    pl = P["plate"]
    h, n = pl["tap_half_mm"], pl["tap_per_side"]
    step = 2 * h / n
    us = [-h + step / 2 + i * step for i in range(n)]
    pts = []
    for u in us:
        pts += [(u, -h), (u, h), (-h, u), (h, u)]
    return pts


def adxl_positions(P: dict) -> list[tuple[float, float]]:
    """3 x M4 sur Ø40 à 120 deg par embase, un trou dirigé vers l'extérieur."""
    pl = P["plate"]
    r = pl["adxl_pcd_mm"] / 2.0
    pts = []
    for cx, cy in P["tilt_sensors"]["positions_mm"]:
        a0 = math.atan2(cy, cx)
        for k in range(3):
            a = a0 + k * 2 * math.pi / 3
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# -----------------------------------------------------------------------------
#  Modèle de la plaque
# -----------------------------------------------------------------------------
def hole_tool(P: dict) -> cq.Shape:
    """Outil d'un trou (révolution) centré sur Z : lamage Ø2, fond conique 118 deg dont le sommet
    est à z = -voile, orifice Ø0,30 jusqu'à 0,5 mm au-dessus de la face supérieure."""
    pl = P["plate"]
    t, v = pl["thickness_mm"], pl["orifice_length_mm"]
    r1, r2 = pl["counterbore_d_mm"] / 2.0, pl["orifice_d_mm"] / 2.0
    k = 1.0 / math.tan(math.radians(pl["cone_angle_deg"] / 2.0))      # hauteur du cône par unité de rayon
    z_apex = -v                                                        # sommet théorique du cône
    prof = [(0.0, -t), (r1, -t), (r1, z_apex - r1 * k), (r2, z_apex - r2 * k), (r2, 0.5), (0.0, 0.5)]
    return cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0)).val()


def hole_tool_inside_volume(P: dict) -> float:
    """Volume retiré par un trou dans la plaque (outil moins la part au-dessus de z=0)."""
    r2 = P["plate"]["orifice_d_mm"] / 2.0
    return hole_tool(P).Volume() - math.pi * r2 ** 2 * 0.5


def _cyl(x, y, z0, d, h, direction=(0, 0, 1)) -> cq.Shape:
    return cq.Solid.makeCylinder(d / 2.0, h, cq.Vector(x, y, z0), cq.Vector(*direction))


def plate_blank(P: dict) -> cq.Workplane:
    """Plaque chanfreinée avec sièges de billes, datums, taraudages, embases, manutention ;
    SANS les trous du réseau."""
    pl = P["plate"]
    t, L = pl["thickness_mm"], pl["outer_square_mm"]
    w = cq.Workplane("XY").workplane(offset=-t).rect(L, L).extrude(t)
    w = w.faces(">Z or <Z").edges().chamfer(pl["chamfer_mm"])
    tools = []
    for s in support_points(P):                                         # sièges Ø25,4 H8 x 10,7
        tools.append(_cyl(s["x"], s["y"], -t, pl["ball_pocket_d_mm"], pl["ball_pocket_depth_mm"]))
    for x, y in tap_positions(P):                                       # 32 x M5
        tools.append(_cyl(x, y, -t, pl["tap_d_mm"], pl["tap_depth_mm"]))
    for x, y in adxl_positions(P):                                      # 12 x M4 (face supérieure)
        tools.append(_cyl(x, y, -pl["adxl_depth_mm"], pl["adxl_hole_d_mm"], pl["adxl_depth_mm"] + 1.0))
    bx, by = pl["datum_B_mm"]
    tools.append(_cyl(bx, by, -t - 1.0, pl["datum_d_mm"], t + 2.0))     # datum B : alésage Ø6 H7
    for x, y in pl["handling_positions_mm"]:                            # 4 x M10 sur les chants
        n = (math.copysign(1.0, x), 0.0, 0.0) if abs(x) > abs(y) else (0.0, math.copysign(1.0, y), 0.0)
        px = math.copysign(L / 2 + 1.0, x) if abs(x) > abs(y) else x
        py = math.copysign(L / 2 + 1.0, y) if abs(y) >= abs(x) else y
        tools.append(_cyl(px, py, -t / 2.0, pl["handling_d_mm"], pl["handling_depth_mm"] + 1.0,
                          (-n[0], -n[1], 0.0)))
    w = w.cut(cq.Workplane("XY").newObject([cq.Compound.makeCompound(tools)]))
    cx, cy = pl["datum_C_mm"]                                           # datum C : lumière 6 x 10 selon x
    slot = (cq.Workplane("XY").workplane(offset=-t - 1.0).center(cx, cy)
            .slot2D(pl["datum_C_len_mm"], pl["datum_d_mm"], 0).extrude(t + 2.0))
    return w.cut(slot)


def hole_comb(P: dict, pts) -> cq.Compound:
    tool = hole_tool(P)
    return cq.Compound.makeCompound([tool.moved(cq.Location(cq.Vector(x, y, 0.0))) for x, y in pts])


def build_plate(P: dict, mode: str = "light") -> cq.Workplane:
    """mode = 'light' (trous témoins) ou 'full' (tous les trous : un seul booléen composé d'outils étagés
    avec l'opérateur OBB de cadquery.occ_impl.shapes.cut)."""
    from cadquery.occ_impl import shapes as S

    blank = plate_blank(P)
    pts = hole_centers(P) if mode == "full" else witness_centers(P)
    res = S.cut(blank.val(), hole_comb(P, pts))
    return cq.Workplane("XY").newObject([res])


def plate_hole_volume_mm3(P: dict) -> dict:
    n = len(hole_centers(P))
    v = hole_tool_inside_volume(P)
    return {"n_holes": n, "v_per_hole_mm3": v, "v_total_mm3": n * v}


# -----------------------------------------------------------------------------
#  Billes de Kelvin (collées dans les sièges)
# -----------------------------------------------------------------------------
def build_balls(P: dict) -> list[PartSpec]:
    from cad.common import levels
    L = levels(P)
    parts = []
    for s in support_points(P):
        ball = cq.Workplane("XY").sphere(P["support"]["ball_d_mm"] / 2.0).translate((s["x"], s["y"], L["ball_zc"]))
        parts.append(PartSpec(f"bille_{s['index']}", ball, COLORS["acier"], "acier", "plaque", commercial=True,
                              note="bille Ø25,4 G10 (100Cr6), collée époxy dans le siège Ø25,4 H8"))
    return parts


def build(P: dict, mode: str = "light") -> list[PartSpec]:
    parts = [PartSpec("plaque", build_plate(P, mode), COLORS["plaque"], "alu_5083", "plaque",
                      formats=("step", "stl"), note=f"modèle {mode}")]
    return parts + build_balls(P)


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
    """DXF 2D vu de dessus (repère plaque, +y = arrière) avec calques : contour, zone percée, lamages Ø2,
    orifices Ø0,30, sièges de billes, taraudages, embases ADXL, datums, manutention, axes."""
    import ezdxf

    pl = P["plate"]
    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for name, color in (("CONTOUR", 7), ("ZONE_PERCEE", 3), ("TROUS_LAMAGES", 5), ("ORIFICES", 1),
                        ("APPUIS", 2), ("TARAUDAGES", 6), ("DATUMS", 4), ("ADXL", 30), ("MANUTENTION", 40),
                        ("AXES", 8)):
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
        msp.add_circle((x, y), pl["counterbore_d_mm"] / 2.0, dxfattribs={"layer": "TROUS_LAMAGES"})
        msp.add_circle((x, y), pl["orifice_d_mm"] / 2.0, dxfattribs={"layer": "ORIFICES"})
    for s in support_points(P):
        msp.add_circle((s["x"], s["y"]), pl["ball_pocket_d_mm"] / 2.0, dxfattribs={"layer": "APPUIS"})
        msp.add_text(f"P{s['index']}", height=4, dxfattribs={"layer": "APPUIS", "insert": (s["x"] + 15, s["y"] + 15)})
    for (x, y) in tap_positions(P):
        msp.add_circle((x, y), pl["tap_d_mm"] / 2.0, dxfattribs={"layer": "TARAUDAGES"})
    for (x, y) in adxl_positions(P):
        msp.add_circle((x, y), pl["adxl_hole_d_mm"] / 2.0, dxfattribs={"layer": "ADXL"})
    bx, by = pl["datum_B_mm"]
    msp.add_circle((bx, by), pl["datum_d_mm"] / 2.0, dxfattribs={"layer": "DATUMS"})
    cx, cy = pl["datum_C_mm"]
    d, ln = pl["datum_d_mm"], pl["datum_C_len_mm"]
    msp.add_line((cx - (ln - d) / 2, cy + d / 2), (cx + (ln - d) / 2, cy + d / 2), dxfattribs={"layer": "DATUMS"})
    msp.add_line((cx - (ln - d) / 2, cy - d / 2), (cx + (ln - d) / 2, cy - d / 2), dxfattribs={"layer": "DATUMS"})
    msp.add_arc((cx - (ln - d) / 2, cy), d / 2, 90, 270, dxfattribs={"layer": "DATUMS"})
    msp.add_arc((cx + (ln - d) / 2, cy), d / 2, -90, 90, dxfattribs={"layer": "DATUMS"})
    for (x, y) in pl["handling_positions_mm"]:
        msp.add_circle((x, y), pl["handling_d_mm"] / 2.0, dxfattribs={"layer": "MANUTENTION"})
    msp.add_line((-L / 2 - 10, 0), (L / 2 + 10, 0), dxfattribs={"layer": "AXES"})
    msp.add_line((0, -L / 2 - 10), (0, L / 2 + 10), dxfattribs={"layer": "AXES"})
    doc.saveas(str(path))
    return {"n_holes": len(pts)}


if __name__ == "__main__":
    from cad.common import get_params
    P = get_params()
    t0 = time.time()
    print(len(hole_centers(P)), "trous", f"{time.time() - t0:.2f}s")
    w = build_plate(P)
    print(w.val().isValid(), w.val().Volume(), f"{time.time() - t0:.2f}s")
