"""Chaîne aéraulique : ventilateur San Ace 9BMC (enveloppe), manchon souple, adaptateur sortie -> Ø50,
diffuseur conique 2θ = 7 deg Ø50 -> Ø80, conduit Ø80 avec vanne de décharge, et aspiration déportée
(caisson 320 x 320 x 220, filtre ePM1, buse col Ø30, tube).  Cotes : [02] §13 (DEFAULTS : fan, aero).

Disposition : chaîne verticale sous le caisson, axe Z central ; la soufflante est couchée (axe d'aspiration
horizontal vers -Y), sortie rectangulaire vers le haut ; le caisson d'aspiration est devant le bâti (-Y).
"""
from __future__ import annotations

import math

import cadquery as cq

from cad.common import COLORS, PartSpec, levels


def _rect_tube(ow: float, od: float, wall: float, z0: float, z1: float) -> cq.Workplane:
    outer = cq.Workplane("XY").workplane(offset=z0).rect(ow + 2 * wall, od + 2 * wall).extrude(z1 - z0)
    inner = cq.Workplane("XY").workplane(offset=z0 - 1).rect(ow, od).extrude(z1 - z0 + 2)
    return outer.cut(inner)


def _loft_rect_to_round(ow: float, od: float, d: float, z0: float, z1: float) -> cq.Workplane:
    return (cq.Workplane("XY").workplane(offset=z0).rect(ow, od)
            .workplane(offset=z1 - z0).circle(d / 2.0).loft(combine=True))


def _box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def _tube_x(x0, x1, y, z, d_in, d_out) -> cq.Workplane:
    c = cq.Solid.makeCylinder(d_out / 2, x1 - x0, cq.Vector(x0, y, z), cq.Vector(1, 0, 0))
    i = cq.Solid.makeCylinder(d_in / 2, x1 - x0 + 2, cq.Vector(x0 - 1, y, z), cq.Vector(1, 0, 0))
    return cq.Workplane("XY").newObject([c.cut(i)])


