"""Interface en ligne de commande : python3 -m host.airtable_host [--port PORT] <commande> ...

Exemples (depuis la racine du dépôt) :
  python3 -m host.airtable_host --port /dev/ttyACM0 status
  python3 -m host.airtable_host --port /dev/ttyACM0 table-load            # calc/aero/results/setpoints.json
  python3 -m host.airtable_host --port /dev/ttyACM0 set-mass 5
  python3 -m host.airtable_host --port /dev/ttyACM0 level home --wait
  python3 -m host.airtable_host --port /dev/ttyACM0 level auto on
  python3 -m host.airtable_host --port /dev/ttyACM0 stream --hz 10 --duration 600 -o essai.csv
  python3 -m host.airtable_host --port /dev/ttyACM0 cal-tilt-flip --samples 200 --apply --save     # capteur unique
  python3 -m host.airtable_host --port /dev/ttyACM0 cal-tilt-flip --all --apply --save              # réseau de 4 ADXL355
  python3 -m host.airtable_host --port /dev/ttyACM0 flip-auto --avg-s 20 --apply --save            # retournement motorisé
  python3 -m host.airtable_host --port /dev/ttyACM0 flip-schedule --every-min 30 --count 8 --log flips.csv
  python3 -m host.airtable_host --port /dev/ttyACM0 therm-learn --duration-min 30 --order 1 --save
  python3 -m host.airtable_host --port /dev/ttyACM0 tilt-report --count 100
  python3 -m host.airtable_host slope-export lachers.csv -o carte_pente.json --grid 31x31
  python3 -m host.airtable_host drift-fit lachers.csv --damping fit --fix-v0 0
  python3 -m host.airtable_host --port sim:// status        # simulateur, sans matériel
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .client import AirtableClient
from .logger import CsvLogger, default_log_path
from .protocol import DeviceError

DEFAULT_SETPOINTS = Path("calc/aero/results/setpoints.json")


def _pp(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _connect(args) -> AirtableClient:
    if not args.port:
        raise SystemExit("port série requis : --port /dev/ttyACM0 (ou variable AIRTABLE_PORT, ou sim://)")
    return AirtableClient(port=args.port, baud=args.baud, timeout=args.timeout)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m host.airtable_host", description=__doc__.split("\n")[0])
    p.add_argument("--port", default=os.environ.get("AIRTABLE_PORT"), help="port série, ou sim://")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--timeout", type=float, default=3.0, help="délai de réponse [s]")
    p.add_argument("--version", action="version", version=f"airtable_host {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("status", "ping", "version", "config", "safe", "clear", "save", "fan-off"):
        sub.add_parser(name)
    sp = sub.add_parser("set-pressure")
    sp.add_argument("pa", type=float, help="consigne de pression plenum [Pa]")
    sm = sub.add_parser("set-mass")
    sm.add_argument("grams", type=float, help="masse du palet [g] (table masse→pression)")
    sd = sub.add_parser("set-duty")
    sd.add_argument("duty", type=float, help="rapport cyclique 0..1 (boucle ouverte)")

    lv = sub.add_parser("level", help="nivellement")
    ls = lv.add_subparsers(dest="level_cmd", required=True)
    la = ls.add_parser("auto")
    la.add_argument("state", choices=["on", "off"])
    lm = ls.add_parser("move")
    lm.add_argument("axis", choices=["X", "Y", "x", "y"])
    lm.add_argument("urad", type=float, help="variation de pente dz/d(axe) [µrad]")
    ls.add_parser("zero")
    lh = ls.add_parser("home")
    lh.add_argument("--wait", action="store_true", help="attend la fin de la prise d'origine")
    ls.add_parser("stop")
    lt = ls.add_parser("target")
    lt.add_argument("x", type=float)
    lt.add_argument("y", type=float)

    tl = sub.add_parser("table-load", help="envoie la table masse→pression au firmware")
    tl.add_argument("path", nargs="?", default=str(DEFAULT_SETPOINTS))

    st = sub.add_parser("stream", help="télémétrie en flux, journalisée en CSV")
    st.add_argument("--hz", type=float, default=10.0)
    st.add_argument("--duration", type=float, default=None, help="durée [s] (horloge du firmware)")
    st.add_argument("--count", type=int, default=None, help="nombre de trames")
    st.add_argument("-o", "--output", default=None, help="fichier CSV (défaut : airtable_AAAAMMJJ_HHMMSS.csv)")
    st.add_argument("--quiet", action="store_true")

    cf = sub.add_parser("cal-tilt-flip", help="calibration de l'inclinomètre par retournement de 180°")
    cf.add_argument("--samples", type=int, default=100, help="échantillons par position (10 Hz)")
    cf.add_argument("--hz", type=float, default=10.0)
    cf.add_argument("--no-return", action="store_true", help="sans série de retour A2 (contrôle de dérive)")
    cf.add_argument("--apply", action="store_true", help="envoie CAL TILT BIAS si le résultat est fiable")
    cf.add_argument("--save", action="store_true", help="avec --apply : SAVE (mémoire non volatile)")
    cf.add_argument("--sensor", type=int, default=None, help="capteur du réseau (0…3) ; défaut : capteur unique")
    cf.add_argument("--all", action="store_true", help="retourne simultanément les capteurs du réseau (--sensors)")
    cf.add_argument("--sensors", default="0,1,2,3", help="liste des capteurs avec --all, ex. 0,1,2,3")

    fa = sub.add_parser("flip-auto", help="retournement 180° MOTORISÉ du capteur 0 (FLIP RUN)")
    fa.add_argument("--avg-s", type=float, default=None, help="durée de mesure par position [s] (défaut firmware : 20)")
    fa.add_argument("--apply", action="store_true", help="FLIP APPLY si le résultat est fiable")
    fa.add_argument("--save", action="store_true", help="avec --apply : SAVE")
    fs = sub.add_parser("flip-schedule", help="planifie des retournements motorisés périodiques (suivi du biais vs T)")
    fs.add_argument("--every-min", type=float, required=True, help="période [min], début à début")
    fs.add_argument("--count", type=int, required=True)
    fs.add_argument("--avg-s", type=float, default=None)
    fs.add_argument("--apply", action="store_true")
    fs.add_argument("--save", action="store_true")
    fs.add_argument("--log", default=None, help="CSV de suivi (ajouté à chaque retournement)")

    tl2 = sub.add_parser("therm-learn", help="apprentissage thermique du zéro de chaque capteur (CAL TILT THERM)")
    tl2.add_argument("--duration-min", type=float, default=30.0, help="durée d'acquisition pendant la variation de température")
    tl2.add_argument("--order", type=int, choices=[1, 2], default=1)
    tl2.add_argument("--sensor", type=int, default=None)
    tl2.add_argument("--save", action="store_true")
    tr2 = sub.add_parser("tilt-report", help="pentes par capteur, fusion, écart inter-capteurs (déformation)")
    tr2.add_argument("--count", type=int, default=50, help="trames moyennées")
    tr2.add_argument("--hz", type=float, default=10.0)

    se = sub.add_parser("slope-export", help="carte de pente / efforts parasites (JSON ou CSV) pour les robots")
    se.add_argument("csv", help="trajectoires de palets (comme drift-fit)")
    se.add_argument("-o", "--output", default="carte_pente.json")
    se.add_argument("--format", choices=["json", "csv", "both"], default="json")
    se.add_argument("--grid-out", default="31x31", help="grille de sortie, ex. 31x31")
    se.add_argument("--source", choices=["auto", "field", "map"], default="auto")
    se.add_argument("--plane", choices=["raw", "corrected"], default="raw",
                    help="corrected : après correction du plan moyen calculée par l'analyse")
    se.add_argument("--extent", default=None, help="x0,x1,y0,y1 en mm (défaut : zone de travail du design)")
    se.add_argument("--fps", type=float, default=None)
    se.add_argument("--scale", type=float, default=1.0)
    se.add_argument("--damping", default="fit")
    se.add_argument("--fix-v0", type=float, default=None)
    se.add_argument("--sigma-pos", type=float, default=None)
    se.add_argument("--poly-order", type=int, default=3)
    se.add_argument("--rot", type=float, default=0.0)
    se.add_argument("--flip-x", action="store_true")
    se.add_argument("--flip-y", action="store_true")

    df = sub.add_parser("drift-fit", help="calibration par palets lâchés (trajectoires CSV)")
    df.add_argument("csv")
    df.add_argument("--fps", type=float, default=None, help="si le temps est un numéro d'image")
    df.add_argument("--scale", type=float, default=1.0, help="facteur appliqué à x,y pour obtenir des mm")
    df.add_argument("--damping", default="fit", help="none | fit | τ en secondes")
    df.add_argument("--fix-v0", type=float, default=None, help="vitesse initiale imposée [mm/s] (0 = lâcher au repos)")
    df.add_argument("--sigma-pos", type=float, default=None, help="bruit de position connu [mm]")
    df.add_argument("--t-min", type=float, default=None)
    df.add_argument("--t-max", type=float, default=None)
    df.add_argument("--grid", default="5x5", help="grille de la carte, ex. 5x5")
    df.add_argument("--poly-order", type=int, default=3)
    df.add_argument("--criterion", choices=["mean", "peak"], default="mean")
    df.add_argument("--rot", type=float, default=0.0, help="rotation caméra → plaque [deg]")
    df.add_argument("--flip-x", action="store_true")
    df.add_argument("--flip-y", action="store_true")
    df.add_argument("--send", choices=["none", "move", "target"], default="none",
                    help="envoie la correction au banc (LEVEL MOVE ou LEVEL TARGET)")
    df.add_argument("--yes", action="store_true", help="ne pas demander de confirmation avant --send")

    tr = sub.add_parser("drift-track", help="détection de palets sur vidéo (OpenCV requis)")
    tr.add_argument("video")
    tr.add_argument("--mm-per-px", type=float, required=True)
    tr.add_argument("--dark-pucks", action="store_true")
    tr.add_argument("-o", "--output", default="trajectoires.csv")
    return p


def _drift_fit(args) -> int:
    from . import drift_calibration as dc
    trajs = dc.load_trajectories_csv(args.csv, fps=args.fps, scale=args.scale)
    try:
        damping: str | float = float(args.damping)
    except ValueError:
        damping = args.damping
    nx, ny = (int(v) for v in args.grid.lower().split("x"))
    frame = dc.CameraFrame(args.rot, args.flip_x, args.flip_y)
    an = dc.analyze(trajs, damping=damping, fix_v0=args.fix_v0, grid=(nx, ny), poly_order=args.poly_order,
                    criterion=args.criterion, sigma_pos_mm=args.sigma_pos, t_min=args.t_min, t_max=args.t_max,
                    frame=frame)
    print(dc.format_report(an))
    if args.send == "none":
        return 0
    cmds = an.correction.level_move_commands()
    with _connect(args) as c:
        if args.send == "target":
            base = c.config().get("target", [0.0, 0.0])
            cmds = [an.correction.level_target_command((float(base[0]), float(base[1])))]
        print("à envoyer : " + " ; ".join(cmds))
        if not args.yes and input("confirmer ? [o/N] ").strip().lower() not in ("o", "oui", "y", "yes"):
            print("annulé")
            return 1
        for line in cmds:
            _pp(c.command(line))
    return 0


def _slope_export(args) -> int:
    from . import drift_calibration as dc
    from . import slope_export as se
    trajs = dc.load_trajectories_csv(args.csv, fps=args.fps, scale=args.scale)
    try:
        damping: str | float = float(args.damping)
    except ValueError:
        damping = args.damping
    extent = tuple(float(v) for v in args.extent.split(",")) if args.extent else None
    an = dc.analyze(trajs, damping=damping, fix_v0=args.fix_v0, poly_order=args.poly_order, extent_mm=extent,
                    sigma_pos_mm=args.sigma_pos, frame=dc.CameraFrame(args.rot, args.flip_x, args.flip_y))
    nx, ny = (int(v) for v in args.grid_out.lower().split("x"))
    grid = se.build_slope_grid(an, nx, ny, extent, source=args.source, plane=args.plane)
    for p in se.export(grid, args.output, args.format):
        print(f"écrit : {p}")
    st = grid.stats()
    print(f"source {grid.source}, plan {grid.plane}, {st.get('n_valid', 0)} points valides ; "
          f"pente rms {st.get('theta_rms_urad', float('nan')):.1f} µrad, crête {st.get('theta_peak_urad', float('nan')):.1f} µrad ; "
          f"accélération crête {st.get('a_peak_mm_s2', float('nan')):.3f} mm/s²")
    for w in grid.warnings:
        print("AVERTISSEMENT : " + w)
    return 0


def _tilt_report(c, args) -> int:
    import numpy as np
    from .tilt_calibration import DEFAULT_POSITIONS_MM, fit_slope_field
    rows = []
    for fr in c.stream(args.hz, count=args.count):
        tc = fr.get("tc")
        if tc and all(v is not None for v in tc):
            rows.append(tc)
    if not rows:
        print("aucune trame valide (capteurs absents ou invalides)")
        return 1
    m = np.mean(np.array(rows, float), axis=0).reshape(-1, 2)
    sd = np.std(np.array(rows, float), axis=0, ddof=1).reshape(-1, 2) if len(rows) > 1 else np.zeros_like(m)
    for i, (v, s_) in enumerate(zip(m, sd)):
        print(f"capteur {i} : pente plaque ({v[0]:+8.2f}, {v[1]:+8.2f}) µrad   bruit 10 Hz ({s_[0]:.2f}, {s_[1]:.2f})")
    print(f"écart inter-capteurs (max − min) : X {np.ptp(m[:, 0]):.2f}  Y {np.ptp(m[:, 1]):.2f} µrad")
    if len(m) >= 3:
        f = fit_slope_field([DEFAULT_POSITIONS_MM[i] for i in range(len(m))], [tuple(v) for v in m])
        print(f"courbure zxx = {f.zxx:+.1f}  zxy = {f.zxy:+.1f}  zyy = {f.zyy:+.1f} µrad/m ; rotationnel {f.curl:+.1f} "
              f"(≠ 0 : erreur de montage ou capteur défaillant)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "drift-fit":
            return _drift_fit(args)
        if args.cmd == "slope-export":
            return _slope_export(args)
        if args.cmd == "drift-track":
            from . import drift_calibration as dc
            trajs = dc.track_pucks_video(args.video, args.mm_per_px, dark_pucks=args.dark_pucks,
                                         progress=lambda n: print(f"  {n} images", file=sys.stderr))
            dc.write_trajectories_csv(args.output, trajs)
            print(f"{len(trajs)} trajectoires écrites dans {args.output}")
            return 0

        with _connect(args) as c:
            if args.cmd == "status":
                _pp(c.status())
            elif args.cmd == "ping":
                _pp(c.ping())
            elif args.cmd == "version":
                _pp(c.version())
            elif args.cmd == "config":
                _pp(c.config())
            elif args.cmd == "safe":
                _pp(c.safe())
            elif args.cmd == "clear":
                _pp(c.clear())
            elif args.cmd == "save":
                _pp(c.save())
            elif args.cmd == "fan-off":
                _pp(c.fan_off())
            elif args.cmd == "set-pressure":
                _pp(c.set_pressure(args.pa))
            elif args.cmd == "set-mass":
                _pp(c.set_mass(args.grams))
            elif args.cmd == "set-duty":
                _pp(c.set_duty(args.duty))
            elif args.cmd == "table-load":
                n = c.load_setpoints(args.path)
                print(f"{n} points chargés depuis {args.path}")
            elif args.cmd == "level":
                lc = args.level_cmd
                if lc == "auto":
                    _pp(c.level_auto(args.state == "on"))
                elif lc == "move":
                    _pp(c.level_move(args.axis, args.urad))
                elif lc == "zero":
                    _pp(c.level_zero())
                elif lc == "home":
                    _pp(c.level_home())
                    if args.wait:
                        c.wait_homed()
                        print("prise d'origine terminée")
                elif lc == "stop":
                    _pp(c.level_stop())
                elif lc == "target":
                    _pp(c.level_target(args.x, args.y))
            elif args.cmd == "stream":
                path = args.output or default_log_path()
                n = 0
                with CsvLogger(path) as log:
                    try:
                        for fr in c.stream(args.hz, args.duration, args.count):
                            log.write(fr)
                            n += 1
                            if not args.quiet and n % max(1, int(args.hz)) == 0:
                                pm = fr.get("pm")
                                print(f"t={fr['t']/1000:8.1f} s  p={pm}  rpm={fr.get('rpm')}  tilt={fr.get('tilt')}",
                                      file=sys.stderr)
                    except KeyboardInterrupt:
                        pass
                print(f"{n} trames écrites dans {path}")
            elif args.cmd == "cal-tilt-flip":
                from .tilt_calibration import run_array_flip_procedure, run_flip_procedure
                if args.all:
                    sensors = tuple(int(v) for v in args.sensors.split(","))
                    run_array_flip_procedure(c, prompt=lambda m: input(m + " "), sensors=sensors, n_samples=args.samples,
                                             hz=args.hz, with_return=not args.no_return, apply=args.apply, save=args.save)
                else:
                    run_flip_procedure(c, prompt=lambda m: input(m + " "), n_samples=args.samples, hz=args.hz,
                                       with_return=not args.no_return, apply=args.apply, save=args.save,
                                       sensor=args.sensor)
            elif args.cmd == "flip-auto":
                from .tilt_calibration import run_motorized_flip
                run_motorized_flip(c, args.avg_s, apply=args.apply, save=args.save)
            elif args.cmd == "flip-schedule":
                from .tilt_calibration import schedule_flips
                rows = schedule_flips(c, args.every_min * 60.0, args.count, args.avg_s, apply=args.apply,
                                      save=args.save, log_path=args.log)
                print(f"{sum(1 for r in rows if r.get('ok'))}/{len(rows)} retournements réussis")
            elif args.cmd == "therm-learn":
                c.therm_start()
                print(f"apprentissage en cours ({args.duration_min:g} min) : faire varier la température des embases "
                      "(plaque immobile, nivellement automatique arrêté) ...")
                for fr in c.stream(1.0, duration_s=args.duration_min * 60.0):
                    pass
                rep = c.therm_fit(args.order, args.sensor)
                for r in rep.get("fit", []):
                    print(f"capteur {int(r[0])} : c1 = ({r[1]:+.2f}, {r[2]:+.2f}) µrad/K  c2 = ({r[3]:+.3f}, {r[4]:+.3f}) "
                          f"µrad/K²  résidu rms ({r[5]:.2f}, {r[6]:.2f}) µrad  excursion {r[7]:.1f} K")
                if args.save:
                    c.save()
                    print("SAVE : coefficients en mémoire non volatile")
            elif args.cmd == "tilt-report":
                return _tilt_report(c, args)
    except DeviceError as e:
        print(f"erreur du firmware : {e.err}", file=sys.stderr)
        return 2
    except (TimeoutError, FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2
    return 0
