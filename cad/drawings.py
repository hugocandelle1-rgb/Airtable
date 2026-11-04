"""Mises en plan 2D cotées des pièces sous-traitées (SVG + PDF dans cad/export/plans/).

Chaque fonction reçoit les paramètres P (get_params) et retourne la liste des fichiers écrits.
Les valeurs de tolérance de planéité sont lues dans params/design.toml (performance_targets) : elles
peuvent encore se resserrer, le plan les suit automatiquement.
"""
from __future__ import annotations

import math
from pathlib import Path

import cadquery as cq

from cad.common import EXPORT_DIR, levels, support_points, vee_geometry
from cad.drafting import Sheet, fmt
from cad.parts import aero as aero_mod
from cad.parts import leveling as lev_mod
from cad.parts import plate as plate_mod
from cad.parts import plenum as plenum_mod

PLANS = EXPORT_DIR / "plans"
TOL_GEN = "ISO 2768-mK"


def _half(shape: cq.Workplane, keep: str = "y+") -> cq.Workplane:
    """Coupe par le plan y = 0 en gardant y >= 0 (à regarder depuis -Y)."""
    box = cq.Workplane("XY").box(4000, 2000, 4000, centered=(True, False, True)).translate((0, -2000, 0))
    return shape.cut(box)


def _mass(P: dict, names: list[str], parts) -> float:
    return sum(p.mass(P) for p in parts if p.name in names)


