"""Bâti Rexroth : montants 45x90, cadre supérieur 45x90 de chant (carré d'axe 250, 545 hors tout),
ceintures 45x45 (z = 150 et 420 aux notes), écharpes 45x45 sur 3 faces (arrière, gauche, droite, en deux
étages de part et d'autre de l'étagère), 4 pieds M16 / patin Ø80, platine ventilateur découplée sur
4 plots + 2 traverses, écran PMMA 120 mm + couvercle nid d'abeille, portique caméra libre (option).
Cotes : [03] §8 (z notes - 900 = z CAD).
"""
from __future__ import annotations

import math

import cadquery as cq

from cad.common import COLORS, PartSpec, _profile_z, bar_part, levels


def _box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def diagonal_part(name: str, key: str, plane: str, c: float, h0: float, z0: float, h1: float, z1: float,
                  w: float, P: dict) -> PartSpec:
    """Écharpe diagonale 45x45 dans le plan d'une face, entre les coins (h0,z0) et (h1,z1) de la baie ;
    les extrémités sont mitrées par intersection avec la baie.
    plane 'x' : face perpendiculaire à Y (h = x, profondeur y = c) ; plane 'y' : face perpendiculaire à X (h = y, x = c)."""
    from cad.common import PROFILES
    d = (h1 - h0, z1 - z0)
    Ld = math.hypot(*d)
    ext = 60.0
    ux, uz = d[0] / Ld, d[1] / Ld
    s = _profile_z(key, round(Ld + 2 * ext, 3))
    a = math.degrees(math.atan2(d[0], d[1]))
    if plane == "x":
        s = s.rotate((0, 0, 0), (0, 1, 0), a).translate((h0 - ext * ux, c, z0 - ext * uz))
        bay = _box(min(h0, h1), max(h0, h1), c - w / 2, c + w / 2, z0, z1)
    else:
        s = s.rotate((0, 0, 0), (1, 0, 0), -a).translate((c, h0 - ext * ux, z0 - ext * uz))
        bay = _box(c - w / 2, c + w / 2, min(h0, h1), max(h0, h1), z0, z1)
    s = s.intersect(bay)
    length = Ld
    return PartSpec(name, s, COLORS["profile"], "alu", "bati", mass_kg=PROFILES[key]["kg_m"] * length / 1000.0,
                    profile={"section": key, "length_mm": round(length, 1), "coupe": "mitrée dans la baie"},
                    commercial=True, note="écharpe diagonale (longueur d'axe ; coupes d'extrémité à ajuster)")


