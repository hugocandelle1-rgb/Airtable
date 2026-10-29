"""Génère tous les exports CAO dans cad/export/ et le rapport cad/export/rapport_cao.json.

Usage (depuis la racine du dépôt) :
    python3 -m cad.build_all                  # modèle léger (plaque à trous témoins)
    python3 -m cad.build_all --full           # + plaque complète (~5700 trous), avec délai max
    python3 -m cad.build_all --no-svg         # sans les vues SVG (plus rapide)
    python3 -m cad.build_all --set plate.thickness_mm=30 --set plenum.panel_t_mm=6
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import multiprocessing as mp
import time
from datetime import date
from pathlib import Path

import cadquery as cq

from cad import assembly
from cad.common import (EXPORT_DIR, PROFILES, PartSpec, check_interferences, compound_of, cut_list,
                        defaults_used, export_svg, get_params, levels, make_assembly, section_compound,
                        svg_to_png)
from cad.parts import plate as plate_mod
from cad.parts import plenum as plenum_mod

VIEWS = ("dessus", "face", "iso")


def _parse_overrides(items: list[str]) -> dict:
    ov: dict = {}
    for it in items or []:
        key, val = it.split("=", 1)
        try:
            v = ast.literal_eval(val)
        except Exception:
            v = val
        d = ov
        *path, last = key.split(".")
        for k in path:
            d = d.setdefault(k, {})
        d[last] = v
    return ov


def _full_plate_worker(overrides: dict, out_dir: str, q) -> None:
    """Sous-processus : plaque complète -> STEP/STL (permet un délai maximal)."""
    t0 = time.time()
    try:
        P = get_params(overrides)
        w = plate_mod.build_plate(P, "full")
        v = w.val()
        res = {"ok": True, "valid": bool(v.isValid()), "volume_mm3": v.Volume(), "t_build_s": time.time() - t0}
        cq.exporters.export(w, str(Path(out_dir) / "plaque_full.step"))
        res["t_step_s"] = time.time() - t0
        q.put(res)
    except Exception as e:  # pragma: no cover
        q.put({"ok": False, "erreur": repr(e), "t_s": time.time() - t0})


def build_full_plate(overrides: dict, timeout_s: float, out_dir: Path) -> dict:
    q: mp.Queue = mp.Queue()
    pr = mp.Process(target=_full_plate_worker, args=(overrides, str(out_dir), q))
    t0 = time.time()
    pr.start()
    pr.join(timeout_s)
    if pr.is_alive():
        pr.terminate()
        pr.join()
        return {"ok": False, "abandonne": True, "delai_s": timeout_s,
                "note": "génération complète abandonnée (> délai) : le modèle léger est conservé"}
    res = q.get() if not q.empty() else {"ok": False, "erreur": "pas de résultat"}
    res["t_total_s"] = round(time.time() - t0, 1)
    if res.get("ok"):
        res["masse_cad_kg"] = round(res["volume_mm3"] * 1e-9 * get_params(overrides)["plate"]["rho"], 3)
    return res


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true", help="génère aussi la plaque complète (≈5700 trous)")
    ap.add_argument("--full-timeout", type=float, default=600.0, help="délai max plaque complète (s)")
    ap.add_argument("--no-svg", action="store_true")
    ap.add_argument("--out", default=None, help="dossier de sortie (défaut cad/export)")
    ap.add_argument("--no-interference", action="store_true")
    ap.add_argument("--set", action="append", default=[], metavar="section.cle=valeur")
    args = ap.parse_args(argv)

    OUT = Path(args.out) if args.out else EXPORT_DIR
    OUT.mkdir(parents=True, exist_ok=True)
    ov = _parse_overrides(args.set)
    P = get_params(ov)
    L = levels(P)
    T: dict = {}
    t_all = time.time()

    # ---- construction -----------------------------------------------------------------------
    t = time.time()
    parts = assembly.build_parts(P)
    T["construction_pieces_s"] = round(time.time() - t, 2)
    byname = {p.name: p for p in parts}
    plate_part = byname["plaque"]

    # ---- exports FAO plaque -------------------------------------------------------------------
    t = time.time()
    n_csv = plate_mod.export_csv(P, OUT / "plaque_centres_trous.csv")
    dxf = plate_mod.export_dxf(P, OUT / "plaque_trous.dxf")
    T["csv_dxf_plaque_s"] = round(time.time() - t, 2)

    # ---- liste de débit -----------------------------------------------------------------------------
    cl = cut_list(parts)
    with open(OUT / "liste_debit_profiles.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["section", "longueur_mm", "quantite", "longueur_totale_m",
                                          "masse_kg_estimee", "pieces"], delimiter=";")
        w.writeheader()
        w.writerows(cl)

    # ---- STEP / STL des pièces ---------------------------------------------------------------------------
    t = time.time()
    (OUT / "pieces").mkdir(exist_ok=True)
    (OUT / "barres").mkdir(exist_ok=True)
    seen_bars = set()
    n_step = n_stl = 0
    for p in parts:
        if p.profile:
            k = (p.profile["section"], p.profile["length_mm"])
            if k in seen_bars:
                continue
            seen_bars.add(k)
            # barre exportée une fois, le long de Z à l'origine (pièce de débit)
            from cad.common import profile
            bar = profile(k[1], k[0])
            cq.exporters.export(bar, str(OUT / "barres" / f"profile_{k[0]}_L{k[1]:g}.step"))
            n_step += 1
            continue
        if "step" in p.formats:
            cq.exporters.export(p.shape, str(OUT / "pieces" / f"{p.name}.step"))
            n_step += 1
        if "stl" in p.formats:
            cq.exporters.export(p.shape, str(OUT / "pieces" / f"{p.name}.stl"), tolerance=0.05,
                                angularTolerance=0.2)
            n_stl += 1
    T["step_stl_pieces_s"] = round(time.time() - t, 2)

    # ---- assemblage STEP --------------------------------------------------------------------------------------
    t = time.time()
    assy = make_assembly(parts)
    assy.export(str(OUT / "assemblage.step"))
    T["assemblage_step_s"] = round(time.time() - t, 2)

    # ---- vues SVG ----------------------------------------------------------------------------------------------------
    t = time.time()
    svg_done = []
    png_done = []
    if not args.no_svg:
        groups = {
            "plaque": [p for p in parts if p.group == "plaque"],
            "plenum": [p for p in parts if p.group == "plenum"],
            "aero": [p for p in parts if p.group == "aero"],
            "bati": [p for p in parts if p.group in ("bati", "nivellement")],
            "assemblage": parts,
        }
        for gname, gp in groups.items():
            comp = compound_of(gp)
            views = list(VIEWS) + (["dessous"] if gname == "plaque" else [])
            for vname in views:
                tt = time.time()
                f = OUT / f"{gname}_{vname}.svg"
                export_svg(comp, f, vname, size=1000)
                svg_done.append(f.name)
                print(f"  svg {f.name}: {time.time() - tt:.1f}s", flush=True)
        # coupe longitudinale (plan y = 0) du plenum et de l'assemblage
        for gname, gp in (("plenum", groups["plenum"] + [p for p in parts if p.group == "nivellement"]),
                          ("assemblage", parts)):
            f = OUT / f"{gname}_coupe_y0.svg"
            export_svg(section_compound(gp), f, "face", size=1000)
            svg_done.append(f.name)
        # PNG de contrôle (matplotlib) des vues d'assemblage
        for f in sorted(OUT.glob("assemblage_*.svg")):
            if svg_to_png(f, f.with_suffix(".png")):
                png_done.append(f.with_suffix(".png").name)
    T["svg_s"] = round(time.time() - t, 2)

    # ---- vérifications ---------------------------------------------------------------------------------------------------
    t = time.time()
    interf: list = []
    n_tested = 0
    if not args.no_interference:
        interf = check_interferences(parts, P["cad"]["tol_interference_mm3"])
        n_tested = getattr(check_interferences, "last_tested", 0)
    T["interferences_s"] = round(time.time() - t, 2)

    pl = P["plate"]
    hv = plate_mod.plate_hole_volume_mm3(P)
    blank_v = plate_mod.plate_blank(P).val().Volume()
    rho = pl["rho"]
    m_naive = (pl["outer_square_mm"] * 1e-3) ** 2 * pl["thickness_mm"] * 1e-3 * rho
    m_full = (blank_v - hv["v_total_mm3"]) * 1e-9 * rho
    m_light = plate_part.mass(P)
    plate_report = {
        "nb_trous_reseau": hv["n_holes"],
        "nb_trous_dxf_csv": dxf["n_holes"],
        "nb_trous_temoins_modele_leger": pl["witness_holes"],
        "masse_pleine_sans_percage_kg": round(m_naive, 3),
        "masse_plaque_complete_analytique_kg": round(m_full, 3),
        "masse_modele_leger_kg": round(m_light, 3),
        "retrait_trous_kg": round(hv["v_total_mm3"] * 1e-9 * rho, 3),
        "volume_retire_par_trou_mm3": round(hv["v_per_hole_mm3"], 3),
        "zone_percee_mm": P["zones"]["perforated_square_mm"],
    }
    pn = P["plenum"]
    hb = plenum_mod.baffle_hole_centers(P, L)
    cross = (2 * (L["pl_cp"] - pn["panel_t_mm"] / 2 - pn["baffle_edge_gap_mm"])) ** 2 - 4 * (
        (L["pl_cp"] - pn["panel_t_mm"] / 2 - pn["baffle_edge_gap_mm"] - L["pl_open_half"]) ** 2)
    baffle_report = {"nb_trous": len(hb) if pn["baffle_holes"] else 0, "diametre_mm": pn["baffle_hole_d_mm"],
                     "pas_hex_mm": round(plenum_mod.baffle_hole_pitch(P), 2),
                     "taux_ouverture_vise": pn["baffle_open_area"],
                     "taux_ouverture_realise": round(len(hb) * 3.14159265 * (pn["baffle_hole_d_mm"] / 2) ** 2 / cross, 3)}
    # masse d'assemblage : on remplace la plaque légère par la masse complète analytique
    pieces = []
    gm: dict = {}
    total = 0.0
    all_valid = True
    for p in parts:
        valid = bool(p.shape.val().isValid())
        all_valid &= valid
        mass = m_full if p.name == "plaque" else p.mass(P)
        total += mass
        gm[p.group] = gm.get(p.group, 0.0) + mass
        b = p.bbox()
        pieces.append({"nom": p.name, "groupe": p.group, "matiere": p.material,
                       "volume_mm3": round(p.volume_mm3(), 1), "masse_kg": round(mass, 4),
                       "bbox_mm": [round(x, 2) for x in b],
                       "dimensions_mm": [round(b[3] - b[0], 2), round(b[4] - b[1], 2), round(b[5] - b[2], 2)],
                       "valide": valid, "commerce": p.commercial, "profil": p.profile, "note": p.note})
    bbs = [p.bbox() for p in parts]
    abb = [min(b[0] for b in bbs), min(b[1] for b in bbs), min(b[2] for b in bbs),
           max(b[3] for b in bbs), max(b[4] for b in bbs), max(b[5] for b in bbs)]
    sx, sy = P["platine"]["size_mm"]
    fan_x = (L["fan_xc"] - P["fan"]["size_mm"][0] / 2, L["fan_xc"] + P["fan"]["size_mm"][0] / 2)
    checks = {
        "toutes_pieces_valides": all_valid,
        "interferences_nulles": len(interf) == 0,
        "platine_couvre_ventilateur_et_filtre": bool(
            L["pf_cx"] - sx / 2 <= fan_x[0] - 1 and L["pf_cx"] + sx / 2 >= fan_x[1] + 1
            and L["pf_cy"] - sy / 2 <= L["fan_y_min"] and L["pf_cy"] + sy / 2 >= L["fan_y_max"]),
        "traverses_platine_au_dessus_du_cadre_bas": bool(L["trav_pf_bot"] >= L["low_ring_top"]),
        "colonnes_dans_zone_percee": all(abs(s["x"]) < P["zones"]["perforated_square_mm"] / 2
                                         and abs(s["y"]) < P["zones"]["perforated_square_mm"] / 2
                                         for s in plate_mod.support_points(P)),
        "trous_dans_zone_percee_hors_bande_bord": all(
            max(abs(x), abs(y)) <= P["zones"]["perforated_square_mm"] / 2 - pl["edge_band_mm"] + 1e-9
            for x, y in plate_mod.hole_centers(P)),
        "trous_hors_logements_d_appui": all(
            min(((x - s_["x"]) ** 2 + (y - s_["y"]) ** 2) ** 0.5 for s_ in plate_mod.support_points(P))
            > pl["pocket_d_mm"] / 2 + pl["counterbore_d_mm"] / 2
            for x, y in plate_mod.hole_centers(P)),
        "masse_plaque_coherente_avec_pleine": bool(0.9 * m_naive < m_full < m_naive),
        "face_haute_plaque_a_z0": abs(byname['plaque'].bbox()[5]) < 1e-3,
    }

    # ---- plaque complète (option) ----------------------------------------------------------------------------------
    full = None
    if args.full:
        t = time.time()
        full = build_full_plate(ov, args.full_timeout, OUT)
        T["plaque_complete_s"] = round(time.time() - t, 1)

    T["total_s"] = round(time.time() - t_all, 1)
    report = {
        "meta": {"date": str(date.today()), "version_params": P["meta"]["version"], "surcharges": ov,
                 "cadquery": cq.__version__},
        "temps_generation_s": T,
        "plaque": plate_report,
        "plaque_complete": full,
        "tole_perforee": baffle_report,
        "masses_par_groupe_kg": {k: round(v, 3) for k, v in sorted(gm.items())},
        "masse_totale_kg": round(total, 3),
        "boite_englobante_assemblage_mm": [round(x, 1) for x in abb],
        "dimensions_assemblage_mm": [round(abb[3] - abb[0], 1), round(abb[4] - abb[1], 1), round(abb[5] - abb[2], 1)],
        "interferences": {"paires_testees_booleen": n_tested, "tolerance_mm3": P["cad"]["tol_interference_mm3"],
                          "paires_en_interference": interf},
        "verifications": checks,
        "exports": {"step_pieces_et_barres": n_step, "stl": n_stl, "svg": svg_done, "png": png_done,
                    "dxf": "plaque_trous.dxf", "csv_trous": "plaque_centres_trous.csv",
                    "liste_debit": "liste_debit_profiles.csv", "assemblage": "assemblage.step"},
        "liste_debit": cl,
        "profils_catalogue": {k: {kk: v[kk] for kk in ("w", "h", "slot", "kg_m")} for k, v in PROFILES.items()},
        "cotes_derivees_mm": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in L.items() if k != "dif"},
        "diffuseur": {k: round(v, 3) for k, v in L["dif"].items()},
        "defaults_utilises": defaults_used(),
        "pieces": pieces,
    }
    with open(OUT / "rapport_cao.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps({"temps": T, "masse_totale_kg": report["masse_totale_kg"], "masses": report["masses_par_groupe_kg"],
                      "plaque": plate_report, "verifications": checks, "interferences": len(interf)},
                     indent=1, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
