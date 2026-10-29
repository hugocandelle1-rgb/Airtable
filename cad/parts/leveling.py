"""Nivellement : 3 colonnes d'appui (plaque -> vérins, traversant le plenum), 1 pivot fixe,
2 vérins de réglage fin à vis, moteurs pas à pas NEMA17 (enveloppes simplifiées).

Les colonnes montent jusqu'aux billes de Kelvin (cote issue de plate.insert_geometry) ; les
vérins reposent sur les consoles du cadre supérieur (frame.py). Phase 2 : mécanisme réel.
"""
from __future__ import annotations

import cadquery as cq

from cad.common import COLORS, PartSpec, levels
from cad.parts import plate as plate_mod


def build(P: dict) -> list[PartSpec]:
    lv, S = P["leveling"], P["support"]
    L = levels(P)
    ct = L["console_top"]
    bx, by, bz = lv["base_mm"]
    parts: list[PartSpec] = []
    for g in plate_mod.insert_geometry(P):
        i, x, y = g["index"] + 1, g["x"], g["y"]
        # colonne d'appui : de la tête du vérin à la bille
        col = (cq.Workplane("XY").workplane(offset=L["verin_head_top"]).center(x, y)
               .circle(S["column_d_mm"] / 2.0).extrude(g["column_top"] - L["verin_head_top"]))
        parts.append(PartSpec(f"colonne_appui_{i}", col, COLORS["acier"], "acier", "nivellement",
                              note="colonne Ø16 traversant le fond et la tôle du plenum (passage étanche non modélisé)"))
        base = cq.Workplane("XY").box(bx, by, bz, centered=(True, True, False)).translate((x, y, ct))
        if g["role"] == "pivot":
            body = (cq.Workplane("XY").workplane(offset=ct + bz).center(x, y).circle(lv["body_d_mm"] / 2.0)
                    .extrude(lv["verin_height_mm"] - bz))
            parts.append(PartSpec(f"pivot_fixe_{i}", base.union(body), COLORS["verin"], "acier", "nivellement",
                                  note="pivot fixe (hauteur non réglable)"))
            continue
        h_knob = 12.0
        body = (cq.Workplane("XY").workplane(offset=ct + bz).center(x, y).circle(lv["body_d_mm"] / 2.0)
                .extrude(lv["verin_height_mm"] - bz - h_knob))
        knob = (cq.Workplane("XY").workplane(offset=ct + lv["verin_height_mm"] - h_knob).center(x, y)
                .circle(lv["knob_d_mm"] / 2.0).extrude(h_knob))
        parts.append(PartSpec(f"verin_{i}", base.union(body).union(knob), COLORS["verin"], "acier",
                              "nivellement", note="vérin à vis fin (enveloppe) : course ± 0,25 deg à détailler en phase 2"))
        # moteur NEMA17 posé sur la console, côté bord du cadre ; accouplement horizontal vers le vérin
        s = 1.0 if y >= 0 else -1.0
        mx, my, mz = lv["nema17_mm"]
        ym = y + s * lv["motor_offset_mm"]
        motor = cq.Workplane("XY").box(mx, my, mz, centered=(True, True, False)).translate((x, ym, ct))
        parts.append(PartSpec(f"moteur_nema17_{i}", motor, COLORS["moteur"], "acier", "nivellement",
                              mass_kg=lv["nema17_mass_kg"], commercial=True, note="NEMA17 (enveloppe)"))
        y_a = y + s * lv["body_d_mm"] / 2.0
        y_b = ym - s * my / 2.0
        ylo, yhi = min(y_a, y_b), max(y_a, y_b)
        cpl = (cq.Workplane("XZ").workplane(offset=-yhi).center(x, ct + 25.0).circle(4.0).extrude(yhi - ylo))
        parts.append(PartSpec(f"accouplement_{i}", cpl, COLORS["acier"], "acier", "nivellement",
                              note="accouplement moteur -> vis (schéma)"))
    return parts
