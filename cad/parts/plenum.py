"""Plenum / caisson : cadre en profilés alu, panneaux dans les rainures, fond avec entrée
d'air centrale, tôle perforée de distribution, bride supérieure, bride de serrage sous la
plaque et membrane souple en U (découplage plaque / plenum).

Principe (tout dérivé de cad.common.levels) :
  - 4 montants verticaux aux coins (axe à pl_cp = (inner + e_panneau)/2) prolongés vers le bas
    (pl_leg) pour reposer sur le cadre supérieur du bâti ; 4 traverses hautes + 4 basses ;
  - les panneaux sont dans les rainures : plan moyen = axe des profilés ; ils entrent de
    `panel_embed_mm` dans la rainure (volume de rainure vide => pas d'interférence) ;
  - la bride (anneau plat) repose sur le dessus du cadre ; la membrane en U pend dans
    l'ouverture, sa collerette haute est serrée sous la plaque par la bride de serrage
    (vissée dans les taraudages de la plaque), sa collerette basse est collée sur la bride.
"""
from __future__ import annotations

import math

import cadquery as cq

from cad.common import COLORS, PROFILES, PartSpec, bar_part, levels, slot_depth, support_points
from cad.parts import plate as plate_mod


def _box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def _sq_ring(h_out: float, h_in: float, z0: float, z1: float) -> cq.Workplane:
    """Anneau carré (demi-côtés h_in < h_out), z de z0 à z1."""
    return _box(-h_out, h_out, -h_out, h_out, z0, z1).cut(_box(-h_in, h_in, -h_in, h_in, z0 - 1, z1 + 1))


def _cross(hx: float, hy: float, z0: float, z1: float) -> cq.Workplane:
    """Croix = [-hx,hx]x[-hy,hy] U [-hy,hy]x[-hx,hx] (carré à coins échancrés)."""
    return _box(-hx, hx, -hy, hy, z0, z1).union(_box(-hy, hy, -hx, hx, z0, z1))


def baffle_hole_pitch(P: dict) -> float:
    """Pas hexagonal pour obtenir le taux d'ouverture : oa = pi d^2 / (2 sqrt3 p^2)."""
    d = P["plenum"]["baffle_hole_d_mm"]
    oa = P["plenum"]["baffle_open_area"]
    return d * math.sqrt(math.pi / (2.0 * math.sqrt(3.0) * oa))