# -----------------------------------------------------------------------------------------------------------
#  1. Plaque de travail (A2)
# -----------------------------------------------------------------------------------------------------------
def plan_plaque(P: dict, m_full_kg: float | None = None, png: bool = False) -> list[str]:
    pl = P["plate"]
    pt = P["performance_targets"]
    t = pl["thickness_mm"]
    flat = pt["plate_flatness_um"] / 1000.0
    flat_loc = pt["plate_local_flatness_um"] / 1000.0
    shape = plate_mod.build_plate(P, "light")
    s = Sheet("A2", "Plaque de travail perforée", "TAB-PLQ-001", "EN AW-5083 coulée détensionnée", m_full_kg,
              "1:2,4 ; 16:1", TOL_GEN, "Plaque 520 x 520 x 35, 5935 orifices Ø0,30",
              rugosite="Ra 0,4 (face A) ; 1,6 (autres)")
    sc = 0.42
    c1, c2 = (150, 285), (435, 285)
    vd = s.view(shape, "dessus", c1, sc)
    vu = s.view(shape, "dessous", c2, sc)
    s.label((c1[0], 158), "VUE DE DESSUS (face A)")
    s.label((c2[0], 158), "VUE DE DESSOUS (image miroir en y)")
    zone = P["zones"]["perforated_square_mm"] / 2
    work = P["zones"]["working_square_mm"] / 2
    for v in (vd, vu):
        for h, ls in ((zone, (0, (6, 2))), (work, (0, (2, 2)))):
            v.line((-h, -h), (h, -h), 0.18, ls)
            v.line((h, -h), (h, h), 0.18, ls)
            v.line((h, h), (-h, h), 0.18, ls)
            v.line((-h, h), (-h, -h), 0.18, ls)
        v.line((-270, 0), (270, 0), 0.13, (0, (8, 1.5, 1.5, 1.5)))
        v.line((0, -270), (0, 270), 0.13, (0, (8, 1.5, 1.5, 1.5)))
        v.dim_x((-260, -260), (260, -260), -8, "520")
        v.dim_y((260, -260), (260, 260), -10, "520")
    vd.note((-60, -180), "zone percée 360 x 360 : 5935 trous, maille hex. pas 5,00 (rangées // x)", 14, -14)
    vd.note((work * 0.55, work), "zone de travail 300 x 300", 14, 22)
    # embases ADXL (face supérieure) : 3 x M4 sur Ø40
    for cx, cy in P["tilt_sensors"]["positions_mm"]:
        vd.circle((cx, cy), pl["adxl_pcd_mm"] / 2, 0.18, (0, (4, 1.5)))
        for hx, hy in [(x, y) for x, y in plate_mod.adxl_positions(P) if abs(x - cx) < 25 and abs(y - cy) < 25]:
            pass
    vd.dim_x((0, 240), (220, 240), 6, "220")
    vd.dim_y((240, 0), (240, 220), -8, "220")
    vd.dia((220, 220), 20, 15, "3 x M4 ↧8 / Ø40", 14)
    vd.note((-240, 0), "B : alésage Ø6 H7 débouchant", 12, 24)
    vd.note((240, 0), "C : lumière 6 H7 x 10 (grand axe // x)", -14, -26)
    vd.dim_x((-260, 0), (-240, 0), 8, "20")
    vd.dim_x((240, 0), (260, 0), 8, "20")
    s.gdt((30, 146), [("flat", None), fmt(flat, 4), "360 x 360"])
    s.gdt((30, 138), [("flat", None), fmt(flat_loc, 5), "/ 100 x 100"])
    s.text((30, 133), "(face A ; valeurs lues dans params/design.toml)", size=2.2)
    # repère A sur la face supérieure (vue de dessus : flèche sur le bord bas)
    s.datum(vd.P(0, -260), "A", (0, -1))
    # --- dessous : appuis, taraudages, manutention --------------------------------------------------------------
    for sp in support_points(P):
        x, y = sp["x"], -sp["y"]
        vu.centerlines((x, y), pl["ball_pocket_d_mm"] / 2, 4)
    vu.dia((0, -242.5), 12.7, 20, "3 x Ø25,4 H8 ↧10,7", 12)
    s.gdt(vu.P(60, -200), [("pos", None), "Ø0,2", "B", "C"])
    vu.dim_y((0, 0), (0, -242.5), 12, "242,5")
    vu.dim_x((0, -242.5), (242.5, -242.5), -8, "242,5")
    vu.dim_y((242.5, 0), (242.5, 145.5), -16, "145,5")
    vu.dia((-182, -208), 2.1, 150, "32 x M5 ↧10 (Ø4,2) carré 2 x 208", 22)
    vu.dim_x((-182, -208), (-130, -208), -14, "52")
    vu.note((-260, 100), "4 x M10 ↧20 sur chants (x décalés à y = -100)", 16, 22)
    s.datum(vu.P(-240, 0), "B", (-1, 0))
    s.datum(vu.P(240, 0), "C", (1, 0))
    # --- coupe A-A ---------------------------------------------------------------------------------------------------------
    cut = _half(shape)
    s.label((215, 148), "COUPE A-A (plan y = 0)")
    vc = s.view(cut, "face", (215, 118), 0.7)
    vc.dim_x((-260, -t), (260, -t), -8, "520")
    vc.dim_y((260, -t), (260, 0), -8, "35")
    vc.note((259.5, -0.5), "chanfrein 1 x 45°", -10, 10)
    s.datum(vc.P(120, 0), "A", (0, 1))
    # --- détail de l'orifice (20:1) ------------------------------------------------------------------------------------------
    sd = 16.0
    ox, oy = 470.0, 124.0                                  # face supérieure au centre de l'orifice
    r2, r1, v = pl["orifice_d_mm"] / 2, pl["counterbore_d_mm"] / 2, pl["orifice_length_mm"]
    k = 1.0 / math.tan(math.radians(pl["cone_angle_deg"] / 2))
    X = lambda x, z: (ox + x * sd, oy + z * sd)
    s.label((ox, 148), "DÉTAIL B (16:1) : orifice")
    for sg in (-1, 1):
        s.line(X(sg * r1 * 1.2, 0), X(sg * r2, 0), 0.35)
        s.line(X(sg * r2, 0), X(sg * r2, -v - r2 * k), 0.35)
        s.line(X(sg * r2, -v - r2 * k), X(sg * r1, -v - r1 * k), 0.35)
        s.line(X(sg * r1, -v - r1 * k), X(sg * r1, -v - r1 * k - 0.7), 0.35)
        s.line(X(sg * r1 * 1.2, 0), X(sg * r1 * 1.2, -v - r1 * k - 0.7), 0.15, (0, (2, 2)))
    s.cline(X(0, 0.4), X(0, -v - r1 * k - 0.9))
    s.dim_lin(X(-r2, 0), X(r2, 0), 8, "Ø0,30 ±0,005")
    s.dim_lin(X(r1 * 1.2, 0), X(r1 * 1.2, -v), 6, "1,20 ±0,05")
    s.dim_lin(X(-r1, -v - r1 * k - 0.4), X(r1, -v - r1 * k - 0.4), -6, "Ø2,0 H11")
    s.text(X(r1 + 0.3, -v - r1 * k - 0.25), "118°", size=2.6)
    s.gdt((420, 80), [("pos", None), "Ø0,05", "A", "B", "C"])
    s.text((420, 75), "orifices ; lamages ⊕ Ø0,2 | A | B | C", size=2.2)
    s.text((420, 71.5), "arête de sortie vive, sans bavure (ISO 13715 : -0,02/0)", size=2.2)
    # --- notes -----------------------------------------------------------------------------------------------------------------
    s.block((30, 92), [
        "1. Matière : EN AW-5083 coulée, détensionnée ; face A = zone de travail 300 x 300 (référence primaire).",
        f"2. Planéité face A : {fmt(flat, 4)} sur 360 x 360, {fmt(flat_loc, 5)} sur tout carré 100 x 100 ; pente locale (base 50) <= 30 µrad.",
        "3. Orifices Ø0,30 ±0,005, voile 1,20 ±0,05 ; lamage Ø2,0 H11 depuis la face inférieure, fond conique 118°, ép. - 1,2.",
        "4. Position des orifices ⊕ Ø0,05 | A | B | C ; pas cumulé ±0,1 sur 360 ; 5935 trous (liste : plaque_centres_trous.csv, plaque_trous.dxf).",
        "5. Références : A face supérieure ; B alésage Ø6 H7 en (-240 ; 0) ; C lumière 6 H7 x 10 en (+240 ; 0).",
        "6. Sièges de billes Ø25,4 H8 ↧10,7 en (0 ; 242,5), (242,5 ; -145,5), (-242,5 ; -145,5), ⊕ Ø0,2 | B | C ; bille Ø25,4 G10 collée.",
        "7. Attache du caisson : 32 x M5 ↧10 de bas en haut, carré de demi-côté 208 ; embases ADXL355 : 4 x 3 x M4 ↧8 sur Ø40.",
        "8. Manutention 4 x M10 ↧20 : les deux de l'axe x décalés à y = -100 (conflit avec B/C à arbitrer).",
        "9. Chanfreins 1 x 45° ; ébavurer ; protéger la face A. Ra face A 0,4 (diamant < 0,1), face inférieure Ra 1,6.",
    ], title="NOTES", size=2.5, lead=3.8)
    return s.save(PLANS / "plan_plaque", png)


