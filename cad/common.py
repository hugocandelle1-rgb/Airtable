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
#  Phase 2 : cotes figées d'après les notes de calcul ; la source est citée en commentaire.
#  Références : [02] docs/02_aeraulique.md §13 ; [03] docs/03_structure_plaque.md §8 ;
#  [04] docs/04_usinage_tolerances.md §7 ; [05] docs/05_nivellement.md §7.
#  Repère CAD : z = 0 sur la face supérieure de la plaque ; z_CAD = z_notes - plate_top_height_mm.
# =============================================================================
DEFAULTS: dict = {
    # masses volumiques kg/m3 (ordres de grandeur usuels ; plate.rho vient du TOML)
    "materials": {
        "alu": 2700.0, "alu_5083": 2660.0, "acier": 7850.0, "inox": 7900.0,
        "pmma": 1190.0, "epdm": 1150.0, "pla": 1240.0, "media_filtrant": 150.0,
        "composite": 1000.0, "xps": 35.0, "ptfe": 2200.0, "bronze": 8800.0,
    },
    "plate": {
        "edge_band_mm": 1.0,             # [04] trous à >= 1 mm du bord de zone -> 5 935 trous
        "chamfer_mm": 1.0,               # [04] chanfreins 1 x 45 deg
        "cone_angle_deg": 118.0,         # [02] fond conique du lamage
        "witness_holes": 19,             # modèle léger : amas central de trous témoins
        "datum_B_mm": [-240.0, 0.0],     # [04] alésage Ø6 H7 débouchant
        "datum_C_mm": [240.0, 0.0],      # [04] lumière 6 H7 x 10, grand axe selon x
        "datum_d_mm": 6.0,
        "datum_C_len_mm": 10.0,
        "ball_pocket_d_mm": 25.4,        # [03] logement Ø25,4 H8 x 10,7
        "ball_pocket_depth_mm": 10.7,
        "ball_center_below_mm": 2.0,     # [03] centre de bille à 2,0 sous la face inférieure
        "tap_thread": "M5",              # [04] attache du caisson : 32 x M5 prof. 10
        "tap_d_mm": 4.2,
        "tap_depth_mm": 10.0,
        "tap_half_mm": 208.0,
        "tap_per_side": 8,
        "adxl_hole_d_mm": 3.3,           # [04] 3 x M4 prof. 8 sur Ø40 (avant-trou)
        "adxl_depth_mm": 8.0,
        "adxl_pcd_mm": 40.0,
        "handling_d_mm": 8.5,            # [04] 4 x M10 prof. 20 sur les chants (avant-trou)
        "handling_depth_mm": 20.0,
        # [04] dit « milieu de chaque côté » mais (±260 ; 0) recoupe les datums B/C (±240 ; 0) :
        # les deux positions sur ±x sont décalées à y = -100 (à arbitrer par la structure).
        "handling_positions_mm": [[0.0, 260.0], [0.0, -260.0], [260.0, -100.0], [-260.0, -100.0]],
    },
    "support": {
        "roller_len_mm": 30.0,           # [03] rouleaux Ø20 x 30 h6
        "vee_block_mm": [40.0, 30.0, 20.0],   # [05] bloc de vé 40 (axe) x 30 x 20
        "roller_axis_above_base_mm": 12.0,
        "vee_half_angle_deg": 45.0,      # vé à 90 deg
        "clamp_pad_d_mm": 10.0,          # [05] patin PTFE Ø10
        "clamp_pad_t_mm": 5.0,
        "clamp_arm_t_mm": 10.0,
        "clamp_post_mm": [9.5, 30.0],    # (épaisseur radiale, largeur) du montant d'étrier (dans le cadre 45)
    },
    "leveling": {
        "housing_mm": [90.0, 30.0],      # [05] boîtier 90 (le long du cadre) x 30 (radial)
        "wedge_mm": [60.0, 24.0],        # [05] coin 60 x 24
        "wedge_travel_mm": 12.1,         # [05] course du coin +/- 12,1
        "head_u_mm": 40.0,               # tête (le long du cadre)
        "screw_d_mm": 6.0,               # [05] M6 x 0,25
        "nema17_mm": [42.0, 42.0, 40.0],  # [05] corps ; 40 = longueur le long de l'arbre
        "nema17_mass_kg": 0.28,
        "knob_d_mm": 40.0,               # [05] bouton gradué Ø40, 100 divisions
        "knob_t_mm": 12.0,
        "coupling_len_mm": 10.0,
        "motor_offset_v_mm": 3.0,        # moteur + bouton décalés vers le cadre : jeu caisson >= 3 mm (Oldham)
        "wedge_floor_mm": 6.0,           # fond de la cavité du boîtier
    },
    "tilt_sensors": {
        "foot_d_mm": 8.0,                # [05] 3 pieds Ø8 x 12 (8 dans la plaque, 4 apparents)
        "foot_visible_mm": 4.0,
        "plateau_d_mm": 50.0,            # [05] plateau Ø50, 3 billes Ø4 sur R18, 6 vés à 60 deg
        "plateau_t_mm": 6.0,
        "ball_d_mm": 4.0,
        "ball_r_mm": 18.0,
        "capot_mm": [80.0, 80.0, 45.0],  # [05] capot XPS 80 x 80 x 45, parois 10
        "capot_wall_mm": 10.0,
        "capot_top_mm": 8.0,
        "pcb_mm": [20.0, 20.0, 2.0],
    },
    "plenum": {
        "gasket_mm": [6.0, 2.0],         # [03] joint plat EPDM 6 x 2
        "angle_mm": [15.0, 3.0],         # [03] cornière intérieure 15 x 15 x 3 (jambe, épaisseur)
        "media_t_mm": 10.0,              # [02] nappe média polyester 10 mm
        "baffle_t_mm": 1.0,              # [02] tôle inox ép. 1
        "baffle_pitch_mm": 8.0,          # [02] trous Ø2 pas 8 en quinconce
        "baffle_holes_full": False,      # True : perforation réelle (~3 270 trous, lent)
        "baffle_edge_gap_mm": 1.0,
        "inlet_d_mm": 80.0,              # [02] conduit Ø80 central par le fond
        "deflector_t_mm": 2.0,
        "deflector_posts_d_mm": 6.0,
        "deflector_posts_r_mm": 70.0,
        "tap_d_mm": 4.0,                 # [02] 4 piquages Ø4 en chambre de tranquillisation
        "wall_material": "alu",
    },
    "fan": {                             # [02] San Ace 9BMC24P2G001, 97 x 95 x 33, 200 g
        "size_mm": [97.0, 95.0, 33.0],   # face X, face Z, épaisseur Y (axe d'aspiration)
        "outlet_mm": [42.0, 30.0],       # ATTENTION : sortie non documentée (fiche constructeur à lire)
        "outlet_offset_x_mm": -15.0,
        "stub_h_mm": 6.0,
        "wall_mm": 2.0,
        "standoff_mm": 6.0,
        "mass_kg": 0.2,
    },
    "aero": {
        "manchon_len_mm": 100.0,         # [02] manchon souple L100
        "adapter_len_mm": 40.0,          # adaptateur sortie -> Ø50
        "diffuser_half_angle_deg": 3.5,  # [02] 2 theta = 7 deg
        "diffuser_d_in_mm": 50.0,        # [02] Ø50 -> Ø80
        "diffuser_d_out_mm": 80.0,
        "diffuser_len_mm": 0.0,          # 0 = déduit du demi-angle (-> 245,2 mm)
        "diffuser_wall_mm": 2.0,
        "flange_extra_mm": 30.0,         # Ø bride = Ø80 + 30
        "flange_t_mm": 4.0,
        "duct_len_mm": 60.0,             # conduit Ø80 portant la vanne de décharge
        "valve_branch_d_mm": 40.0,       # [02] vanne Ø ~ 40 mm
        "valve_body_mm": 50.0,
        "valve_branch_len_mm": 20.0,
        "valve_exhaust_len_mm": 50.0,
        "bell_flare_r_mm": 20.0,         # buse col Ø30 (profil ISO 5801 approché par un arc)
        "bell_lip_mm": 2.0,
        "suction_tube_wall_mm": 2.0,
        "box_mm": [320.0, 220.0, 320.0],  # [02] caisson d'aspiration 320 x 320 x 220 (X, profondeur Y, Z)
        "box_wall_mm": 3.0,
        "box_front_clear_mm": 20.0,      # dégagement devant le bâti
        "box_floor_clear_mm": 10.0,
        "filter_mm": [287.0, 48.0, 287.0],  # [02] filtre ePM1 287 x 287 x 48
        "window_mm": 283.0,
    },
    "frame": {
        "profile_heavy": "45x90",        # [03] cadre supérieur et montants
        "profile_light": "45x45",        # [03] ceintures, écharpes
        "belt_axis_heights_mm": [150.0, 420.0],   # [03] ceinture basse / étagère (cotes sol)
        "foot_h_mm": 60.0,               # sous les montants (M16 + patin)
        "foot_stud_d_mm": 16.0,
        "foot_base_d_mm": 80.0,          # [03] patin Ø80
        "foot_base_t_mm": 10.0,
    },
    "platine": {
        "size_mm": [200.0, 440.0],
        "t_mm": 8.0,
        "plot_d_mm": 25.0,
        "plot_h_mm": 20.0,
        "plot_x_mm": 55.0,
        "traverse_y_mm": 200.0,          # traverses du plot le long de X, calées contre les montants
    },
    "screen": {
        "t_mm": 5.0,                     # [02] parois PMMA 4-6 mm
        "gap_mm": 0.5,                   # parois contre le bord de zone percée
        "lid_t_mm": 20.0,                # couvercle nid d'abeille alu 20 mm
        "lid_mass_kg": 0.5,
    },
    "gantry": {
        "enabled": True,
        "post_offset_mm": 325.0,         # montants libres de part et d'autre du bâti
        "camera_lens_z_mm": 450.0,
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
def support_points(P: dict) -> list[dict]:
    """Appuis Maxwell (3 vés) : [{index, x, y, role, vee_angle}] d'après support.points_mm
    (centre de plaque, +y = arrière) ; l'appui `fixed_point` est le pivot fixe, les autres sont motorisés."""
    S = P["support"]
    out = []
    for i, (x, y) in enumerate(S["points_mm"]):
        out.append({"index": i, "x": float(x), "y": float(y), "vee_angle": float(S["vee_axis_angle_deg"][i]),
                    "role": "pivot" if i == S["fixed_point"] else "verin"})
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


def vee_geometry(P: dict) -> dict:
    """Couplage bille Ø25,4 / 2 rouleaux Ø20 à 90 deg : entraxe et hauteur du centre de bille / axes."""
    S, Fr = P["support"], P["frame"]
    R, r = S["ball_d_mm"] / 2.0, S["roller_d_mm"] / 2.0
    a = math.radians(S["vee_half_angle_deg"])
    return {"half_spacing": (R + r) * math.sin(a), "dz": (R + r) * math.cos(a)}


def levels(P: dict) -> dict:
    """Cotes verticales et positions dérivées des paramètres (mm, repère CAD : plaque z=0 en haut)."""
    pl, pn, fr, A, F = P["plate"], P["plenum"], P["frame"], P["aero"], P["fan"]
    lv, pf, S = P["leveling"], P["platine"], P["support"]
    Z0 = fr["plate_top_height_mm"]
    zc = lambda zd: zd - Z0                         # cotes des notes -> repère CAD
    L: dict = {"Z0": Z0}
    t = pl["thickness_mm"]
    L["plate_top"], L["plate_bot"] = 0.0, -t
    # --- bâti : cadre supérieur (45x90 de chant), montants, ceintures --------------------------------
    kh, kl = fr["profile_heavy"], fr["profile_light"]
    wh, hh = PROFILES[kh]["w"], PROFILES[kh]["h"]        # 45 x 90
    wl = PROFILES[kl]["w"]
    L.update(w_h=wh, h_h=hh, w_l=wl)
    ca = fr["top_ring_axis_half_mm"]                      # demi-côté d'axe du cadre (250)
    L["ca"] = ca
    L["cad_top"] = zc(fr["ring_axis_height_mm"] + hh / 2)  # dessus du cadre (790 -> -110)
    L["cad_bot"] = L["cad_top"] - hh
    L["cad_zc"] = (L["cad_top"] + L["cad_bot"]) / 2
    L["up_x_in"] = ca - wh / 2                            # face intérieure des montants selon x (227,5)
    L["up_y_in"] = ca + wh / 2 - hh                       # 272,5 - 90 = 182,5
    L["up_yc"] = ca + wh / 2 - hh / 2                     # centre des montants selon y (227,5)
    L["foot_top"] = zc(fr["foot_h_mm"])                   # dessous des montants
    L["floor"] = -Z0
    L["up_bot"] = L["floor"] + fr["foot_h_mm"]
    # --- appuis : bille, rouleaux, bloc de vé, tête de vérin -----------------------------------------------
    V = vee_geometry(P)
    L["vee"] = V
    L["ball_zc"] = L["plate_bot"] - pl["ball_center_below_mm"]
    L["roller_z"] = L["ball_zc"] - V["dz"]
    L["block_base"] = L["roller_z"] - S["roller_axis_above_base_mm"]
    L["stack_h"] = L["block_base"] - L["cad_top"]         # vérin à mi-course / rehausse de P0 (~45)
    # --- caisson suspendu à la plaque --------------------------------------------------------------------------
    gk_w, gk_t = pn["gasket_mm"]
    L["gasket_top"], L["gasket_bot"] = L["plate_bot"], L["plate_bot"] - gk_t
    L["wall_top"] = L["gasket_bot"]
    L["cav_half"] = pn["inner_square_mm"] / 2.0
    L["box_half"] = L["cav_half"] + pn["wall_mm"]
    L["cav_top"] = L["plate_bot"]                         # le vide du caisson monte jusqu'à la plaque
    L["floor_top"] = L["plate_bot"] - pn["height_mm"]
    L["box_bot"] = L["floor_top"] - pn["bottom_mm"]
    L["baffle_bot"] = L["floor_top"] + pn["distribution_height_mm"]
    L["baffle_top"] = L["baffle_bot"] + pn["baffle_t_mm"]
    L["media_top"] = L["baffle_top"] + pn["media_t_mm"]
    L["deflector_bot"] = L["floor_top"] + pn["deflector_gap_mm"]
    L["tap_z"] = (L["media_top"] + L["plate_bot"]) / 2.0   # milieu de la chambre de tranquillisation
    # --- chaîne aéraulique (axe z central) -----------------------------------------------------------------------------
    D = diffuser_geometry(P)
    L["dif"] = D
    L["duct_top"] = L["box_bot"]
    L["duct_bot"] = L["duct_top"] - A["duct_len_mm"]
    L["dif_top"] = L["duct_bot"]
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
    L["fan_y_in"] = -F["size_mm"][2] / 2.0                # face d'aspiration du ventilateur
    # aspiration déportée devant le bâti : caisson + filtre + buse col Ø30 + tube
    box_x, box_y, box_z = A["box_mm"]
    L["box_y_rear"] = -(ca + wh / 2 + A["box_front_clear_mm"])        # paroi côté ventilateur
    L["box_y_far"] = L["box_y_rear"] - box_y
    L["box_z0"] = L["floor"] + A["box_floor_clear_mm"]
    L["box_z1"] = L["box_z0"] + box_z
    # --- platine découplée + traverses -------------------------------------------------------------------------------------
    L["pf_top"] = L["cale_bot"]
    L["pf_bot"] = L["pf_top"] - pf["t_mm"]
    L["plot_bot"] = L["pf_bot"] - pf["plot_h_mm"]
    L["trav_top"] = L["plot_bot"]
    L["trav_bot"] = L["trav_top"] - wl
    L["pf_cx"], L["pf_cy"] = L["fan_xc"], 0.0
    # --- ceintures ------------------------------------------------------------------------------------------------------------
    L["belts_z"] = [zc(h) for h in fr["belt_axis_heights_mm"]]
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


def _oriented(shape: cq.Workplane, view: str) -> cq.Workplane:
    """Tourne la forme pour que la vue demandée soit une vue « de dessus » (X droite, Y haut) :
    cadquery choisit lui-même l'axe haut de l'écran pour les directions ≠ +Z."""
    if view == "dessus":
        return shape
    if view == "dessous":       # caméra en -Z (image miroir en Y)
        return shape.rotate((0, 0, 0), (1, 0, 0), 180)
    if view == "droite":        # caméra en +X, Z vers le haut (raw = (y, z))
        return shape.rotate((0, 0, 0), (0, 0, 1), -90).rotate((0, 0, 0), (1, 0, 0), -90)
    if view == "face":          # caméra en -Y, Z vers le haut de l'écran
        return shape.rotate((0, 0, 0), (1, 0, 0), -90)
    if view == "iso":           # caméra en (+X, -Y, +Z), élévation ~35 deg
        return shape.rotate((0, 0, 0), (0, 0, 1), 45).rotate((0, 0, 0), (1, 0, 0), -54.74)
    raise ValueError(view)


def section_compound(parts: list[PartSpec], exclude_groups: tuple = ("option",)) -> cq.Workplane:
    """Coupe par le plan y = 0 : on retire la moitié y < 0 (à regarder depuis -Y avec la vue « face »)."""
    box = cq.Workplane("XY").box(4000, 2000, 4000, centered=(True, False, True)).translate((0, -2000, -400))
    solids = [p.shape.cut(box).val() for p in parts if p.group not in exclude_groups]
    return cq.Workplane("XY").newObject([cq.Compound.makeCompound(solids)])


def export_svg(shape: cq.Workplane, path: Path, view: str = "dessus", size: int = 900, hidden: bool = False):
    """Vue SVG (lignes cachées supprimées) : view = 'dessus' | 'dessous' | 'face' | 'iso'."""
    cq.exporters.export(_oriented(shape, view), str(path), opt={
        "projectionDir": (0, 0, 1), "showHidden": hidden, "width": size, "height": size,
        "marginLeft": 20, "marginTop": 20, "strokeWidth": 0.6, "showAxes": False})


def make_assembly(parts: list[PartSpec], name: str = "table_coussin_air") -> cq.Assembly:
    a = cq.Assembly(name=name)
    for p in parts:
        a.add(p.shape, name=p.name, color=cq.Color(*p.color))
    return a


def svg_to_png(svg: Path, png: Path, dpi: int = 110) -> bool:
    """Rendu PNG d'un SVG de cadquery (chemins M/L uniquement) via matplotlib, sans cairosvg.
    Retourne False si matplotlib est absent."""
    try:
        import re

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.collections import LineCollection
    except Exception:
        return False
    txt = Path(svg).read_text(encoding="utf-8")
    m = re.search(r"scale\(([-\d.eE]+),\s*([-\d.eE]+)\)\s*translate\(([-\d.eE]+),\s*([-\d.eE]+)\)", txt)
    sx, sy, tx, ty = map(float, m.groups()) if m else (1, -1, 0, 0)
    segs = []
    for d in re.findall(r'<path d="([^"]+)"', txt):
        nums = [tuple(map(float, p.split(","))) for p in re.findall(r"[-\d.eE]+,[-\d.eE]+", d)]
        for a, b in zip(nums[:-1], nums[1:]):
            segs.append([((a[0] + tx) * sx, (a[1] + ty) * sy), ((b[0] + tx) * sx, (b[1] + ty) * sy)])
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.add_collection(LineCollection(segs, colors="k", linewidths=0.35))
    ax.autoscale()
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(png, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return True