def baffle_hole_centers(P: dict, L: dict) -> list[tuple[float, float]]:
    pn = P["plenum"]
    d = pn["baffle_hole_d_mm"]
    p = baffle_hole_pitch(P)
    hb = L["pl_cp"] - pn["panel_t_mm"] / 2.0 - pn["baffle_edge_gap_mm"]     # demi-côté de la tôle
    ha = L["pl_open_half"]                                                   # échancrure des coins
    m = d / 2.0 + 5.0
    col_r = pn["column_hole_d_mm"] / 2.0 + d / 2.0 + 3.0
    cols = [(s["x"], s["y"]) for s in support_points(P)]
    dy = p * math.sqrt(3.0) / 2.0
    pts = []
    nj = int(hb // dy)
    for j in range(-nj, nj + 1):
        y = j * dy
        off = 0.0 if j % 2 == 0 else p / 2.0
        for i in range(-int(hb // p) - 1, int(hb // p) + 2):
            x = i * p + off
            ok = (abs(x) <= hb - m and abs(y) <= ha - m) or (abs(x) <= ha - m and abs(y) <= hb - m)
            if ok and not any(math.hypot(x - cx, y - cy) < col_r for cx, cy in cols):
                pts.append((x, y))
    return pts


def build(P: dict) -> list[PartSpec]:
    pn, pl = P["plenum"], P["plate"]
    L = levels(P)
    key = pn["profile"]
    s, cp = L["pl_s"], L["pl_cp"]
    tp, emb = pn["panel_t_mm"], pn["panel_embed_mm"]
    assert emb <= slot_depth(key), "panel_embed_mm > profondeur de rainure"
    parts: list[PartSpec] = []

    # ---- ossature -------------------------------------------------------------------
    span = 2 * cp - s                       # longueur de coupe des traverses (entre montants)
    sx = [(+1, +1), (-1, +1), (-1, -1), (+1, -1)]
    for i, (sgx, sgy) in enumerate(sx, 1):
        parts.append(bar_part(f"plenum_montant_{i}", key, "Z", (sgx * cp, sgy * cp, L["pl_up_bot"]),
                              L["rail_top_top"] - L["pl_up_bot"], P, "plenum"))
    for lvl, zc in (("haut", (L["rail_top_top"] + L["rail_top_bot"]) / 2), ("bas", L["rail_bot_c"])):
        z0 = zc
        # traverses le long de Y (x = ±cp) puis le long de X (y = ±cp) ; l'axe neutre est à zc
        for k, sg in enumerate((+1, -1)):
            parts.append(bar_part(f"plenum_traverse_{lvl}_Y{'p' if sg > 0 else 'm'}", key, "Y",
                                  (sg * cp, -span / 2, z0), span, P, "plenum"))
            parts.append(bar_part(f"plenum_traverse_{lvl}_X{'p' if sg > 0 else 'm'}", key, "X",
                                  (-span / 2, sg * cp, z0), span, P, "plenum"))

    # ---- panneaux ----------------------------------------------------------------------
    zlo = L["rail_bot_top"] - emb
    zhi = L["rail_top_bot"] + emb
    yy = L["pl_open_half"] + emb
    for nm, (x0, x1, y0, y1) in {
        "X+": (cp - tp / 2, cp + tp / 2, -yy, yy), "X-": (-cp - tp / 2, -cp + tp / 2, -yy, yy),
        "Y+": (-yy, yy, cp - tp / 2, cp + tp / 2), "Y-": (-yy, yy, -cp - tp / 2, -cp + tp / 2),
    }.items():
        parts.append(PartSpec(f"plenum_panneau_{nm}", _box(x0, x1, y0, y1, zlo, zhi), COLORS["panneau"],
                              pn["panel_material"], "plenum", formats=("step",),
                              note="panneau plein dans les rainures"))
    # fond avec entrée d'air centrale + passages des colonnes
    fond = _cross(yy, L["pl_open_half"], L["fond_bot"], L["fond_top"])
    d_in = L["dif"]["d_out"]
    fond = fond.cut(cq.Workplane("XY").workplane(offset=L["fond_bot"] - 1).circle(d_in / 2).extrude(tp + 2))
    cols = [(c["x"], c["y"]) for c in support_points(P)]
    fond = fond.cut(cq.Workplane("XY").workplane(offset=L["fond_bot"] - 1).pushPoints(cols)
                    .circle(pn["column_hole_d_mm"] / 2).extrude(tp + 2))
    parts.append(PartSpec("plenum_fond", fond, COLORS["panneau"], pn["panel_material"], "plenum",
                          note=f"entrée d'air centrale Ø{d_in:.0f} (diffuseur), 3 passages de colonnes"))

    # ---- tôle perforée de distribution (mi-hauteur) -------------------------------------------
    hb = cp - tp / 2 - pn["baffle_edge_gap_mm"]
    baffle = _cross(hb, L["pl_open_half"], L["baffle_bot"], L["baffle_top"])
    baffle = baffle.cut(cq.Workplane("XY").workplane(offset=L["baffle_bot"] - 1).pushPoints(cols)
                        .circle(pn["column_hole_d_mm"] / 2).extrude(pn["baffle_t_mm"] + 2))
    n_holes = 0
    if pn["baffle_holes"]:
        pts = baffle_hole_centers(P, L)
        n_holes = len(pts)
        baffle = baffle.cut(cq.Workplane("XY").workplane(offset=L["baffle_bot"] - 1).pushPoints(pts)
                            .circle(pn["baffle_hole_d_mm"] / 2).extrude(pn["baffle_t_mm"] + 2))
    parts.append(PartSpec("plenum_tole_perforee", baffle, COLORS["tole"], "alu", "plenum",
                          note=f"{n_holes} trous Ø{pn['baffle_hole_d_mm']}, ouverture visée {pn['baffle_open_area']:.0%} ; "
                               "tenue par 4 tasseaux (non modélisés)"))

    # ---- bride supérieure du plenum ---------------------------------------------------------------
    bride = _sq_ring(L["pl_outer_half"], L["pl_open_half"], L["bride_bot"], L["bride_top"])
    parts.append(PartSpec("plenum_bride", bride, COLORS["bride"], "alu", "plenum", formats=("step", "stl"),
                          note="bride plate usinée, repose sur le cadre"))

    # ---- membrane U + bride de serrage sous la plaque ------------------------------------------------
    tm = pn["membrane_t_mm"]
    zp = L["plate_bot"]
    hF = pn["membrane_flange_half_mm"]
    hB = L["pl_open_half"] - pn["membrane_inset_mm"]
    hA = hB - pn["membrane_wall_spacing_mm"]
    zm = L["bride_top"] - pn["membrane_fold_dip_mm"]
    taps = [(x, y, 0) for x, y in plate_mod.tap_positions(P)]
    mem = (_sq_ring(hF, hA - tm, zp - tm, zp)                       # collerette haute (sous la plaque)
           .union(_sq_ring(hA, hA - tm, zm, zp))                     # branche intérieure
           .union(_sq_ring(hB, hA - tm, zm, zm + tm))                # fond du U
           .union(_sq_ring(hB, hB - tm, zm, L["bride_top"] + tm))    # branche extérieure
           .union(_sq_ring(hF, hB - tm, L["bride_top"], L["bride_top"] + tm)))  # collerette basse
    hole_d = pl["tap_d_mm"] + 1.3
    mem = mem.cut(cq.Workplane("XY").workplane(offset=zp - tm - 1).pushPoints([(x, y) for x, y, _ in taps])
                  .circle(hole_d / 2).extrude(tm + 2))
    parts.append(PartSpec("membrane_U", mem, COLORS["souple"], "epdm", "plenum",
                          note=f"membrane EPDM en U : branches h={hA:.0f}/{hB:.0f}, fond z={zm:.0f}, e={tm}"))
    ring_t = pn["ring_t_mm"]
    ring = _sq_ring(hF, hA + pn["ring_wall_clearance_mm"], zp - tm - ring_t, zp - tm)
    ring = ring.cut(cq.Workplane("XY").workplane(offset=zp - tm - ring_t - 1).pushPoints([(x, y) for x, y, _ in taps])
                    .circle(hole_d / 2).extrude(ring_t + 2))
    parts.append(PartSpec("plenum_bride_plaque", ring, COLORS["bride"], "alu", "plenum", formats=("step", "stl"),
                          note="bride de serrage de la membrane, vissée (M5) dans les taraudages de la plaque ; "
                               "vis non modélisées"))
    return parts