# -----------------------------------------------------------------------------------------------------------
#  2. Appui en vé : bloc + 2 rouleaux Ø20 + bille Ø25,4 (A3, 2,5:1)
# -----------------------------------------------------------------------------------------------------------
def plan_vee(P: dict, png: bool = False) -> list[str]:
    L = levels(P)
    S = P["support"]
    V = vee_geometry(P)
    hs = V["half_spacing"]
    sp = {"index": 9, "x": 0.0, "y": 0.0, "vee_angle": 0.0, "role": "verin"}
    vp = lev_mod.vee_parts(P, sp, L)
    ball = cq.Workplane("XY").sphere(S["ball_d_mm"] / 2).translate((0, 0, L["ball_zc"]))
    comp = cq.Workplane("XY").newObject([cq.Compound.makeCompound([p.shape.val() for p in vp] + [ball.val()])])
    mass = sum(p.mass(P) for p in vp) + 4 / 3 * math.pi * (S["ball_d_mm"] / 2) ** 3 * 7.85e-6
    bl, bw, bh = S["vee_block_mm"]
    zb, zr, zc = L["block_base"], L["roller_z"], L["ball_zc"]
    s = Sheet("A3", "Appui en vé (bloc + 2 rouleaux + bille)", "TAB-APP-VEE", "Acier trempé (à confirmer)",
              mass, "2:1", TOL_GEN, "Bille Ø25,4 sur 2 rouleaux Ø20, vé à 90° (appuis Maxwell)",
              rugosite="Ra 0,8 (portées) ; Ra 3,2 sinon")
    sc = 2.0
    vr = s.view(comp, "droite", (100, 205), sc)
    vf = s.view(comp, "face", (240, 205), sc)
    vd = s.view(comp, "dessus", (345, 205), sc)
    s.label((100, 268), "VUE DE BOUT (profil du vé)")
    s.label((240, 268), "VUE DE FACE")
    s.label((345, 268), "VUE DE DESSUS")
    # profil
    vr.dim_x((-bw / 2, zb), (bw / 2, zb), -8, fmt(bw))
    vr.dim_x((-hs, zr), (hs, zr), -34, fmt(2 * hs, 1) + " ±0,01 (entraxe)")
    vr.dim_y((-hs - 10, zb), (-hs - 10, zr), 6, "12")
    vr.dim_y((bw / 2, zb), (bw / 2, zb + bh), -8, fmt(bh))
    vr.dim_y((hs + 10, zr), (hs + 10, zc), -10, fmt(V["dz"], 2) + " (centre bille)")
    vr.dia((hs, zr), S["roller_d_mm"] / 2, -30, "2 x Ø20 h6", 10)
    vr.dia((0, zc), S["ball_d_mm"] / 2, 60, "bille Ø25,4 G10", 12)
    vr.line((0, zb - 4), (0, zc + 16), 0.13, (0, (8, 1.5, 1.5, 1.5)))
    s.text(vr.P(-hs - 30, zc + 16), "vé à 90° (contacts à 45°)", size=2.8)
    # face
    vf.dim_x((-bl / 2, zb), (bl / 2, zb), -8, fmt(bl))
    vf.dim_x((-S["roller_len_mm"] / 2, zr + S["roller_d_mm"] / 2), (S["roller_len_mm"] / 2, zr + S["roller_d_mm"] / 2), 14,
             fmt(S["roller_len_mm"]) + " h6")
    vf.dim_y((bl / 2, zr), (bl / 2, zc), -8, fmt(V["dz"], 2))
    # dessus
    vd.dim_x((-bl / 2, -bw / 2), (bl / 2, -bw / 2), -8, fmt(bl))
    vd.dim_y((-bl / 2, -bw / 2), (-bl / 2, bw / 2), 8, fmt(bw))
    vd.dim_y((S["roller_len_mm"] / 2, -hs), (S["roller_len_mm"] / 2, hs), -10, fmt(2 * hs, 1))
    s.block((30, 118), [
        "1. Bloc 40 x 30 x 20 : sièges cylindriques usinés pour les rouleaux ; creux central dégageant la bille.",
        "2. Rouleaux Ø20 x 30 h6 trempés, axes parallèles à l'axe du vé ; entraxe 32,1 ; axes à 12 de la base du bloc.",
        "3. Centre de bille à 16,05 au-dessus des axes ; bille Ø25,4 G10 collée dans la plaque (siège Ø25,4 H8 ↧10,7).",
        "4. Axes de vé (depuis +x) : P0 -90°, P1 151,9°, P2 28,1° (vers le barycentre (0 ; -16,2)).",
        "5. P0 : bloc posé sur une rehausse fixe de 45 ; P1, P2 : bloc posé sur la tête du vérin à coin.",
        "6. Parallélisme des axes de rouleaux / axe du vé et rectitude des sièges : à spécifier avec la note 03 (valeurs à valider).",
    ], title="NOTES", size=2.5, lead=3.8)
    return s.save(PLANS / "plan_vee", png)