def build(P: dict) -> list[PartSpec]:
    A, F, L = P["aero"], P["fan"], levels(P)
    D = L["dif"]
    w = F["wall_mm"]
    ow, od = F["outlet_mm"]
    fw, fh, ft = F["size_mm"]                    # face (X), face (Z), épaisseur (Y)
    parts: list[PartSpec] = []

    # ---- ventilateur + cale ---------------------------------------------------------------------------------
    box = cq.Workplane("XY").box(fw, ft, fh).translate((L["fan_xc"], L["fan_yc"], L["fan_zc"]))
    fan = box.union(_rect_tube(ow, od, w, L["fan_top"], L["stub_top"]))
    parts.append(PartSpec("ventilateur", fan, COLORS["ventilateur"], "composite", "aero", mass_kg=F["mass_kg"],
                          commercial=True, note=f"San Ace 9BMC24P2G001 : enveloppe {fw:.0f}x{fh:.0f}x{ft:.0f} ; "
                                                f"sortie {ow:.0f}x{od:.0f} NON DOCUMENTÉE (à lire sur la fiche)"))
    cale = (cq.Workplane("XY").box(60.0, ft, F["standoff_mm"], centered=(True, True, False))
            .translate((L["fan_xc"], L["fan_yc"], L["cale_bot"])))
    parts.append(PartSpec("cale_ventilateur", cale, COLORS["platine"], "alu", "aero", note="cale/appui du ventilateur"))

    # ---- manchon souple L100 + adaptateur sortie -> Ø50 ------------------------------------------------------------
    parts.append(PartSpec("manchon_souple", _rect_tube(ow, od, w, L["man_bot"], L["man_top"]), COLORS["souple"],
                          "epdm", "aero", note=f"manchon souple rectangulaire L{A['manchon_len_mm']:.0f}"))
    dw = A["diffuser_wall_mm"]
    outer = _loft_rect_to_round(ow + 2 * w, od + 2 * w, D["d_in"] + 2 * dw, L["adp_bot"], L["adp_top"])
    inner = _loft_rect_to_round(ow, od, D["d_in"], L["adp_bot"], L["adp_top"])
    parts.append(PartSpec("adaptateur_rect_rond", outer.cut(inner), COLORS["aero"], "pla", "aero",
                          formats=("step", "stl"), note="impression 3D, loft rectangle -> Ø50"))

    # ---- diffuseur conique ---------------------------------------------------------------------------------------------
    ri, ro = D["d_in"] / 2.0, D["d_out"] / 2.0
    fr, ft_ = ro + A["flange_extra_mm"] / 2.0, A["flange_t_mm"]
    zb, zt = L["dif_bot"], L["dif_top"]
    prof = [(ri, zb), (ri + dw, zb), (ro + dw, zt - ft_), (fr, zt - ft_), (fr, zt), (ro, zt)]
    dif = cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0))
    parts.append(PartSpec("diffuseur_conique", dif, COLORS["aero"], "pla", "aero", formats=("step", "stl"),
                          note=f"demi-angle {D['half_angle_deg']:.2f} deg, Ø{D['d_in']:.0f}->Ø{D['d_out']:.0f}, "
                               f"L={D['length']:.1f} mm, bride Ø{2 * fr:.0f}"))

    # ---- conduit Ø80 (bride haute sous le caisson) + vanne de décharge sur piquage Ø40 --------------------------------------
    zb, zt = L["duct_bot"], L["duct_top"]
    zm = (zb + zt) / 2.0
    prof = [(ro, zb), (fr, zb), (fr, zb + ft_), (ro + dw, zb + ft_), (ro + dw, zt - ft_), (fr, zt - ft_), (fr, zt),
            (ro, zt)]
    duct = cq.Workplane("XZ").polyline(prof).close().revolve(360, (0, 0, 0), (0, 1, 0))
    dv = A["valve_branch_d_mm"]
    duct = duct.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(dv / 2, ro + 10, cq.Vector(0, 0, 0 + 0),
                                                                          cq.Vector(1, 0, 0))]).translate((0, 0, zm)))
    parts.append(PartSpec("conduit_vanne", duct, COLORS["aero"], "pla", "aero", formats=("step", "stl"),
                          note=f"conduit Ø{D['d_out']:.0f} L{A['duct_len_mm']:.0f}, piquage Ø{dv:.0f} de la vanne"))
    r_out = ro + dw
    br = A["valve_branch_len_mm"]
    cyl_duct = cq.Workplane("XY").newObject([cq.Solid.makeCylinder(r_out, 100, cq.Vector(0, 0, zm - 50),
                                                                     cq.Vector(0, 0, 1))])
    saddle = _tube_x(r_out - 12, r_out + br, 0, zm, dv, dv + 4).cut(cyl_duct)
    vb = A["valve_body_mm"]
    x0 = r_out + br
    body = _box(x0, x0 + vb, -vb / 2, vb / 2, zm - vb / 2, zm + vb / 2).cut(
        _tube_x(x0 - 1, x0 + vb + 1, 0, zm, 0.01, dv))
    exh = _tube_x(x0 + vb, x0 + vb + A["valve_exhaust_len_mm"], 0, zm, dv, dv + 4)
    parts.append(PartSpec("vanne_piquage", saddle, COLORS["aero"], "pla", "aero", note="piquage Ø40 de la vanne"))
    parts.append(PartSpec("vanne_corps", body, COLORS["verin"], "alu", "aero", commercial=True,
                          note="vanne de décharge 2 états (enveloppe 50 x 50 x 50), commutation à 238 Pa"))
    parts.append(PartSpec("vanne_rejet", exh, COLORS["souple"], "pla", "aero", note="rejet canalisé (départ)"))

    # ---- aspiration déportée : caisson 320 x 220 x 320, filtre ePM1, buse col Ø30, tube --------------------------------------------
    bx, by, bz = A["box_mm"]
    bw = A["box_wall_mm"]
    xc, zc_ = L["fan_xc"], (L["box_z0"] + L["box_z1"]) / 2.0
    yr, yf = L["box_y_rear"], L["box_y_far"]
    shell = _box(xc - bx / 2, xc + bx / 2, yf, yr, L["box_z0"], L["box_z1"])
    shell = shell.cut(_box(xc - bx / 2 + bw, xc + bx / 2 - bw, yf + bw, yr - bw, L["box_z0"] + bw, L["box_z1"] - bw))
    wn = A["window_mm"]
    shell = shell.cut(_box(xc - wn / 2, xc + wn / 2, yf - 1, yf + bw + 1, zc_ - wn / 2, zc_ + wn / 2))
    d_t = P["fan"]["size_mm"][2] * 0 + 2 * 15.0                       # col Ø30 = alésage du tube
    t_w = A["suction_tube_wall_mm"]
    hole = cq.Solid.makeCylinder(d_t / 2 + t_w + 0.2, bw + 2, cq.Vector(xc, yr - bw - 1, L["fan_zc"]), cq.Vector(0, 1, 0))
    shell = shell.cut(cq.Workplane("XY").newObject([hole]))
    parts.append(PartSpec("aspiration_caisson", shell, COLORS["panneau"], "alu", "aero", formats=("step",),
                          note=f"caisson d'aspiration {bx:.0f} x {by:.0f} x {bz:.0f}, tôle {bw:.0f} mm, fenêtre {wn:.0f}"))
    fx, fy, fz = A["filter_mm"]
    filt = _box(xc - fx / 2, xc + fx / 2, yf + bw, yf + bw + fy, zc_ - fz / 2, zc_ + fz / 2)
    parts.append(PartSpec("aspiration_filtre", filt, COLORS["filtre"], "media_filtrant", "aero", commercial=True,
                          note=f"filtre ISO 16890 ePM1 {fx:.0f} x {fz:.0f} x {fy:.0f}"))
    # buse col Ø30 (profil ISO 5801 approché par un arc), construite le long de +Z local puis couchée vers -Y
    rt, Rf, lip = d_t / 2.0, A["bell_flare_r_mm"], A["bell_lip_mm"]
    Lb = Rf + 6.0
    r_o = rt + Rf + lip
    c = (rt + Rf, Lb - Rf)
    mid = (c[0] - Rf * math.cos(math.radians(45)), c[1] + Rf * math.sin(math.radians(45)))
    bell = (cq.Workplane("XZ").moveTo(rt, 0).lineTo(r_o + 8.0, 0).lineTo(r_o + 8.0, 3.0).lineTo(r_o, 3.0)
            .lineTo(r_o, Lb).lineTo(rt + Rf, Lb).threePointArc(mid, (rt, Lb - Rf)).close()
            .revolve(360, (0, 0, 0), (0, 1, 0)))
    bell = bell.rotate((0, 0, 0), (1, 0, 0), 90).translate((xc, yr - bw, L["fan_zc"]))
    parts.append(PartSpec("aspiration_buse", bell, COLORS["aero"], "pla", "aero", formats=("step", "stl"),
                          note=f"buse col Ø{d_t:.0f}, rayon {Rf:.0f} (profil ISO 5801 approché), impression 3D"))
    Lt = L["fan_y_in"] - (yr - bw)
    t_out = cq.Workplane("XY").newObject([cq.Solid.makeCylinder(d_t / 2 + t_w, Lt, cq.Vector(xc, yr - bw, L["fan_zc"]),
                                                                  cq.Vector(0, 1, 0))])
    t_in = cq.Workplane("XY").newObject([cq.Solid.makeCylinder(d_t / 2, Lt + 2, cq.Vector(xc, yr - bw - 1, L["fan_zc"]),
                                                                 cq.Vector(0, 1, 0))])
    tube = t_out.cut(t_in)
    parts.append(PartSpec("aspiration_tube", tube, COLORS["souple"], "pla", "aero",
                          note=f"tube d'aspiration Ø{d_t:.0f} int. (du col au ventilateur)"))
    return parts
