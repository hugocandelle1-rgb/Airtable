"""Infrastructure CAO paramétrique de la table à coussin d'air.

Contenu :
  - DEFAULTS     : valeurs par défaut des cotes absentes de params/design.toml
                   (à figer en phase 2 par les agents aéraulique / structure) ;
  - get_params   : fusion TOML (prioritaire) + DEFAULTS (+ surcharges éventuelles) ;
  - levels       : cotes Z / positions dérivées (une seule vérité pour tous les modules) ;
  - PROFILES, profile_solid, bar : bibliothèque de profilés aluminium + liste de débit ;
  - PartSpec     : description d'une pièce (forme, couleur, matière, masse) ;
  - check_interferences, helpers d'export.

Repère global (identique dans tous les modules) :
  origine = centre de la FACE SUPÉRIEURE de la plaque, Z vers le haut, X/Y dans le plan.
  Unités : mm, kg. Sol à z = -frame.table_height_mm.
"""
from __future__ import annotations

import copy
import functools
import math
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq

from calc.common.params import REPO_ROOT, load_params

CAD_DIR = REPO_ROOT / "cad"
EXPORT_DIR = CAD_DIR / "export"

# =============================================================================
#  VALEURS PAR DÉFAUT (clés absentes de params/design.toml)
#  >>> Ce bloc est ce que la phase 2 devra figer (ou déplacer dans le TOML). <<<
# =============================================================================
DEFAULTS: dict = {
    # masses volumiques kg/m3 (ordres de grandeur usuels ; plate.rho vient du TOML)
    "materials": {
        "alu": 2700.0, "alu_5083": 2660.0, "acier": 7850.0, "inox": 7900.0,
        "pmma": 1190.0, "epdm": 1150.0, "pla": 1240.0, "media_filtrant": 150.0,
        "composite": 1000.0,
    },
    "plate": {
        "edge_band_mm": 2.5,            # bande exclue au bord de la zone percée (centres des trous)
        "witness_holes": 19,            # modèle léger : nb de trous témoins (amas central)
        "pocket_d_mm": 16.0,            # logement d'insert (dessous)
        "pocket_depth_mm": 6.0,
        "hole_exclusion_margin_mm": 2.0,  # trous supprimés autour d'un logement d'appui
        "insert_d_mm": 15.9,            # pastille d'appui (vé / cône / plat)
        "insert_t_mm": 6.0,
        "insert_recess_depth_mm": 5.0,  # profondeur du cône / vé dans la pastille
        "insert_half_angle_deg": 45.0,
        "ball_d_mm": 10.0,              # bille de contact (couplage de Kelvin)
        "tap_thread": "M5",
        "tap_d_mm": 4.2,                # avant-trou taraudage
        "tap_depth_mm": 12.0,
        "tap_half_mm": 228.0,           # demi-côté du carré de vis de la bride plaque/plenum
        "tap_per_side": 6,              # vis par côté, coins inclus
        "pin_d_mm": 6.0,                # pions de référence (reprise d'usinage)
        "pin_depth_mm": 10.0,           # borgne depuis le dessous
        "pin_positions_mm": [[-250.0, -250.0], [250.0, 250.0]],
    },
    "support": {                         # schéma d'appui : TOML support.scheme = "TBD"
        "radius_mm": 168.0,              # ~0,645 x 260 (optimum disque, à recalculer)
        "angles_deg": [90.0, 210.0, 330.0],
        "insert_types": ["cone", "ve", "plat"],   # Kelvin : cône / vé / plat
        "roles": ["pivot", "verin", "verin"],     # 1 pivot fixe + 2 vérins
        "column_d_mm": 16.0,             # colonne d'appui traversant le plenum
    },
    "plenum": {
        "profile": "45x45",
        "panel_t_mm": 5.0,
        "panel_embed_mm": 8.0,           # pénétration du panneau dans la rainure
        "panel_material": "alu",
        "bride_t_mm": 8.0,               # bride supérieure du plenum
        "membrane_gap_mm": 12.0,         # dessous plaque -> dessus bride
        "membrane_t_mm": 1.5,
        "membrane_fold_dip_mm": 12.0,    # profondeur du U sous la bride
        "membrane_wall_spacing_mm": 10.0,  # écart entre les deux branches du U
        "membrane_flange_half_mm": 240.0,  # demi-largeur extérieure des collerettes
        "membrane_inset_mm": 6.0,        # branche extérieure du U = ouverture bride - inset
        "ring_t_mm": 6.0,                # bride de serrage sous la plaque
        "ring_wall_clearance_mm": 1.0,
        "baffle_t_mm": 2.0,
        "baffle_hole_d_mm": 8.0,
        "baffle_edge_gap_mm": 1.0,
        "baffle_holes": True,            # perforation réelle (False = tôle pleine)
        "column_hole_d_mm": 20.0,        # passage des colonnes (fond + tôle)
    },
    "leveling": {
        "verin_height_mm": 60.0,         # console -> tête du vérin
        "head_gap_mm": 5.0,              # tête vérin / dessous du fond du plenum
        "base_mm": [40.0, 40.0, 8.0],
        "body_d_mm": 30.0,
        "knob_d_mm": 22.0,
        "nema17_mm": [42.3, 42.3, 40.0],
        "nema17_mass_kg": 0.28,
        "motor_offset_mm": 60.0,         # moteur / axe vérin le long de la console
        "console_clear_mm": 22.5,        # la console dépasse l'axe du vérin de cette valeur
    },
    "fan": {                             # TOML fan.reference = "TBD"
        "size_mm": [97.0, 97.0, 33.0],   # face x face x épaisseur (axe d'aspiration)
        "outlet_mm": [30.0, 26.0],       # sortie rectangulaire (selon X, selon Y)
        "outlet_offset_x_mm": -30.0,     # position de la sortie / centre du carter
        "stub_h_mm": 6.0,
        "wall_mm": 2.0,
        "standoff_mm": 6.0,              # cale sous le ventilateur
        "mass_kg": 0.15,
    },
    "aero": {
        "manchon_len_mm": 40.0,
        "adapter_len_mm": 40.0,
        "diffuser_half_angle_deg": 7.0,
        "diffuser_d_in_mm": 40.0,
        "diffuser_d_out_mm": 120.0,
        "diffuser_len_mm": 0.0,          # 0 = déduit du demi-angle
        "diffuser_wall_mm": 2.0,
        "diffuser_flange_extra_mm": 30.0,   # Ø bride = d_out + extra
        "diffuser_flange_t_mm": 6.0,
        "bell_throat_d_mm": 60.0,
        "bell_flare_r_mm": 12.0,
        "bell_len_mm": 15.0,
        "bell_lip_mm": 2.0,
        "filter_d_mm": 95.6,
        "filter_t_mm": 20.0,
        "filter_gap_mm": 10.0,
        "housing_wall_mm": 2.0,
    },
    "frame": {
        "footprint_mm": 700.0,
        "table_height_mm": 900.0,        # sol -> dessus de la plaque
        "foot_h_mm": 60.0,               # pied réglable (hauteur sous montant)
        "foot_stud_d_mm": 16.0,
        "foot_base_d_mm": 60.0,
        "foot_base_t_mm": 10.0,
        "top_ring_drop_mm": 5.0,         # dessus du cadre haut sous le dessous de plaque
    },
    "platine": {
        "size_mm": [260.0, 200.0],
        "t_mm": 8.0,
        "plot_d_mm": 25.0,
        "plot_h_mm": 20.0,
        "plot_inset_mm": 25.0,
        "margin_mm": 20.0,
    },
    "screen": {
        "t_mm": 4.0,
        "height_above_plate_mm": 150.0,
    },
    "gantry": {
        "enabled": True,
        "camera_lens_z_mm": 450.0,       # hauteur de l'objectif au-dessus de la plaque
        "camera_mm": [60.0, 60.0, 40.0],
        "lens_d_mm": 30.0,
        "lens_len_mm": 30.0,
        "camera_mass_kg": 0.25,
    },
    "cad": {
        "tol_interference_mm3": 1.0,
    },
}