# -----------------------------------------------------------------------------------------------------------
#  3. Vérin à coin (A3, 2:1)
# -----------------------------------------------------------------------------------------------------------
def plan_verin(P: dict, png: bool = False) -> list[str]:
    L = levels(P)
    lv = P["leveling"]
    sp = {"index": 9, "x": 0.0, "y": 0.0, "vee_angle": 0.0, "role": "verin"}
    jp = lev_mod.jack_parts(P, sp, L)
    shapes = [p.shape.rotate((0, 0, 0), (0, 0, 1), 90.0) for p in jp]      # axe de vis selon +x
    comp = cq.Workplane("XY").newObject([cq.Compound.makeCompound([q.val() for q in shapes])])
    mass = sum(p.mass(P) for p in jp)
    z0, H = L["cad_top"], L["stack_h"]
    hu, hv = lv["housing_mm"]
    wl, ww = lv["wedge_mm"]
    mx, my, mz = lv["nema17_mm"]
    u_m0 = hu / 2 + lv["coupling_len_mm"]
    vm = lv["motor_offset_v_mm"]
    s = Sheet("A3", "Vérin à coin 1:5 (P1, P2)", "TAB-NIV-VERIN", "Acier ; NEMA17 du commerce", mass, "2:1",
              TOL_GEN, "Course verticale ±2,43 mm, vis M6 x 0,25, 0,64 µrad/pas moteur",
              rugosite="Ra 0,8 (coin, tête) ; Ra 3,2 sinon")
    sc = 2.0
    vd = s.view(comp, "dessus", (190, 232), sc)
    cut = _half(comp)
    vc = s.view(cut, "face", (190, 128), sc)
    s.label((190, 276), "VUE DE DESSUS (axe de vis selon x)")
    s.label((190, 180), "COUPE LONGITUDINALE (plan y = 0)")
    vd.dim_x((-hu / 2, -hv / 2), (hu / 2, -hv / 2), -8, fmt(hu))
    vd.dim_y((-hu / 2, -hv / 2), (-hu / 2, hv / 2), 10, fmt(hv))
    vd.dim_x((u_m0, my / 2 + vm), (u_m0 + mz, my / 2 + vm), 8, fmt(mz) + " (NEMA17)")
    vd.dim_y((u_m0 + mz, -my / 2 + vm), (u_m0 + mz, my / 2 + vm), -22, fmt(my) + " (décalé de " + fmt(vm) + ")")
    vd.dim_x((u_m0 + mz, -lv["knob_d_mm"] / 2 + vm), (u_m0 + mz + lv["knob_t_mm"], -lv["knob_d_mm"] / 2 + vm), -8, fmt(lv["knob_t_mm"]))
    vd.dia((u_m0 + mz + lv["knob_t_mm"] / 2, vm), lv["knob_d_mm"] / 2, -60, "bouton Ø40, 100 div.", 14)
    vd.dim_x((hu / 2, 0), (u_m0, 0), 8 + 12, fmt(lv["coupling_len_mm"]) + " (accoupl.)")
    # coupe
    vc.dim_y((-hu / 2, z0), (-hu / 2, z0 + H), 10, "45 (" + fmt(H) + ")")
    vc.dim_y((u_m0, z0), (u_m0, z0 + my), -14, fmt(my))
    vc.dim_y((-wl / 2 - 2, z0 + lv["wedge_floor_mm"]), (-wl / 2 - 2, z0 + 24.0), 8, "24 (coin, extrémité mince)")
    vc.dim_y((hu / 2, z0), (hu / 2, z0 + my / 2), -8, "21 (axe de vis)")
    vc.dim_x((-wl / 2, z0 - 3), (wl / 2, z0 - 3), -4, fmt(wl) + " (coin)")
    vc.note((12, z0 + 31.5), "coin 1:5", 8, 12)
    vc.note((-30, z0 + 38), "tête (±2,43)", -6, 8)
    vc.note((hu / 2 - 2, z0 + 21), "vis M6 x 0,25", 8, -14)
    s.block((30, 70), [
        "1. Boîtier 90 x 30 x 45 (tête à mi-course), posé sur le cadre ; moteur en bout, posé sur le cadre.",
        "2. Coin 60 x 24, pente 1:5 (tan = 0,2), course ±12,1 mm -> tête ±2,43 mm ; cage à aiguilles entre coin et tête.",
        "3. Tête guidée en translation verticale par 2 lames flexibles 0,3 x 20 x 30 (non modélisées).",
        "4. NEMA17 200 pas/tr double arbre (42 x 42 x 40) : arbre avant -> accouplement -> vis ; arbre arrière -> bouton gradué Ø40.",
        f"5. Moteur et bouton décalés de {fmt(vm)} mm vers le cadre (jeu >= 3 mm avec le caisson) : accouplement type Oldham.",
        "6. Planéité des portées coin/tête et jeu de glissement : à spécifier (valeurs à valider, note 05).",
    ], title="NOTES", size=2.5, lead=3.8)
    return s.save(PLANS / "plan_verin", png)


