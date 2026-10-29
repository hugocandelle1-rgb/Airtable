"""Interface en ligne de commande : python3 -m host.airtable_host [--port PORT] <commande> ...

Exemples (depuis la racine du dépôt) :
  python3 -m host.airtable_host --port /dev/ttyACM0 status
  python3 -m host.airtable_host --port /dev/ttyACM0 table-load            # calc/aero/results/setpoints.json
  python3 -m host.airtable_host --port /dev/ttyACM0 set-mass 5
  python3 -m host.airtable_host --port /dev/ttyACM0 level home --wait
  python3 -m host.airtable_host --port /dev/ttyACM0 level auto on
  python3 -m host.airtable_host --port /dev/ttyACM0 stream --hz 10 --duration 600 -o essai.csv
  python3 -m host.airtable_host --port /dev/ttyACM0 cal-tilt-flip --samples 200 --apply --save
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "drift-fit":
            return _drift_fit(args)
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
                from .tilt_calibration import run_flip_procedure
                run_flip_procedure(c, prompt=lambda m: input(m + " "), n_samples=args.samples, hz=args.hz,
                                   with_return=not args.no_return, apply=args.apply, save=args.save)
    except DeviceError as e:
        print(f"erreur du firmware : {e.err}", file=sys.stderr)
        return 2
    except (TimeoutError, FileNotFoundError, ValueError, RuntimeError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 2
    return 0