def build(P: dict) -> list[PartSpec]:
    fr, pf, sc, gt = P["frame"], P["platine"], P["screen"], P["gantry"]
    L = levels(P)
    kh, kl = fr["profile_heavy"], fr["profile_light"]
    ca, xin, yin, yc = L["ca"], L["up_x_in"], L["up_y_in"], L["up_yc"]
    wl = L["w_l"]
    parts: list[PartSpec] = []
    sgn = [(+1, +1), (-1, +1), (-1, -1), (+1, -1)]

    # ---- montants 45x90 (45 selon x, 90 selon y, faces extérieures dans le carré 545) ----------------------------
    for i, (sx, sy) in enumerate(sgn, 1):
        parts.append(bar_part(f"bati_montant_{i}", kh, "Z", (sx * ca, sy * yc, L["up_bot"]),
                              L["cad_top"] - L["up_bot"], P, "bati"))

    # ---- cadre supérieur 45x90 de chant ---------------------------------------------------------------------------------
    span_x, span_y = 2 * xin, 2 * yin
    for sg, tag in ((+1, "p"), (-1, "m")):
        parts.append(bar_part(f"bati_cadre_X{tag}", kh, "X", (-xin, sg * ca, L["cad_zc"]), span_x, P, "bati"))
        parts.append(bar_part(f"bati_cadre_Y{tag}", kh, "Y", (sg * ca, -yin, L["cad_zc"]), span_y, P, "bati"))

    # ---- ceintures 45x45 (basse + étagère) ------------------------------------------------------------------------------------
    for j, zb in enumerate(L["belts_z"]):
        for sg, tag in ((+1, "p"), (-1, "m")):
            parts.append(bar_part(f"bati_ceinture{j}_X{tag}", kl, "X", (-xin, sg * ca, zb), span_x, P, "bati"))
            parts.append(bar_part(f"bati_ceinture{j}_Y{tag}", kl, "Y", (sg * ca, -yin, zb), span_y, P, "bati"))

    # ---- écharpes (arrière, gauche, droite) : 2 étages de part et d'autre de l'étagère -----------------------------------------
    zb0, zb1 = L["belts_z"]
    h2 = wl / 2
    stages = [(zb0 + h2, zb1 - h2), (zb1 + h2, L["cad_bot"])]
    for st, (za, zb_) in enumerate(stages, 1):
        parts.append(diagonal_part(f"bati_echarpe_arriere_{st}", kl, "x", ca, -xin, za, xin, zb_, wl, P))
        for sg, tag in ((+1, "droite"), (-1, "gauche")):
            parts.append(diagonal_part(f"bati_echarpe_{tag}_{st}", kl, "y", sg * ca, -yin, za, yin, zb_, wl, P))

    # ---- pieds réglables M16 / patin Ø80 ----------------------------------------------------------------------------------------
    for i, (sx, sy) in enumerate(sgn, 1):
        base = (cq.Workplane("XY").workplane(offset=L["floor"]).center(sx * ca, sy * yc)
                .circle(fr["foot_base_d_mm"] / 2).extrude(fr["foot_base_t_mm"]))
        stud = (cq.Workplane("XY").workplane(offset=L["floor"] + fr["foot_base_t_mm"]).center(sx * ca, sy * yc)
                .circle(fr["foot_stud_d_mm"] / 2).extrude(L["up_bot"] - L["floor"] - fr["foot_base_t_mm"]))
        parts.append(PartSpec(f"bati_pied_{i}", base.union(stud), COLORS["pied"], "acier", "bati", commercial=True,
                              note="pied M16 x 2 à rotule, patin Ø80 (enveloppe)"))

    # ---- platine ventilateur découplée (4 plots) + 2 traverses ----------------------------------------------------------------------
    sx_, sy_ = pf["size_mm"]
    cx = L["pf_cx"]
    parts.append(PartSpec("platine_ventilateur", _box(cx - sx_ / 2, cx + sx_ / 2, -sy_ / 2, sy_ / 2, L["pf_bot"], L["pf_top"]),
                          COLORS["platine"], "alu", "bati", formats=("step", "stl"),
                          note="platine ventilateur sur 4 plots anti-vibratoires"))
    k = 1
    ty = pf["traverse_y_mm"]
    for yy in (-ty, ty):
        for xx in (cx - pf["plot_x_mm"], cx + pf["plot_x_mm"]):
            plot = (cq.Workplane("XY").workplane(offset=L["plot_bot"]).center(xx, yy)
                    .circle(pf["plot_d_mm"] / 2).extrude(pf["plot_h_mm"]))
            parts.append(PartSpec(f"platine_plot_{k}", plot, COLORS["plot"], "epdm", "bati", commercial=True,
                                  note="plot anti-vibratoire (enveloppe)"))
            k += 1
    for j, yy in enumerate((-ty, ty), 1):
        parts.append(bar_part(f"bati_traverse_platine_{j}", kl, "X", (-xin, yy, L["trav_top"] - wl / 2), span_x, P, "bati"))

    # ---- écran PMMA 120 mm (au bord de la zone percée) + couvercle nid d'abeille ----------------------------------------------------
    t, g = sc["t_mm"], sc["gap_mm"]
    h0 = P["zones"]["perforated_square_mm"] / 2.0 + g
    zt = fr["screen_height_mm"]
    for sg, tag in ((+1, "p"), (-1, "m")):
        parts.append(PartSpec(f"ecran_Y{tag}", _box(-h0 + 1.0, h0 - 1.0, sg * (h0 + t / 2) - t / 2, sg * (h0 + t / 2) + t / 2, 0, zt),
                              COLORS["ecran"], "pmma", "option", formats=("step",),
                              note="paroi PMMA amovible posée sur la plaque, hors embases ADXL"))
        parts.append(PartSpec(f"ecran_X{tag}", _box(sg * (h0 + t / 2) - t / 2, sg * (h0 + t / 2) + t / 2, -h0 + 1.0, h0 - 1.0, 0, zt),
                              COLORS["ecran"], "pmma", "option", formats=("step",),
                              note="paroi PMMA amovible posée sur la plaque, hors embases ADXL"))
    hl = h0 + t
    parts.append(PartSpec("ecran_couvercle", _box(-hl, hl, -hl, hl, zt, zt + sc["lid_t_mm"]), COLORS["ecran"], "alu",
                          "option", mass_kg=sc["lid_mass_kg"], note="couvercle nid d'abeille alu (enveloppe pleine)"))

    # ---- option portique caméra libre (montants au sol de part et d'autre du bâti) ------------------------------------------------------
    if gt["enabled"]:
        cw, cd, ch = gt["camera_mm"]
        z_cam_bot = L["plate_top"] + gt["camera_lens_z_mm"] + gt["lens_len_mm"]
        z_top = z_cam_bot + ch + wl
        px = gt["post_offset_mm"]
        for i, sg in enumerate((+1, -1), 1):
            parts.append(bar_part(f"portique_montant_{i}", kl, "Z", (sg * px, 0.0, L["floor"]), z_top - L["floor"], P, "option"))
        parts.append(bar_part("portique_traverse", kl, "X", (-(px - wl / 2), 0.0, z_top - wl / 2), 2 * (px - wl / 2), P, "option"))
        body = cq.Workplane("XY").box(cw, cd, ch, centered=(True, True, False)).translate((0, 0, z_cam_bot))
        lens = (cq.Workplane("XY").workplane(offset=z_cam_bot - gt["lens_len_mm"]).circle(gt["lens_d_mm"] / 2)
                .extrude(gt["lens_len_mm"]))
        parts.append(PartSpec("camera_corps", body, COLORS["camera"], "composite", "option", mass_kg=gt["camera_mass_kg"],
                              commercial=True, note="caméra (enveloppe) sous la traverse du portique"))
        parts.append(PartSpec("camera_objectif", lens, COLORS["camera"], "composite", "option", mass_kg=0.05,
                              commercial=True, note="objectif (enveloppe)"))
    return parts