# -----------------------------------------------------------------------------------------------------------
#  4. Embase isotherme ADXL355 (A3, 2:1)
# -----------------------------------------------------------------------------------------------------------
def plan_adxl(P: dict, png: bool = False) -> list[str]:
    T = P["tilt_sensors"]
    ap = lev_mod.adxl_parts(P, 9, 0.0, 0.0)
    byn = {p.name.split("_", 2)[2]: p for p in ap}
    comp = cq.Workplane("XY").newObject([cq.Compound.makeCompound([p.shape.val() for p in ap])])
    nocap = cq.Workplane("XY").newObject([cq.Compound.makeCompound([p.shape.val() for p in ap if "capot" not in p.name])])
    mass = sum(p.mass(P) for p in ap)
    bx, by, bz = T["base_block_mm"]
    cw, cd, ch = T["capot_mm"]
    z = {k: (v.bbox()[2], v.bbox()[5]) for k, v in byn.items()}
    s = Sheet("A3", "Embase isotherme ADXL355", "TAB-CAP-ADXL", "Alliage d'alu (socle, plateau) ; capot XPS",
              mass, "2:1", TOL_GEN, "4 embases en (±220 ; ±220) ; plateau rotatif Ø50 : retournement 180° (3 billes / 6 vés)",
              rugosite="Ra 0,8 (vés, plateau) ; Ra 3,2 sinon")
    sc = 2.0
    vd = s.view(nocap, "dessus", (105, 190), sc)
    vd.circle((0, 0), cw / 2, 0.18, (0, (4, 1.5)))
    cut = _half(comp)
    vc = s.view(cut, "face", (290, 215), sc)
    s.label((105, 262), "VUE DE DESSUS (capot retiré ; capot en traits mixtes)")
    s.label((290, 262), "COUPE (plan y = 0)")
    vd.dim_x((-bx / 2, -by / 2), (bx / 2, -by / 2), -8, fmt(bx))
    vd.dim_y((-bx / 2, -by / 2), (-bx / 2, by / 2), 8, fmt(by))
    vd.dim_x((-cw / 2, cd / 2), (cw / 2, cd / 2), 8, fmt(cw) + " (capot)")
    vd.dia((0, 0), T["plateau_d_mm"] / 2, 200, "plateau Ø50", 12)
    vd.dia((0, T["ball_r_mm"]), T["ball_d_mm"] / 2, 60, "3 x Ø4 sur R18 (120°)", 14)
    for a in range(6):
        ang = math.radians(a * 60)
        vd.line((10 * math.cos(ang), 10 * math.sin(ang)), (23 * math.cos(ang), 23 * math.sin(ang)), 0.13, (0, (2, 2)))
    s.text((30, 126), "6 vés radiaux à 60° (R18) : traits pointillés dans la vue de dessus", size=2.4)
    vc.dim_y((-cw / 2, 0), (-cw / 2, ch), 8, fmt(ch))
    vc.dim_y((cw / 2, 0), (cw / 2, ch - T["capot_top_mm"]), -8, fmt(ch - T["capot_top_mm"]) + " (cavité)")
    vc.dim_y((cw / 2, ch - T["capot_top_mm"]), (cw / 2, ch), -20, fmt(T["capot_top_mm"]))
    vc.dim_x((-cw / 2, ch), (-bx / 2 - 0.2, ch), 6, fmt(T["capot_wall_mm"]))
    vc.dim_y((bx / 2, z["socle"][0] + 0.0), (bx / 2, z["socle"][1]), -14, fmt(bz) + " (socle)")
    vc.dim_y((-bx / 2 + 6, 0), (-bx / 2 + 6, T["foot_visible_mm"]), 20, fmt(T["foot_visible_mm"]) + " (pieds)")
    vc.dim_y((T["plateau_d_mm"] / 2, z["plateau"][0]), (T["plateau_d_mm"] / 2, z["plateau"][1]), -26, fmt(T["plateau_t_mm"]) + " (plateau)")
    vc.dia((0, z["socle"][1]), 0.1, 130, "billes Ø4 dans les vés", 20)
    vc.note((8, z["carte"][1]), "carte ADXL355 + TMP117 20 x 20", 22, 20)
    s.block((30, 118), [
        "1. Capot XPS 80 x 80 x 45, parois 10, plafond 8 : posé sur la plaque, sans contact avec le socle (jeu 0,2).",
        "2. Socle 60 x 60 x 20 sur 3 pieds Ø8 x 12 (8 dans la plaque : M4 sur Ø40 à 120°, un trou vers l'extérieur).",
        "3. Plateau Ø50 x 6 sur 3 billes Ø4 (R18) dans 3 des 6 vés à 60° : indexation à 0° / 180°.",
        "4. Alignement des vés et planéité du socle : valeurs à spécifier avec la note 05 (non chiffrées).",
        "5. Pièces usinées : socle et plateau (alliage d'aluminium isotherme) ; capot XPS découpé.",
    ], title="NOTES", size=2.5, lead=3.8)
    return s.save(PLANS / "plan_adxl", png)