def _merge(base: dict, over: dict) -> dict:
    """Fusion récursive : `over` écrase `base`."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _flatten(d: dict, pre: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{pre}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


def get_params(overrides: dict | None = None) -> dict:
    """P = DEFAULTS <- params/design.toml <- overrides (le TOML est prioritaire sur DEFAULTS)."""
    P = _merge(DEFAULTS, load_params())
    if overrides:
        P = _merge(P, overrides)
    return P


def defaults_used() -> list[str]:
    """Clés de DEFAULTS absentes du TOML (donc pilotées par défaut)."""
    toml_keys = set(_flatten(load_params()))
    return sorted(k for k in _flatten(DEFAULTS) if k not in toml_keys)


# =============================================================================
#  Pièces, couleurs, matières
# =============================================================================
COLORS = {
    "plaque": (0.78, 0.80, 0.84, 1.0), "acier": (0.35, 0.37, 0.40, 1.0),
    "profile": (0.72, 0.74, 0.77, 1.0), "panneau": (0.55, 0.65, 0.80, 1.0),
    "tole": (0.62, 0.64, 0.68, 1.0), "joint": (0.10, 0.10, 0.10, 1.0),
    "bride": (0.60, 0.62, 0.66, 1.0), "ventilateur": (0.15, 0.15, 0.17, 1.0),
    "aero": (0.95, 0.60, 0.15, 1.0), "souple": (0.20, 0.20, 0.25, 1.0),
    "filtre": (0.95, 0.95, 0.85, 1.0), "moteur": (0.10, 0.45, 0.20, 1.0),
    "verin": (0.85, 0.25, 0.20, 1.0), "plot": (0.05, 0.05, 0.05, 1.0),
    "ecran": (0.70, 0.88, 0.95, 0.30), "camera": (0.20, 0.20, 0.60, 1.0),
    "pied": (0.25, 0.25, 0.25, 1.0), "platine": (0.80, 0.70, 0.40, 1.0),
}


@dataclass
class PartSpec:
    """Une pièce en coordonnées globales (repère de l'assemblage)."""
    name: str
    shape: cq.Workplane
    color: tuple = (0.7, 0.7, 0.7, 1.0)
    material: str = "alu"
    group: str = ""                    # plaque | plenum | aero | bati | nivellement | option
    mass_kg: float | None = None       # surcharge (composant du commerce, profilé catalogue)
    formats: tuple = ("step",)         # exports individuels : "step", "stl"
    profile: dict | None = None        # {"section": "45x45", "length_mm": 400.0}
    commercial: bool = False
    note: str = ""

    def volume_mm3(self) -> float:
        return float(self.shape.val().Volume())

    def mass(self, P: dict) -> float:
        if self.mass_kg is not None:
            return self.mass_kg
        rho = P["materials"][self.material] if self.material in P["materials"] else 2700.0
        if self.material == "alu_5083":
            rho = P["plate"].get("rho", rho)
        return self.volume_mm3() * 1e-9 * rho

    def bbox(self) -> tuple:
        b = self.shape.val().BoundingBox()
        return (b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax)


# =============================================================================
#  Bibliothèque de profilés aluminium (sections simplifiées à rainures en T)
# =============================================================================
# w x h : section ; slot : ouverture de rainure ; lip : épaisseur de la lèvre ;
# ch_w / ch_d : largeur / profondeur de la chambre en T ; bore : perçage central.
# kg_m : masse linéique ESTIMÉE (ordre de grandeur catalogue léger, NON SOURCÉE :
#        à confirmer sur fiche fournisseur dans docs/research/).
PROFILES: dict[str, dict] = {
    "40x40": dict(w=40.0, h=40.0, slot=8.0, lip=3.0, ch_w=16.5, ch_d=7.0, bore=8.5, kg_m=1.45),
    "45x45": dict(w=45.0, h=45.0, slot=10.0, lip=4.0, ch_w=20.0, ch_d=8.0, bore=10.5, kg_m=1.85),
    "40x80": dict(w=40.0, h=80.0, slot=8.0, lip=3.0, ch_w=16.5, ch_d=7.0, bore=8.5, kg_m=2.75),
    "45x90": dict(w=45.0, h=90.0, slot=10.0, lip=4.0, ch_w=20.0, ch_d=8.0, bore=10.5, kg_m=3.60),
}


def profile_key(size_mm: float) -> str:
    return f"{int(size_mm)}x{int(size_mm)}"


def slot_depth(key: str) -> float:
    d = PROFILES[key]
    return d["lip"] + d["ch_d"]


def _slot_tool(d: dict, c: float, angle: float, length: float) -> cq.Workplane:
    """Rainure en T sur la face +Y, centrée en x=c, puis tournée de `angle` autour de Z."""
    s, lip, cw, cd = d["slot"], d["lip"], d["ch_w"], d["ch_d"]
    top = d["h"] / 2.0 if angle in (0, 180) else d["w"] / 2.0
    # NB : pour les faces ±X la « hauteur » de la face à partir du centre est w/2
    pts = [
        (c - s / 2, top + 1), (c + s / 2, top + 1), (c + s / 2, top - lip),
        (c + cw / 2, top - lip), (c + cw / 2, top - lip - cd), (c - cw / 2, top - lip - cd),
        (c - cw / 2, top - lip), (c - s / 2, top - lip),
    ]
    t = cq.Workplane("XY").polyline(pts).close().extrude(length)
    return t.rotate((0, 0, 0), (0, 0, 1), angle)


@functools.lru_cache(maxsize=256)
def _profile_z(key: str, length: float) -> cq.Workplane:
    """Profilé le long de +Z (z de 0 à length), section centrée sur l'origine."""
    d = PROFILES[key]
    w, h = d["w"], d["h"]
    body = cq.Workplane("XY").rect(w, h).extrude(length)
    cut = None
    for angle, face_len in ((0, w), (180, w), (90, h), (270, h)):
        m = max(1, round(face_len / min(w, h)))
        pitch = face_len / m
        for i in range(m):
            c = (i - (m - 1) / 2.0) * pitch
            t = _slot_tool(d, c, angle, length)
            cut = t if cut is None else cut.union(t)
    body = body.cut(cut)
    body = body.cut(cq.Workplane("XY").circle(d["bore"] / 2).extrude(length))
    return body


def profile(length: float, key: str = "45x45") -> cq.Workplane:
    """Profilé de longueur `length` le long de Z (de 0 à length)."""
    return _profile_z(key, round(float(length), 3)).translate((0, 0, 0))


def section_dims(key: str, axis: str, tall: bool = True) -> tuple[float, float]:
    """(dim horizontale, dim verticale) de la section pour une barre horizontale."""
    d = PROFILES[key]
    a, b = d["w"], d["h"]
    if axis == "Z":
        return a, b
    lo, hi = min(a, b), max(a, b)
    return (lo, hi) if tall else (hi, lo)


def bar(key: str, axis: str, start: tuple, length: float, tall: bool = True) -> cq.Workplane:
    """Profilé d'axe X, Y ou Z, de longueur `length`, démarrant au point `start`
    (point de l'axe neutre). Pour une section rectangulaire, `tall` met le grand côté à la verticale."""
    s = _profile_z(key, round(float(length), 3))
    d = PROFILES[key]
    if axis == "X":
        # rotation Y +90 : x_local -> -z ; il faut w vertical (grand côté si tall)
        roll = 90 if (tall and d["w"] < d["h"]) or (not tall and d["w"] > d["h"]) else 0
        s = s.rotate((0, 0, 0), (0, 0, 1), roll).rotate((0, 0, 0), (0, 1, 0), 90)
    elif axis == "Y":
        # rotation X -90 : y_local -> -z ; il faut h vertical
        roll = 90 if (tall and d["h"] < d["w"]) or (not tall and d["h"] > d["w"]) else 0
        s = s.rotate((0, 0, 0), (0, 0, 1), roll).rotate((0, 0, 0), (1, 0, 0), -90)
    return s.translate(start)


def bar_part(name: str, key: str, axis: str, start: tuple, length: float, P: dict,
             group: str, tall: bool = True, note: str = "") -> PartSpec:
    """PartSpec d'un profilé (masse = masse linéique catalogue estimée)."""
    mass = PROFILES[key]["kg_m"] * length / 1000.0
    return PartSpec(name, bar(key, axis, start, length, tall), COLORS["profile"], "alu", group,
                    mass_kg=mass, profile={"section": key, "length_mm": round(length, 2)},
                    commercial=True, note=note)


def cut_list(parts: list[PartSpec]) -> list[dict]:
    """Liste de débit : profilés regroupés par (section, longueur)."""
    agg: dict = {}
    for p in parts:
        if not p.profile:
            continue
        k = (p.profile["section"], p.profile["length_mm"])
        row = agg.setdefault(k, {"section": k[0], "longueur_mm": k[1], "quantite": 0, "pieces": []})
        row["quantite"] += 1
        row["pieces"].append(p.name)
    rows = []
    for (sec, L), r in sorted(agg.items()):
        r["longueur_totale_m"] = round(L * r["quantite"] / 1000.0, 4)
        r["masse_kg_estimee"] = round(PROFILES[sec]["kg_m"] * L * r["quantite"] / 1000.0, 3)
        r["pieces"] = " ".join(r["pieces"])
        rows.append(r)
    return rows


# =============================================================================
#  Cotes dérivées (Z, positions) — SEULE source pour tous les modules
# =============================================================================
def support_radius(P: dict) -> float:
    rr = P.get("support", {}).get("radius_ratio", 0.0) or 0.0
    return rr * P["plate"]["outer_square_mm"] / 2.0 if rr > 0 else P["support"]["radius_mm"]


def support_points(P: dict) -> list[dict]:
    """Positions des appuis : [{x, y, type, role, index}] (angles mesurés depuis +X)."""
    S = P["support"]
    r = support_radius(P)
    out = []
    for i, a in enumerate(S["angles_deg"]):
        out.append({"index": i, "x": r * math.cos(math.radians(a)), "y": r * math.sin(math.radians(a)),
                    "type": S["insert_types"][i], "role": S["roles"][i], "angle": a})
    return out


def diffuser_geometry(P: dict) -> dict:
    A = P["aero"]
    d_in, d_out = A["diffuser_d_in_mm"], A["diffuser_d_out_mm"]
    if A["diffuser_len_mm"] > 0:
        L = A["diffuser_len_mm"]
        ang = math.degrees(math.atan((d_out - d_in) / 2.0 / L))
    else:
        ang = A["diffuser_half_angle_deg"]
        L = (d_out - d_in) / 2.0 / math.tan(math.radians(ang))
    return {"length": L, "half_angle_deg": ang, "d_in": d_in, "d_out": d_out}


def levels(P: dict) -> dict:
    """Cotes verticales et positions dérivées des paramètres (mm)."""
    pl, pn, fr, A, F = P["plate"], P["plenum"], P["frame"], P["aero"], P["fan"]
    lv, pf = P["leveling"], P["platine"]
    L: dict = {}
    t = pl["thickness_mm"]
    L["plate_top"], L["plate_bot"] = 0.0, -t
    # --- plenum ---------------------------------------------------------------
    pk = pn["profile"]
    s = PROFILES[pk]["w"]                       # section carrée requise pour le plenum
    L["pl_s"] = s
    L["pl_cp"] = (pn["inner_square_mm"] + pn["panel_t_mm"]) / 2.0      # axe des montants/panneaux
    L["pl_open_half"] = L["pl_cp"] - s / 2.0                          # ouverture libre (demi)
    L["pl_outer_half"] = L["pl_cp"] + s / 2.0
    L["bride_top"] = L["plate_bot"] - pn["membrane_gap_mm"]
    L["bride_bot"] = L["bride_top"] - pn["bride_t_mm"]
    L["rail_top_top"] = L["bride_bot"]                                # dessus rails/montants
    L["rail_top_bot"] = L["rail_top_top"] - s
    L["cavity_top"] = L["bride_top"]
    L["cavity_floor"] = L["cavity_top"] - pn["height_mm"]
    L["fond_top"] = L["cavity_floor"]
    L["fond_bot"] = L["cavity_floor"] - pn["panel_t_mm"]
    L["rail_bot_c"] = L["cavity_floor"] - pn["panel_t_mm"] / 2.0
    L["rail_bot_bot"] = L["rail_bot_c"] - s / 2.0
    L["rail_bot_top"] = L["rail_bot_c"] + s / 2.0
    L["baffle_top"] = L["cavity_top"] - pn["settling_height_mm"]
    L["baffle_bot"] = L["baffle_top"] - pn["baffle_t_mm"]
    # --- nivellement ------------------------------------------------------------
    L["verin_head_top"] = L["fond_bot"] - lv["head_gap_mm"]
    L["console_top"] = L["verin_head_top"] - lv["verin_height_mm"]
    L["pl_leg"] = L["rail_bot_bot"] - L["console_top"]                  # prolongement des montants
    L["pl_up_bot"] = L["console_top"]
    # --- chaîne aéraulique --------------------------------------------------------
    D = diffuser_geometry(P)
    L["dif"] = D
    L["dif_top"] = L["fond_bot"]
    L["dif_bot"] = L["dif_top"] - D["length"]
    L["adp_top"], L["adp_bot"] = L["dif_bot"], L["dif_bot"] - A["adapter_len_mm"]
    L["man_top"], L["man_bot"] = L["adp_bot"], L["adp_bot"] - A["manchon_len_mm"]
    L["stub_top"] = L["man_bot"]
    L["fan_top"] = L["stub_top"] - F["stub_h_mm"]
    L["fan_bot"] = L["fan_top"] - F["size_mm"][1]
    L["fan_zc"] = (L["fan_top"] + L["fan_bot"]) / 2.0
    L["fan_xc"] = -F["outlet_offset_x_mm"]
    L["fan_yc"] = 0.0
    L["cale_bot"] = L["fan_bot"] - F["standoff_mm"]
    L["bell_tube_len"] = A["bell_len_mm"] + A["bell_lip_mm"] + A["filter_gap_mm"] + A["filter_t_mm"] + 2.0
    # empreinte du ventilateur + filtre (axe d'aspiration = -Y)
    y_far = -F["size_mm"][2] / 2.0 - L["bell_tube_len"]
    L["fan_y_min"], L["fan_y_max"] = y_far, F["size_mm"][2] / 2.0
    L["pf_cx"] = L["fan_xc"]
    L["pf_cy"] = (L["fan_y_min"] + L["fan_y_max"]) / 2.0
    # --- platine découplée + traverses ---------------------------------------------
    L["pf_top"] = L["cale_bot"]
    L["pf_bot"] = L["pf_top"] - pf["t_mm"]
    L["plot_bot"] = L["pf_bot"] - pf["plot_h_mm"]
    fs = PROFILES[profile_key(fr["profile_main_mm"])]["w"]
    L["fs"] = fs
    L["trav_pf_top"] = L["plot_bot"]
    L["trav_pf_bot"] = L["trav_pf_top"] - fs
    # --- bâti ------------------------------------------------------------------------
    L["floor"] = -fr["table_height_mm"]
    L["up_bot"] = L["floor"] + fr["foot_h_mm"]
    L["top_ring_top"] = L["plate_bot"] - fr["top_ring_drop_mm"]
    L["top_ring_bot"] = L["top_ring_top"] - fs
    L["low_ring_bot"], L["low_ring_top"] = L["up_bot"], L["up_bot"] + fs
    L["cad_sup_top"] = L["console_top"]
    L["cad_sup_bot"] = L["console_top"] - fs
    L["fr_cp"] = fr["footprint_mm"] / 2.0 - fs / 2.0                    # axe des montants du bâti
    L["fr_in_half"] = fr["footprint_mm"] / 2.0 - fs                     # face intérieure
    return L


# =============================================================================
#  Vérifications et exports
# =============================================================================
def check_interferences(parts: list[PartSpec], tol_mm3: float = 1.0, margin: float = 0.001) -> list[dict]:
    """Intersections booléennes deux à deux (pré-filtre par boîtes englobantes).
    Retourne la liste des paires dont le volume commun dépasse tol_mm3."""
    bbs = [p.bbox() for p in parts]
    bad = []
    n_tested = 0
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            a, b = bbs[i], bbs[j]
            if (a[0] >= b[3] - margin or b[0] >= a[3] - margin or a[1] >= b[4] - margin
                    or b[1] >= a[4] - margin or a[2] >= b[5] - margin or b[2] >= a[5] - margin):
                continue
            n_tested += 1
            try:
                v = parts[i].shape.val().intersect(parts[j].shape.val()).Volume()
            except Exception as e:  # booléen dégénéré : on le signale
                bad.append({"a": parts[i].name, "b": parts[j].name, "volume_mm3": None, "erreur": str(e)})
                continue
            if v > tol_mm3:
                bad.append({"a": parts[i].name, "b": parts[j].name, "volume_mm3": round(v, 3)})
    check_interferences.last_tested = n_tested
    return bad


def compound_of(parts: list[PartSpec]) -> cq.Workplane:
    return cq.Workplane("XY").newObject([cq.Compound.makeCompound([p.shape.val() for p in parts])])


def export_svg(shape: cq.Workplane, path: Path, direction: tuple, size: int = 900, hidden: bool = False):
    cq.exporters.export(shape, str(path), opt={
        "projectionDir": direction, "showHidden": hidden, "width": size, "height": size,
        "marginLeft": 20, "marginTop": 20, "strokeWidth": 0.6, "showAxes": False})


def make_assembly(parts: list[PartSpec], name: str = "table_coussin_air") -> cq.Assembly:
    a = cq.Assembly(name=name)
    for p in parts:
        a.add(p.shape, name=p.name, color=cq.Color(*p.color))
    return a
