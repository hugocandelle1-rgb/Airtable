"""Chaîne complète des calculs aérauliques (ordre imposé par les dépendances).

orifice → optimize → setpoints → cogging → montecarlo → dynamics → network → jets → thermal
→ drift_sim → parasitic

- optimize écrit results/recommended_hole.json (configuration de perçage) ;
- setpoints écrit results/setpoints.json (loi h(m), table ps(m), enveloppe) lu
  par cogging, montecarlo, dynamics, network, jets, thermal.

Chaque étape est lancée dans un sous-processus (BLAS mono-thread) et chronométrée ;
une étape dépassant 5 min est signalée. Durée totale ≈ 6 min sur 4 cœurs.
Lancement : ``python3 -m calc.aero.run_all`` (``--skip-optimize`` pour réutiliser
results/recommended_hole.json).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from calc.aero.common import REPO_ROOT, save_json

STEPS = ["orifice", "optimize", "setpoints", "cogging", "montecarlo", "dynamics", "network",
         "jets", "thermal", "drift_sim", "parasitic"]
LIMIT_S = 300.0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    steps = [s for s in STEPS if not ("--skip-optimize" in argv and s == "optimize")]
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    log = []
    t0 = time.time()
    for s in steps:
        t = time.time()
        print(f"=== calc.aero.{s}", flush=True)
        r = subprocess.run([sys.executable, "-m", f"calc.aero.{s}"], cwd=REPO_ROOT, env=env,
                           capture_output=True, text=True)
        dt = time.time() - t
        tail = (r.stdout or "").strip().splitlines()[-3:]
        for line in tail:
            print("   ", line)
        log.append(dict(step=s, seconds=dt, returncode=r.returncode, over_limit=dt > LIMIT_S))
        print(f"    → {dt:.0f} s, code {r.returncode}{'  [> 5 min]' if dt > LIMIT_S else ''}", flush=True)
        if r.returncode != 0:
            print(r.stderr[-3000:], file=sys.stderr)
            save_json("run_all.json", dict(steps=log, ok=False, total_s=time.time() - t0))
            sys.exit(f"échec de calc.aero.{s}")
    ok = all(not x["over_limit"] for x in log)
    save_json("run_all.json", dict(steps=log, ok=ok, total_s=time.time() - t0))
    print(f"Terminé en {time.time()-t0:.0f} s ; toutes les étapes < 5 min : {ok}")


if __name__ == "__main__":
    main()