# -----------------------------------------------------------------------------------------------------------
#  5. Caisson de plenum + joint + cornière (A2, 1:2)
# -----------------------------------------------------------------------------------------------------------
def plan_caisson(P: dict, parts: list | None = None, png: bool = False) -> list[str]:
    pn = P["plenum"]
    L = levels(P)
    pp = plenum_mod.build(P)
    by = {p.name: p for p in pp}
    mass = by["caisson"].mass(P) + by["joint_plat"].mass(P) + by["corniere_caisson"].mass(P)
    ho, hi = L["box_half"], L["cav_half"]
    s = Sheet("A2", "Caisson de plenum suspendu à la plaque", "TAB-PLN-001", "Tôle alu 6 mm soudée (à confirmer)",
              mass, "1:2 ; 5:1", TOL_GEN, "Caisson 430 x 430 x 150 int., parois et fond 6, joint EPDM 6 x 2, cornière 15 x 15 x 3",
              rugosite="Ra 3,2 ; appui joint Ra 1,6")
    sc = 0.5
    box = by["caisson"].shape
    vd = s.view(box, "dessus", (150, 285), sc)
    s.label((150, 172), "VUE DE DESSUS")
    vd.dim_x((-ho, -ho), (ho, -ho), -8, fmt(2 * ho))
    vd.dim_x((-hi, hi), (hi, hi), 4, fmt(2 * hi) + " (intérieur)")
    vd.dim_y((ho, -ho), (ho, ho), -8, fmt(2 * ho))
    vd.dia((0, 0), pn["inlet_d_mm"] / 2, 45, "entrée Ø80 (fond)", 14)
    vd.note((hi, -hi), "dégagements locaux de paroi (vés P1, P2)", -4, -22)
    # coupe y = 0 avec l'intérieur
    keep = ["caisson", "joint_plat", "corniere_caisson", "tole_distribution", "nappe_media", "deflecteur", "deflecteur_plots"]
    comp = cq.Workplane("XY").newObject([cq.Compound.makeCompound([by[k].shape.val() for k in keep])])
    cut = _half(comp)
    s.label((150, 142), "COUPE A-A (plan y = 0)")
    vc = s.view(cut, "face", (150, 108), sc)
    vc.dim_y((ho, L["box_bot"]), (ho, L["wall_top"]), -10, fmt(L["wall_top"] - L["box_bot"]) + " (hors tout)")
    vc.dim_y((-ho, L["floor_top"]), (-ho, L["plate_bot"]), 10, fmt(pn["height_mm"]) + " (intérieur)")
    vc.dim_y((-ho, L["floor_top"]), (-ho, L["baffle_bot"]), 22, fmt(pn["distribution_height_mm"]) + " (distribution)")
    vc.dim_y((ho, L["box_bot"]), (ho, L["floor_top"]), -22, fmt(pn["bottom_mm"]) + " (fond)")
    vc.dim_x((-pn["inlet_d_mm"] / 2, L["box_bot"]), (pn["inlet_d_mm"] / 2, L["box_bot"]), -8, "Ø" + fmt(pn["inlet_d_mm"]))
    vc.note((-hi + 4, L["tap_z"]), "4 piquages Ø4 (milieu des parois, chambre de tranquillisation)", 20, -14)
    vc.note((0, L["deflector_bot"] + 1), "déflecteur Ø200 à 25 du fond", 40, -16)
    vc.note((60, L["baffle_top"]), "tôle inox ép. 1 (Ø2, pas 8) + média 10", 30, 16)
    # détail C : angle paroi / joint / cornière / plaque (5:1)
    x0, x1 = 192.0, 236.0
    reg = cq.Workplane("XY").box(x1 - x0, 40, 36, centered=False).translate((x0, 0, L["plate_bot"] - 30))
    plate_sl = plate_mod.plate_blank(P).intersect(reg)
    det = [by["caisson"].shape.intersect(reg), by["joint_plat"].shape.intersect(reg),
           by["corniere_caisson"].shape.intersect(reg), plate_sl]
    dcomp = cq.Workplane("XY").newObject([cq.Compound.makeCompound([d.val() for d in det])])
    s.label((470, 402), "DÉTAIL C (5:1) : attache à la plaque")
    vC = s.view(dcomp, "face", (470, 300), 5.0)
    zp = L["plate_bot"]
    gk_w, gk_t = pn["gasket_mm"]
    leg, te = pn["angle_mm"]
    vC.dim_x((hi, L["wall_top"] - 2), (ho, L["wall_top"] - 2), -10, fmt(pn["wall_mm"]) + " (paroi)")
    vC.dim_y((ho + 2, L["gasket_bot"]), (ho + 2, L["gasket_top"]), -6, fmt(gk_t) + " (joint)")
    vC.dim_x((hi - leg, zp - te), (hi, zp - te), -8, fmt(leg))
    vC.dim_y((hi - leg - 1, zp - te), (hi - leg - 1, zp), 6, fmt(te))
    vC.dim_y((hi - te, zp - leg), (hi - te, zp), 14, fmt(leg))
    vC.dim_x((ho, zp + 6), (L["up_x_in"], zp + 6), 6, "6,5 (jeu / cadre)")
    vC.line((L["up_x_in"], zp - 40), (L["up_x_in"], zp + 10), 0.15, (0, (4, 1.5)))
    vC.line((P["plate"]["tap_half_mm"], zp - 20), (P["plate"]["tap_half_mm"], zp + 4), 0.15, (0, (8, 1.5, 1.5, 1.5)))
    vC.note((P["plate"]["tap_half_mm"], zp - 14), "M5 ↧10 dans la plaque (axe à 208)", -30, -16)
    s.block((330, 190), [
        "1. Caisson soudé : parois et fond 6, intérieur 430 x 430, hauteur intérieure 150 (jusqu'à la plaque).",
        "2. Joint plat EPDM 6 x 2 entre le chant des parois et la plaque (pas de gorge dans la plaque).",
        "3. Cornière intérieure 15 x 15 x 3 : 32 vis M5 (carré de demi-côté 208, pas 52) dans la plaque.",
        "4. Jeu caisson / cadre 6,5 ; le caisson ne touche que la plaque (poussée auto-équilibrée).",
        "5. Dégagements locaux en paroi face aux blocs de vé P1 et P2 (conflit des notes 03/05, à arbitrer).",
        "6. Planéité de la face d'appui du joint et étanchéité : à spécifier (valeurs à valider).",
        "7. Tôle de distribution, nappe média, déflecteur et plots : pièces associées (non détaillées ici).",
    ], title="NOTES", size=2.5, lead=3.8)
    return s.save(PLANS / "plan_caisson", png)


