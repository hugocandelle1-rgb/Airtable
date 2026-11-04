"""Appuis Maxwell (3 vés), vérins à coin (P1, P2), pivot fixe (P0), étriers anti-soulèvement,
embases isothermes ADXL355.  Cotes : [03] §8, [05] §7 (DEFAULTS : support, leveling, tilt_sensors).

Local -> global : chaque ensemble est construit dans un repère local (u le long de l'axe de
travail, v transversal, w vers le haut) puis tourné autour de Z et translaté.
"""
from __future__ import annotations

import math

import cadquery as cq

from cad.common import COLORS, PartSpec, levels, support_points, vee_geometry


def _box(u0, u1, v0, v1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(u1 - u0, v1 - v0, z1 - z0, centered=False).translate((u0, v0, z0))


def _cyl_u(u0: float, u1: float, v: float, z: float, d: float) -> cq.Workplane:
    """Cylindre d'axe parallèle à u (X local)."""
    return cq.Workplane("XY").newObject([cq.Solid.makeCylinder(d / 2.0, u1 - u0, cq.Vector(u0, v, z),
                                                                cq.Vector(1, 0, 0))])


def _place(shape: cq.Workplane, x: float, y: float, angle_deg: float) -> cq.Workplane:
    return shape.rotate((0, 0, 0), (0, 0, 1), angle_deg).translate((x, y, 0))


# -----------------------------------------------------------------------------
#  Bloc de vé : 2 rouleaux Ø20 x 30 h6 + bloc 40 x 30 x 20 ; la bille est dans plate.py
# -----------------------------------------------------------------------------
def vee_parts(P: dict, sp: dict, L: dict) -> list[PartSpec]:
    S = P["support"]
    bl, bw, bh = S["vee_block_mm"]
    V = vee_geometry(P)
    hs, rr = V["half_spacing"], S["roller_d_mm"] / 2.0
    zb, zr = L["block_base"], L["roller_z"]
    i = sp["index"]
    block = _box(-bl / 2, bl / 2, -bw / 2, bw / 2, zb, zb + bh)
    for sg in (+1, -1):
        block = block.cut(_cyl_u(-bl / 2 - 1, bl / 2 + 1, sg * hs, zr, S["roller_d_mm"]))
    block = block.cut(_box(-bl / 2 - 1, bl / 2 + 1, -(hs - 2.0), hs - 2.0, zb + 10.0, zb + bh + 1.0))
    parts = [PartSpec(f"vee_bloc_{i}", _place(block, sp["x"], sp["y"], sp["vee_angle"]), COLORS["acier"], "acier",
                      "appuis", formats=("step",), note=f"bloc de vé P{i}, axe à {sp['vee_angle']:.1f} deg")]
    for k, sg in enumerate((+1, -1)):
        r = _cyl_u(-S["roller_len_mm"] / 2, S["roller_len_mm"] / 2, sg * hs, zr, S["roller_d_mm"])
        parts.append(PartSpec(f"vee_rouleau_{i}{'ab'[k]}", _place(r, sp["x"], sp["y"], sp["vee_angle"]),
                              COLORS["acier"], "acier", "appuis", formats=("step",), commercial=True,
                              note="rouleau Ø20 x 30 h6 trempé"))
    return parts


# -----------------------------------------------------------------------------
#  Vérin à coin 1:5 (boîtier, coin, tête, vis, accouplement, moteur NEMA17, bouton)
# -----------------------------------------------------------------------------
def jack_parts(P: dict, sp: dict, L: dict) -> list[PartSpec]:
    lv = P["leveling"]
    i = sp["index"]
    H = L["stack_h"]
    z0 = L["cad_top"]
    hu, hv = lv["housing_mm"]
    wl, ww = lv["wedge_mm"]
    fl = lv["wedge_floor_mm"]
    tan = P["leveling"]["wedge_tan"] if "wedge_tan" in P["leveling"] else 0.2
    w_ax = lv["nema17_mm"][0] / 2.0                       # axe de vis = axe moteur (21 au-dessus du cadre)
    # profil du coin dans (u, w) : épaisseur 18 (extrémité mince) -> 30 (épaisse), pente 1:5
    w_thin = 24.0
    w_thick = w_thin + wl * tan
    wedge_poly = [(-wl / 2, z0 + fl), (wl / 2, z0 + fl), (wl / 2, z0 + w_thick), (-wl / 2, z0 + w_thin)]

    def prism(poly, v0, v1):          # polygone dans le plan (u, z), extrudé selon v
        return (cq.Workplane("XZ").polyline(poly).close().extrude(-(v1 - v0)).translate((0, v0, 0)))

    wedge_full = prism(wedge_poly, -ww / 2, ww / 2)
    wedge = wedge_full.cut(_cyl_u(-wl / 2 - 1, wl / 2 + 1, 0, z0 + w_ax, lv["screw_d_mm"]))
    cav = _box(-hu / 2 + 2, hu / 2 - 2, -ww / 2 - 0.2, ww / 2 + 0.2, z0 + fl, z0 + H + 1)
    housing = _box(-hu / 2, hu / 2, -hv / 2, hv / 2, z0, z0 + H).cut(cav)
    housing = housing.cut(_cyl_u(hu / 2 - 3, hu / 2 + 1, 0, z0 + w_ax, lv["screw_d_mm"] + 0.4))
    hd = lv["head_u_mm"]
    head = _box(-hd / 2, hd / 2, -ww / 2 + 0.2, ww / 2 - 0.2, z0 + w_thin - hd / 2 * tan, z0 + H).cut(wedge_full)
    screw = _cyl_u(-hu / 2 + 4, hu / 2, 0, z0 + w_ax, lv["screw_d_mm"])
    cpl = _cyl_u(hu / 2, hu / 2 + lv["coupling_len_mm"], 0, z0 + w_ax, 10.0)
    mx, my, mz = lv["nema17_mm"]
    u_m0 = hu / 2 + lv["coupling_len_mm"]
    vm = lv["motor_offset_v_mm"] * (1.0 if sp["x"] >= 0 else -1.0)   # décalage radial vers le cadre (jeu >= 3 mm avec le caisson)
    motor = _box(u_m0, u_m0 + mz, -mx / 2 + vm, mx / 2 + vm, z0, z0 + my)
    knob = _cyl_u(u_m0 + mz, u_m0 + mz + lv["knob_t_mm"], vm, z0 + w_ax, lv["knob_d_mm"])
    # motorisation vers le coin de cadre le plus proche : u local -> -y global
    ang = -90.0
    pl = lambda s: _place(s, sp["x"], sp["y"], ang)
    out = [
        PartSpec(f"verin_boitier_{i}", pl(housing), COLORS["verin"], "acier", "appuis", formats=("step",),
                 note="boîtier 90 x 30 x 45 (tête à mi-course), cavité du coin ; lames flexibles non modélisées"),
        PartSpec(f"verin_coin_{i}", pl(wedge), COLORS["verin"], "acier", "appuis", formats=("step",),
                 note="coin 60 x 24, pente 1:5, course +/- 12,1 (cage à aiguilles non modélisée)"),
        PartSpec(f"verin_tete_{i}", pl(head), COLORS["verin"], "acier", "appuis", formats=("step",),
                 note="tête guidée verticalement, course +/- 2,43"),
        PartSpec(f"verin_vis_{i}", pl(screw), COLORS["acier"], "acier", "appuis", note="vis M6 x 0,25"),
        PartSpec(f"verin_accouplement_{i}", pl(cpl), COLORS["acier"], "acier", "appuis", note="accouplement"),
        PartSpec(f"verin_moteur_{i}", pl(motor), COLORS["moteur"], "acier", "appuis", mass_kg=lv["nema17_mass_kg"],
                 commercial=True, note="NEMA17 200 pas/tr double arbre (enveloppe 42 x 42 x 40)"),
        PartSpec(f"verin_bouton_{i}", pl(knob), COLORS["pied"], "alu", "appuis", formats=("step",),
                 note="bouton gradué Ø40, 100 divisions"),
    ]
    return out


def pivot_part(P: dict, sp: dict, L: dict) -> PartSpec:
    bl, bw, _ = P["support"]["vee_block_mm"]
    blk = _box(-bl / 2, bl / 2, -bw / 2, bw / 2, L["cad_top"], L["block_base"])
    return PartSpec(f"pivot_rehausse_{sp['index']}", _place(blk, sp["x"], sp["y"], sp["vee_angle"]),
                    COLORS["verin"], "acier", "appuis", formats=("step",),
                    note="rehausse fixe de P0 (même hauteur que le vérin à mi-course)")


# -----------------------------------------------------------------------------
#  Étrier anti-soulèvement (patin PTFE à 0,5 mm au-dessus de la plaque)
# -----------------------------------------------------------------------------
def clamp_parts(P: dict, sp: dict, L: dict) -> list[PartSpec]:
    S = P["support"]
    half = P["plate"]["outer_square_mm"] / 2.0
    pd, pt, at = S["clamp_pad_d_mm"], S["clamp_pad_t_mm"], S["clamp_arm_t_mm"]
    pr, pw = S["clamp_post_mm"]
    gap = P.get("support", {}).get("antilift_gap_mm", 0.5)
    # direction radiale sortante n (selon y pour P0, selon x pour P1/P2) ; v = n tourné de +90 deg
    n = (0.0, math.copysign(1.0, sp["y"])) if abs(sp["y"]) >= abs(sp["x"]) else (math.copysign(1.0, sp["x"]), 0.0)
    v_axis = (-n[1], n[0])
    r_pad = sp["x"] * n[0] + sp["y"] * n[1]
    v0 = sp["x"] * v_axis[0] + sp["y"] * v_axis[1]
    ang = math.degrees(math.atan2(n[1], n[0]))
    z_arm0 = gap + pt
    z_top = z_arm0 + at
    r0, r1 = half + 3.0, half + 3.0 + pr
    # montant décalé latéralement de 40 mm (côté +y pour P1/P2) pour éviter le bloc de vé
    sgn = 1.0 if v_axis[1] > 0 or (v_axis[1] == 0 and v_axis[0] <= 0) else -1.0
    vp = v0 + sgn * 40.0
    post = _box(r0, r1, vp - pw / 2, vp + pw / 2, L["cad_top"], z_top)
    va, vb = sorted((v0 - pd / 2 - 3.0, vp + sgn * pw / 2))
    bar1 = _box(r_pad - pd / 2 - 3.0, r_pad + pd / 2 + 3.0, va, vb, z_arm0, z_top)
    bar2 = _box(r_pad, r1, vp - pw / 2, vp + pw / 2, z_arm0, z_top)
    arm = bar1.union(bar2)
    pad = cq.Workplane("XY").workplane(offset=gap).center(r_pad, v0).circle(pd / 2).extrude(pt)
    rot = lambda s: s.rotate((0, 0, 0), (0, 0, 1), ang)
    i = sp["index"]
    return [
        PartSpec(f"etrier_{i}", rot(post.union(arm)), COLORS["pied"], "acier", "appuis", formats=("step",),
                 note="étrier anti-soulèvement sur le cadre, jeu 0,5 mm"),
        PartSpec(f"etrier_patin_{i}", rot(pad), COLORS["filtre"], "ptfe", "appuis", commercial=True,
                 note="patin PTFE Ø10 à 0,5 mm au-dessus de la face supérieure"),
    ]


# -----------------------------------------------------------------------------
#  Embase isotherme ADXL355 (socle + 3 pieds, plateau rotatif Ø50 sur 3 billes / 6 vés, capot XPS)
# -----------------------------------------------------------------------------
def adxl_parts(P: dict, k: int, cx: float, cy: float) -> list[PartSpec]:
    T = P["tilt_sensors"]
    bx, by, bz = P["tilt_sensors"]["base_block_mm"]
    fv = T["foot_visible_mm"]
    rb, ballr = T["ball_r_mm"], T["ball_d_mm"] / 2.0
    out = []
    z_soc0, z_soc1 = fv, fv + bz
    soc = _box(-bx / 2, bx / 2, -by / 2, by / 2, z_soc0, z_soc1)
    # 6 vés radiaux à 60 deg (demi-angle 45, profondeur 1,5, longueur 8) sur R18
    depth = 1.5
    for a in range(6):
        # prisme triangulaire (apex vers le bas) le long de la direction radiale
        poly = [(-(depth + 1.0), z_soc1 + 1.0), ((depth + 1.0), z_soc1 + 1.0), (0, z_soc1 - depth)]
        v = cq.Workplane("XZ").polyline(poly).close().extrude(4.0, both=True)   # largeur le long de Y (=8 mm)
        v = v.rotate((0, 0, 0), (0, 0, 1), -90.0).translate((rb, 0, 0))             # groove le long de x, centré sur R18
        v = v.rotate((0, 0, 0), (0, 0, 1), a * 60.0)
        soc = soc.cut(v)
    feet = [cq.Solid.makeCylinder(T["foot_d_mm"] / 2.0, fv, cq.Vector(20 * math.cos(math.radians(90 + 120 * j)),
                                                                        20 * math.sin(math.radians(90 + 120 * j)), 0),
                                  cq.Vector(0, 0, 1)) for j in range(3)]
    soc = soc.union(cq.Workplane("XY").newObject([cq.Compound.makeCompound(feet)]))
    z_ball = z_soc1 - depth + ballr / math.sin(math.radians(45))
    z_plat0 = z_ball + ballr
    plat = cq.Workplane("XY").workplane(offset=z_plat0).circle(T["plateau_d_mm"] / 2.0).extrude(T["plateau_t_mm"])
    balls = [cq.Solid.makeSphere(ballr, cq.Vector(rb * math.cos(math.radians(90 + 120 * j)),
                                                  rb * math.sin(math.radians(90 + 120 * j)), z_ball))
             for j in range(3)]
    pcbx, pcby, pcbz = T["pcb_mm"]
    z_pcb = z_plat0 + T["plateau_t_mm"]
    pcb = _box(-pcbx / 2, pcbx / 2, -pcby / 2, pcby / 2, z_pcb, z_pcb + pcbz)
    cw, cd, ch = T["capot_mm"]
    capot = _box(-cw / 2, cw / 2, -cd / 2, cd / 2, 0, ch).cut(
        _box(-bx / 2 - 0.2, bx / 2 + 0.2, -by / 2 - 0.2, by / 2 + 0.2, -1, ch - T["capot_top_mm"]))
    mv = lambda s: s.translate((cx, cy, 0))
    p = f"adxl_{k}"
    out.append(PartSpec(f"{p}_socle", mv(soc), COLORS["platine"], "alu", "capteurs", formats=("step",),
                        note="socle isotherme 60 x 60 x 20, 3 pieds Ø8 (M4 dans la plaque), 6 vés à 60 deg"))
    out.append(PartSpec(f"{p}_plateau", mv(plat), COLORS["platine"], "alu", "capteurs", formats=("step",),
                        note="plateau Ø50 rotatif (retournement 180 deg)"))
    out.append(PartSpec(f"{p}_billes", mv(cq.Workplane("XY").newObject([cq.Compound.makeCompound(balls)])),
                        COLORS["acier"], "acier", "capteurs", commercial=True, note="3 billes Ø4 sur R18"))
    out.append(PartSpec(f"{p}_carte", mv(pcb), COLORS["moteur"], "composite", "capteurs", mass_kg=0.01,
                        commercial=True, note="carte ADXL355 + TMP117 (enveloppe)"))
    out.append(PartSpec(f"{p}_capot", mv(capot), COLORS["ecran"], "xps", "capteurs", formats=("step",),
                        note="capot XPS 80 x 80 x 45, parois 10"))
    return out


def build(P: dict) -> list[PartSpec]:
    L = levels(P)
    parts: list[PartSpec] = []
    for sp in support_points(P):
        parts += vee_parts(P, sp, L)
        parts += jack_parts(P, sp, L) if sp["role"] == "verin" else [pivot_part(P, sp, L)]
        parts += clamp_parts(P, sp, L)
    for k, (cx, cy) in enumerate(P["tilt_sensors"]["positions_mm"], 1):
        parts += adxl_parts(P, k, cx, cy)
    return parts
