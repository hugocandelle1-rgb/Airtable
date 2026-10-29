"""Chaîne aéraulique : ventilateur (enveloppe), manchon souple, adaptateur rectangle -> rond,
diffuseur conique, buse d'entrée calibrée (bellmouth) avec carter et filtre à l'aspiration.

Disposition : chaîne verticale sous le plenum, axe Z = axe de l'entrée d'air centrale ;
la soufflante est couchée (axe d'aspiration horizontal, vers -Y), sortie rectangulaire vers le haut.
"""
from __future__ import annotations

import math

import cadquery as cq

from cad.common import COLORS, PartSpec, levels


def _rect_tube(ow: float, od: float, wall: float, z0: float, z1: float) -> cq.Workplane:
    """Tube rectangulaire : ouverture ow x od, épaisseur `wall`, de z0 à z1, centré sur Z."""
    outer = cq.Workplane("XY").workplane(offset=z0).rect(ow + 2 * wall, od + 2 * wall).extrude(z1 - z0)
    inner = cq.Workplane("XY").workplane(offset=z0 - 1).rect(ow, od).extrude(z1 - z0 + 2)
    return outer.cut(inner)


def _loft_rect_to_round(ow: float, od: float, d: float, z0: float, z1: float) -> cq.Workplane:
    """Solide plein rectangle ow x od (en z0) -> cercle Ø d (en z1)."""
    return (cq.Workplane("XY").workplane(offset=z0).rect(ow, od)
            .workplane(offset=z1 - z0).circle(d / 2.0).loft(combine=True))


def build(P: dict) -> list[PartSpec]:
    A, F, L = P["aero"], P["fan"], levels(P)
    D = L["dif"]
    w = F["wall_mm"]
    ow, od = F["outlet_mm"]
    fw, fh, ft = F["size_mm"]                    # face (X), face (Z), épaisseur (Y)
    parts: list[PartSpec] = []

    # ---- ventilateur : carter + embout de sortie ----------------------------------------
    box = cq.Workplane("XY").box(fw, ft, fh).translate((L["fan_xc"], L["fan_yc"], L["fan_zc"]))
    stub = _rect_tube(ow, od, w, L["fan_top"], L["stub_top"])
    fan = box.union(stub)
    parts.append(PartSpec("ventilateur", fan, COLORS["ventilateur"], "composite", "aero",
                          mass_kg=F["mass_kg"], commercial=True,
                          note=f"enveloppe soufflante {fw:.0f}x{fh:.0f}x{ft:.0f}, sortie {ow:.0f}x{od:.0f} (réf. TBD)"))
    # cale sous le ventilateur
    cale = (cq.Workplane("XY").box(60.0, ft, F["standoff_mm"], centered=(True, True, False))
            .translate((L["fan_xc"], L["fan_yc"], L["cale_bot"])))
    parts.append(PartSpec("cale_ventilateur", cale, COLORS["platine"], "alu", "aero", note="cale/appui du ventilateur"))

    # ---- manchon souple -------------------------------------------------------------------
    man = _rect_tube(ow, od, w, L["man_bot"], L["man_top"])
    parts.append(PartSpec("manchon_souple", man, COLORS["souple"], "epdm", "aero",
                          note="manchon souple rectangulaire (découplage vibratoire)"))

    # ---- adaptateur rectangle -> rond (creux) -----------------------------------------------------
    dw = A["diffuser_wall_mm"]
    z0, z1 = L["adp_bot"], L["adp_top"]
    outer = _loft_rect_to_round(ow + 2 * w, od + 2 * w, D["d_in"] + 2 * dw, z0, z1)
    inner = _loft_rect_to_round(ow, od, D["d_in"], z0, z1)
    adp = outer.cut(inner)
    parts.append(PartSpec("adaptateur_rect_rond", adp, COLORS["aero"], "pla", "aero", formats=("step", "stl"),
                          note="impression 3D, loft rectangle -> rond"))

    # ---- diffuseur conique (demi-angle, Ø entrée/sortie, longueur) ----------------------------------
    ri, ro = D["d_in"] / 2.0, D["d_out"] / 2.0
    fr = ro + A["diffuser_flange_extra_mm"] / 2.0
    ft_ = A["diffuser_flange_t_mm"]
    zb, zt = L["dif_bot"], L["dif_top"]
    prof = [(ri, zb), (ri + dw, zb), (ro + dw, zt - ft_), (fr, zt - ft_), (fr, zt), (ro, zt)]
    dif = cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0))
    parts.append(PartSpec("diffuseur_conique", dif, COLORS["aero"], "pla", "aero", formats=("step", "stl"),
                          note=f"demi-angle {D['half_angle_deg']:.2f} deg, Ø{D['d_in']:.0f}->Ø{D['d_out']:.0f}, "
                               f"L={D['length']:.1f} mm, bride Ø{2 * fr:.0f}"))

    # ---- buse d'entrée calibrée + carter + filtre (construits le long de +Z local, puis couchés) ----------
    rt, Rf, Lb = A["bell_throat_d_mm"] / 2.0, A["bell_flare_r_mm"], A["bell_len_mm"]
    r_o = rt + Rf + A["bell_lip_mm"]
    r_h = A["filter_d_mm"] / 2.0 + 0.2
    hw = A["housing_wall_mm"]
    tube = L["bell_tube_len"]
    c = (rt + Rf, Lb - Rf)
    mid = (c[0] - Rf * math.cos(math.radians(45)), c[1] + Rf * math.sin(math.radians(45)))
    assert r_o < r_h, "filter_d trop petit pour la buse"
    bell = (cq.Workplane("XZ").moveTo(rt, 0).lineTo(r_h + hw, 0).lineTo(r_h + hw, tube).lineTo(r_h, tube)
            .lineTo(r_h, 3.0).lineTo(r_o, 3.0).lineTo(r_o, Lb).lineTo(rt + Rf, Lb)
            .threePointArc(mid, (rt, Lb - Rf)).close().revolve(360, (0, 0, 0), (0, 1, 0)))
    zf0 = Lb + A["bell_lip_mm"] + A["filter_gap_mm"]
    filt = cq.Workplane("XY").workplane(offset=zf0).circle(A["filter_d_mm"] / 2.0).extrude(A["filter_t_mm"])

    def place(s):  # z local -> -Y global, au droit de l'orifice d'aspiration du ventilateur
        return s.rotate((0, 0, 0), (1, 0, 0), 90).translate((L["fan_xc"], -ft / 2.0, L["fan_zc"]))

    parts.append(PartSpec("buse_entree_bellmouth", place(bell), COLORS["aero"], "pla", "aero",
                          formats=("step", "stl"),
                          note=f"buse Ø{2 * rt:.0f}, rayon {Rf:.0f}, avec bride et carter de filtre (impression 3D)"))
    parts.append(PartSpec("filtre_aspiration", place(filt), COLORS["filtre"], "media_filtrant", "aero",
                          commercial=True, note=f"média filtrant Ø{A['filter_d_mm']:.0f}x{A['filter_t_mm']:.0f}"))
    return parts