# -----------------------------------------------------------------------------------------------------------
#  6. Pièces aérauliques imprimées : diffuseur, adaptateur, buse (A3)
# -----------------------------------------------------------------------------------------------------------
def plan_aero(P: dict, png: bool = False) -> list[str]:
    A, F = P["aero"], P["fan"]
    L = levels(P)
    D = L["dif"]
    ap = {p.name: p for p in aero_mod.build(P)}
    dif = ap["diffuseur_conique"].shape.translate((0, 0, -L["dif_top"]))
    adp = ap["adaptateur_rect_rond"].shape.translate((0, 0, -L["adp_bot"]))
    bell = (ap["aspiration_buse"].shape.translate((-L["fan_xc"], -(L["box_y_rear"] - A["box_wall_mm"]), -L["fan_zc"]))
            .rotate((0, 0, 0), (1, 0, 0), -90))
    mass = sum(ap[k].mass(P) for k in ("diffuseur_conique", "adaptateur_rect_rond", "aspiration_buse"))
    s = Sheet("A3", "Pièces aérauliques imprimées : diffuseur, adaptateur, buse", "TAB-AER-001",
              "Impression 3D (PA12 ou ABS)", mass, "0,55:1 ; 1,5:1",
              "ISO 2768-mK (brut : ±0,3)", "Diffuseur 2θ = 7° Ø50 -> Ø80 ; adaptateur ; buse col Ø30 (masse à 1240 kg/m³)",
              rugosite="Ra 6,3 (brut) ; joints 3,2")
    ro, ri = D["d_out"] / 2, D["d_in"] / 2
    dw, ft = A["diffuser_wall_mm"], A["flange_t_mm"]
    fr = ro + A["flange_extra_mm"] / 2
    # diffuseur
    s.label((130, 281), "DIFFUSEUR CONIQUE (coupe)")
    vd = s.view(_half(dif), "face", (130, 185), 0.55)
    zt, zb = 0.0, -D["length"]
    vd.dim_y((fr, zb), (fr, zt), -10, fmt(D["length"], 1))
    vd.dim_x((-ri, zb), (ri, zb), -8, "Ø" + fmt(D["d_in"]) + " (int.)")
    vd.dim_x((-ro, zt - 1), (ro, zt - 1), 6, "Ø" + fmt(D["d_out"]) + " (int.)")
    vd.dim_x((-fr, zt), (fr, zt), 14, "Ø" + fmt(2 * fr) + " (bride)")
    vd.dim_y((-fr, zt - ft), (-fr, zt), 10, fmt(ft))
    vd.note((ro + dw / 2 + 3, zt - 120), f"demi-angle {fmt(D['half_angle_deg'], 2)}°, paroi {fmt(dw)}", 18, -10)
    # adaptateur
    ow, od = F["outlet_mm"]
    w = F["wall_mm"]
    s.label((290, 280), "ADAPTATEUR (coupe)")
    va = s.view(_half(adp), "face", (290, 235), 1.5)
    va.dim_y((-(ow + 2 * w) / 2 - 2, 0), (-(ow + 2 * w) / 2 - 2, A["adapter_len_mm"]), 6, fmt(A["adapter_len_mm"]))
    va.dim_x(((-ow - 2 * w) / 2, 0), ((ow + 2 * w) / 2, 0), -6, fmt(ow + 2 * w) + " (rect.)")
    va.dim_x((-(D["d_in"] + 2 * dw) / 2, A["adapter_len_mm"]), ((D["d_in"] + 2 * dw) / 2, A["adapter_len_mm"]), 6,
             "Ø" + fmt(D["d_in"] + 2 * dw))
    s.label((380, 280), "ADAPTATEUR (dessus)")
    vt = s.view(adp, "dessus", (380, 235), 1.5)
    vt.dim_y((-(ow + 2 * w) / 2, -(od + 2 * w) / 2), (-(ow + 2 * w) / 2, (od + 2 * w) / 2), 6, fmt(od + 2 * w))
    vt.note((-ow / 2, -od / 2), f"sortie ventilateur {fmt(ow)} x {fmt(od)} (à confirmer)", -4, -18)
    # buse
    rt, Rf, lip = 15.0, A["bell_flare_r_mm"], A["bell_lip_mm"]
    Lb = Rf + 6.0
    ro_b = rt + Rf + lip
    s.label((340, 165), "BUSE COL Ø30 (coupe)")
    vb = s.view(_half(bell), "face", (340, 118), 1.5)
    vb.dim_x((-rt, Lb / 2), (rt, Lb / 2), -4, "Ø30 (col)") if False else vb.dim_x((-rt, 0), (rt, 0), -8, "Ø30 (col)")
    vb.dim_x((-ro_b, Lb), (ro_b, Lb), 8, "Ø" + fmt(2 * ro_b) + " (collerette de bouche)")
    vb.dim_y((ro_b + 8, 0), (ro_b + 8, Lb), -8, fmt(Lb))
    vb.dim_x((-(ro_b + 8), 0), (ro_b + 8, 0), -22, "Ø" + fmt(2 * (ro_b + 8)) + " (bride)")
    vb.note((-(rt + Rf * 0.3), Lb - Rf * 0.7), f"R{fmt(Rf)} (ISO 5801 approché)", -4, 18)
    s.block((30, 80), [
        "1. Diffuseur : bride Ø110 x 4 côté plenum (face d'appui du joint), conicité 2θ = 7° (L = 245,2).",
        "2. Adaptateur : loft rectangle -> Ø50, parois 2 ; sortie rectangulaire du 9BMC à confirmer (fiche constructeur).",
        "3. Buse : col Ø30, bouche évasée R20, bride arrière Ø90 ; montée dans le caisson d'aspiration, alésage Ø30 du tube.",
        "4. Étanchéité entre étages assurée par joints et colle ; états de surface internes lissés (sans marche).",
        "5. Tolérances d'impression ±0,3 ; portées usinées ou ponçées : planéité 0,2 (valeur indicative).",
    ], title="NOTES", size=2.5, lead=3.8)
    return s.save(PLANS / "plan_aero", png)


def make_all(P: dict, m_plate_kg: float | None = None, png: bool = False) -> dict:
    """Génère les 6 plans ; retourne {nom: fichiers} ou l'erreur rencontrée."""
    out: dict = {}
    for name, fn in (("plaque", lambda: plan_plaque(P, m_plate_kg, png)), ("vee", lambda: plan_vee(P, png)),
                     ("verin", lambda: plan_verin(P, png)), ("adxl", lambda: plan_adxl(P, png)),
                     ("caisson", lambda: plan_caisson(P, None, png)), ("aero", lambda: plan_aero(P, png))):
        try:
            out[name] = fn()
        except Exception as e:  # pragma: no cover
            out[name] = {"erreur": repr(e)}
    return out


if __name__ == "__main__":
    from cad.common import get_params
    import json
    print(json.dumps(make_all(get_params(), None, png=False), indent=1, ensure_ascii=False))
