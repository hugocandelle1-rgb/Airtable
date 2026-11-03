"""Caisson de plenum suspendu à la plaque (chemin B) : parois et fond de 6 mm, joint plat EPDM 6 x 2,
cornière intérieure 15 x 15 x 3 vissée (32 x M5) sous la plaque, tôle inox de distribution,
nappe média, disque déflecteur Ø200, piquages de pression.  Cotes : [03] §8 et [02] §13.

Le caisson ne touche que la plaque (via le joint) : jeu de 6,5 mm avec le cadre.
"""
from __future__ import annotations

import math

import cadquery as cq

from cad.common import COLORS, PartSpec, levels
from cad.parts import plate as plate_mod


def _box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def _sq_ring(h_out: float, h_in: float, z0: float, z1: float) -> cq.Workplane:
    """Anneau carré (demi-côtés h_in < h_out), z de z0 à z1."""
    return _box(-h_out, h_out, -h_out, h_out, z0, z1).cut(_box(-h_in, h_in, -h_in, h_in, z0 - 1, z1 + 1))


def baffle_hole_centers(P: dict, L: dict) -> list[tuple[float, float]]:
    """Trous Ø2 de la tôle : réseau hexagonal (quinconce) de pas 8, centré, à 6 mm du bord."""
    pn = P["plenum"]
    p = pn["baffle_pitch_mm"]
    half = L["cav_half"] - pn["baffle_edge_gap_mm"] - 6.0
    dy = p * math.sqrt(3.0) / 2.0
    pts = []
    nj = int(half // dy)
    for j in range(-nj, nj + 1):
        off = 0.0 if j % 2 == 0 else p / 2.0
        for i in range(-int(half // p) - 1, int(half // p) + 2):
            x = i * p + off
            if abs(x) <= half and abs(j * dy) <= half:
                pts.append((x, j * dy))
    return pts


def baffle_open_area_realised(P: dict, L: dict) -> dict:
    pn = P["plenum"]
    n = len(baffle_hole_centers(P, L))
    a_total = (2 * (L["cav_half"] - pn["baffle_edge_gap_mm"])) ** 2
    a_holes = n * math.pi * (pn["baffle_hole_d_mm"] / 2) ** 2
    return {"n_holes": n, "taux_ouverture": a_holes / a_total, "volume_retire_mm3": a_holes * pn["baffle_t_mm"]}


def build(P: dict) -> list[PartSpec]:
    pn, pl = P["plenum"], P["plate"]
    L = levels(P)
    parts: list[PartSpec] = []
    h_o, h_i = L["box_half"], L["cav_half"]

    # ---- caisson (parois + fond de 6 mm, soudé) -----------------------------------------------------------------
    box = _box(-h_o, h_o, -h_o, h_o, L["box_bot"], L["wall_top"])
    box = box.cut(_box(-h_i, h_i, -h_i, h_i, L["floor_top"], L["wall_top"] + 1.0))
    d_in = pn["inlet_d_mm"]
    box = box.cut(cq.Workplane("XY").workplane(offset=L["box_bot"] - 1).circle(d_in / 2).extrude(pn["bottom_mm"] + 2))
    taps = []
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):                  # 4 piquages Ø4 au milieu des parois
        taps.append(cq.Solid.makeCylinder(pn["tap_d_mm"] / 2, pn["wall_mm"] + 2,
                                          cq.Vector(sx * (h_i - 1), sy * (h_i - 1), L["tap_z"]),
                                          cq.Vector(sx, sy, 0)))
    box = box.cut(cq.Workplane("XY").newObject([cq.Compound.makeCompound(taps)]))
    parts.append(PartSpec("caisson", box, COLORS["panneau"], pn["wall_material"], "plenum", formats=("step",),
                          note=f"caisson {2 * h_i:.0f} x {2 * h_i:.0f} int., parois/fond {pn['wall_mm']:.0f} mm, "
                               f"entrée Ø{d_in:.0f}, 4 piquages Ø{pn['tap_d_mm']:.0f}"))

    # ---- joint plat EPDM 6 x 2 ------------------------------------------------------------------------------------------
    gk_w, gk_t = pn["gasket_mm"]
    parts.append(PartSpec("joint_plat", _sq_ring(h_o, h_o - gk_w, L["gasket_bot"], L["gasket_top"]),
                          COLORS["joint"], "epdm", "plenum", note="joint plat EPDM 6 x 2 sous la plaque"))

    # ---- cornière intérieure 15 x 15 x 3 (32 x M5 dans la plaque) ----------------------------------------------------------------
    leg, te = pn["angle_mm"]
    zp = L["plate_bot"]
    horiz = _sq_ring(h_i, h_i - leg, zp - te, zp)
    vert = _sq_ring(h_i, h_i - te, zp - leg, zp)
    ang = horiz.union(vert)
    holes = [(x, y) for x, y in plate_mod.tap_positions(P)]
    ang = ang.cut(cq.Workplane("XY").workplane(offset=zp - te - 1).pushPoints(holes).circle(2.75).extrude(te + 2))
    parts.append(PartSpec("corniere_caisson", ang, COLORS["bride"], "alu", "plenum", formats=("step",),
                          note=f"cornière {leg:.0f} x {leg:.0f} x {te:.0f}, 32 trous Ø5,5 (vis M5 dans la plaque)"))

    # ---- tôle inox de distribution + nappe média --------------------------------------------------------------------------------
    hb = h_i - pn["baffle_edge_gap_mm"]
    baffle = _box(-hb, hb, -hb, hb, L["baffle_bot"], L["baffle_top"])
    pts = baffle_hole_centers(P, L)
    if not pn["baffle_holes_full"]:
        pts = sorted(pts, key=lambda c: (round(math.hypot(*c), 6), c))[:19]          # modèle léger : trous témoins
    tool = cq.Workplane("XY").workplane(offset=L["baffle_bot"] - 1).pushPoints(pts) \
        .circle(pn["baffle_hole_d_mm"] / 2).extrude(pn["baffle_t_mm"] + 2)
    baffle = baffle.cut(tool)
    ba = baffle_open_area_realised(P, L)
    # la tôle pleine réelle porte ba['n_holes'] trous : masse corrigée en analytique
    m_full = (_vol := ((2 * hb) ** 2 * pn["baffle_t_mm"] - ba["volume_retire_mm3"])) * 1e-9 * P["materials"]["inox"]
    parts.append(PartSpec("tole_distribution", baffle, COLORS["tole"], "inox", "plenum", mass_kg=m_full,
                          note=f"inox ép. {pn['baffle_t_mm']:.0f}, trous Ø{pn['baffle_hole_d_mm']:.0f} pas "
                               f"{pn['baffle_pitch_mm']:.0f} quinconce ({ba['n_holes']} trous, "
                               f"{ba['taux_ouverture']:.1%}) ; modèle léger : 19 trous témoins ; tasseaux non modélisés"))
    media = _box(-hb, hb, -hb, hb, L["baffle_top"], L["media_top"])
    parts.append(PartSpec("nappe_media", media, COLORS["filtre"], "media_filtrant", "plenum", commercial=True,
                          note="nappe média polyester 10 mm sur la tôle"))

    # ---- disque déflecteur Ø200 à 25 mm du fond + 3 plots ---------------------------------------------------------------------------------
    zd = L["deflector_bot"]
    disc = cq.Workplane("XY").workplane(offset=zd).circle(pn["deflector_d_mm"] / 2).extrude(pn["deflector_t_mm"])
    parts.append(PartSpec("deflecteur", disc, COLORS["tole"], "alu", "plenum", formats=("step",),
                          note="disque déflecteur Ø200 à 25 mm du fond"))
    posts = [cq.Solid.makeCylinder(pn["deflector_posts_d_mm"] / 2, zd - L["floor_top"],
                                   cq.Vector(pn["deflector_posts_r_mm"] * math.cos(math.radians(90 + 120 * k)),
                                             pn["deflector_posts_r_mm"] * math.sin(math.radians(90 + 120 * k)),
                                             L["floor_top"]), cq.Vector(0, 0, 1)) for k in range(3)]
    parts.append(PartSpec("deflecteur_plots", cq.Workplane("XY").newObject([cq.Compound.makeCompound(posts)]),
                          COLORS["tole"], "alu", "plenum", note="3 plots Ø6 du déflecteur"))
    return parts
