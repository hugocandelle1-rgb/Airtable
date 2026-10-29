"""Bâti : table en profilés (emprise frame.footprint_mm, plateau à frame.table_height_mm),
cadres haut / bas, cadre supérieur (traverses porteuses du plenum + consoles des vérins),
pieds réglables, platine support ventilateur découplée (plots), écran anti-courant d'air
amovible et option portique caméra.
"""
from __future__ import annotations

import cadquery as cq

from cad.common import COLORS, PROFILES, PartSpec, bar_part, levels, profile_key, support_points


def _box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def build(P: dict) -> list[PartSpec]:
    fr, pf, sc, gt, lv = P["frame"], P["platine"], P["screen"], P["gantry"], P["leveling"]
    L = levels(P)
    key = profile_key(fr["profile_main_mm"])
    fs, cp, ih = L["fs"], L["fr_cp"], L["fr_in_half"]
    span = 2 * ih
    parts: list[PartSpec] = []

    # ---- montants ----------------------------------------------------------------------------------
    corners = [(+1, +1), (-1, +1), (-1, -1), (+1, -1)]
    for i, (sx, sy) in enumerate(corners, 1):
        parts.append(bar_part(f"bati_montant_{i}", key, "Z", (sx * cp, sy * cp, L["up_bot"]),
                              L["top_ring_top"] - L["up_bot"], P, "bati"))

    def ring(name, zc):
        for sg, tag in ((+1, "p"), (-1, "m")):
            parts.append(bar_part(f"{name}_X{tag}", key, "X", (-ih, sg * cp, zc), span, P, "bati"))
            parts.append(bar_part(f"{name}_Y{tag}", key, "Y", (sg * cp, -ih, zc), span, P, "bati"))

    ring("bati_cadre_haut", L["top_ring_top"] - fs / 2)
    ring("bati_cadre_bas", L["low_ring_bot"] + fs / 2)
    zc_cs = L["cad_sup_top"] - fs / 2
    ring("bati_cadre_sup", zc_cs)

    # ---- traverses porteuses du plenum (sous les montants du plenum) -------------------------------------
    for sg, tag in ((+1, "p"), (-1, "m")):
        parts.append(bar_part(f"bati_traverse_plenum_{tag}", key, "Y", (sg * L["pl_cp"], -ih, zc_cs), span, P, "bati"))

    # ---- consoles des vérins / du pivot (le long de Y, depuis le bord le plus proche) ---------------------------
    cl = lv["console_clear_mm"]
    for sp in support_points(P):
        s = 1.0 if sp["y"] >= 0 else -1.0
        y0, y1 = (sp["y"] - cl, ih) if s > 0 else (-ih, sp["y"] + cl)
        parts.append(bar_part(f"bati_console_{sp['index'] + 1}", key, "Y", (sp["x"], y0, zc_cs), y1 - y0, P,
                              "bati", note=f"console de l'appui {sp['index'] + 1} ({sp['role']})"))

    # ---- pieds réglables ---------------------------------------------------------------------------------------
    for i, (sx, sy) in enumerate(corners, 1):
        base = (cq.Workplane("XY").workplane(offset=L["floor"]).center(sx * cp, sy * cp)
                .circle(fr["foot_base_d_mm"] / 2).extrude(fr["foot_base_t_mm"]))
        stud = (cq.Workplane("XY").workplane(offset=L["floor"] + fr["foot_base_t_mm"]).center(sx * cp, sy * cp)
                .circle(fr["foot_stud_d_mm"] / 2).extrude(L["up_bot"] - L["floor"] - fr["foot_base_t_mm"]))
        parts.append(PartSpec(f"bati_pied_{i}", base.union(stud), COLORS["pied"], "acier", "bati",
                              commercial=True, note="pied réglable (embase + tige M16)"))

    # ---- platine support ventilateur découplée (plots) + traverses porteuses -------------------------------------
    sx_, sy_ = pf["size_mm"]
    cx, cy = L["pf_cx"], L["pf_cy"]
    parts.append(PartSpec("platine_ventilateur",
                          _box(cx - sx_ / 2, cx + sx_ / 2, cy - sy_ / 2, cy + sy_ / 2, L["pf_bot"], L["pf_top"]),
                          COLORS["platine"], "alu", "bati", formats=("step", "stl"),
                          note="platine ventilateur, posée sur 4 plots anti-vibratoires"))
    ins = pf["plot_inset_mm"]
    px = [cx - sx_ / 2 + ins, cx + sx_ / 2 - ins]
    py = [cy - sy_ / 2 + ins, cy + sy_ / 2 - ins]
    k = 1
    for yy in py:
        for xx in px:
            plot = (cq.Workplane("XY").workplane(offset=L["plot_bot"]).center(xx, yy)
                    .circle(pf["plot_d_mm"] / 2).extrude(pf["plot_h_mm"]))
            parts.append(PartSpec(f"platine_plot_{k}", plot, COLORS["plot"], "epdm", "bati", commercial=True,
                                  note="plot anti-vibratoire (enveloppe)"))
            k += 1
    for j, yy in enumerate(py, 1):
        parts.append(bar_part(f"bati_traverse_platine_{j}", key, "X", (-ih, yy, L["trav_pf_top"] - fs / 2), span,
                              P, "bati"))

    # ---- écran anti-courant d'air amovible (PMMA) ------------------------------------------------------------------
    t = sc["t_mm"]
    z0, z1 = L["top_ring_top"], L["plate_top"] + sc["height_above_plate_mm"]
    for sg, tag in ((+1, "p"), (-1, "m")):
        parts.append(PartSpec(f"ecran_Y{tag}", _box(-ih, ih, sg * cp - t / 2, sg * cp + t / 2, z0, z1),
                              COLORS["ecran"], "pmma", "option", formats=("step",),
                              note="panneau transparent amovible posé sur le cadre haut"))
        parts.append(PartSpec(f"ecran_X{tag}", _box(sg * cp - t / 2, sg * cp + t / 2, -ih, ih, z0, z1),
                              COLORS["ecran"], "pmma", "option", formats=("step",),
                              note="panneau transparent amovible posé sur le cadre haut"))

    # ---- option portique caméra ------------------------------------------------------------------------------------------
    if gt["enabled"]:
        cw, cd, ch = gt["camera_mm"]
        z_cam_bot = L["plate_top"] + gt["camera_lens_z_mm"] + gt["lens_len_mm"]
        z_arm_bot = z_cam_bot + ch
        z_top = z_arm_bot + fs
        for i, sx in enumerate((+1, -1), 1):
            parts.append(bar_part(f"portique_montant_{i}", key, "Z", (sx * cp, cp, L["top_ring_top"]),
                                  z_top - L["top_ring_top"], P, "option"))
        parts.append(bar_part("portique_traverse", key, "X", (-ih, cp, z_top - fs / 2), span, P, "option"))
        parts.append(bar_part("portique_bras", key, "Y", (0.0, -fs / 2, z_top - fs / 2), ih + fs / 2, P, "option"))
        body = cq.Workplane("XY").box(cw, cd, ch, centered=(True, True, False)).translate((0, 0, z_cam_bot))
        lens = (cq.Workplane("XY").workplane(offset=z_cam_bot - gt["lens_len_mm"]).circle(gt["lens_d_mm"] / 2)
                .extrude(gt["lens_len_mm"]))
        parts.append(PartSpec("camera_corps", body, COLORS["camera"], "composite", "option", mass_kg=gt["camera_mass_kg"],
                              commercial=True, note="caméra (enveloppe) sous le bras du portique"))
        parts.append(PartSpec("camera_objectif", lens, COLORS["camera"], "composite", "option", mass_kg=0.05,
                              commercial=True, note="objectif (enveloppe)"))
    return parts
