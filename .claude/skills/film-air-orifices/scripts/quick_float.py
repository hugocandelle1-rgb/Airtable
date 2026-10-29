#!/usr/bin/env python3
"""Estimation rapide de la flottaison d'un palet sur une plaque à orifices.

Modèle axisymétrique à source répartie (voir SKILL.md § 2) avec loi d'orifice
mixte laminaire + pertes singulières. Sert de vérification d'ordre de grandeur ;
la note de calcul détaillée est dans calc/aero/.

Exemple :
    python3 quick_float.py --d 0.4 --L 1.0 --pitch 5 --pattern hex \
        --ps 50 100 200 300 --mass 2 5 10
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy.integrate import solve_bvp
from scipy.optimize import brentq

MU, RHO, G = 1.81e-5, 1.204, 9.81


def q_hole(dp, d, L, K=1.5):
    """Débit (m³/s) d'un trou de diamètre d et longueur L sous Δp (Pa)."""
    area = np.pi * d**2 / 4
    r_lam = 128 * MU * L / (np.pi * d**4)
    a = K * RHO / 2 / area**2
    dp = np.maximum(dp, 0.0)
    return (-r_lam + np.sqrt(r_lam**2 + 4 * a * dp)) / (2 * a)


def hole_density(pitch, pattern):
    return 2 / (np.sqrt(3) * pitch**2) if pattern == "hex" else 1 / pitch**2


def load(h, ps, d, L, n, R):
    """Portance (N) pour un entrefer h (m) et une pression plenum ps (Pa)."""
    c = h**3 / (12 * MU)

    def f(r, y):
        p, dp = y
        src = n * q_hole(ps - p, d, L)
        rr = np.where(r < 1e-9, 1e-9, r)
        d2p = np.where(r < 1e-9, -src / (2 * c), -src / c - dp / rr)
        return np.vstack([dp, d2p])

    r = np.linspace(0, R, 200)
    guess = np.vstack([ps * (1 - (r / R) ** 2), -2 * ps * r / R**2])
    sol = solve_bvp(f, lambda ya, yb: np.array([ya[1], yb[0]]), r, guess,
                    tol=1e-6, max_nodes=20000)
    p = sol.sol(r)[0]
    return np.trapezoid(2 * np.pi * r * p, r)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--d", type=float, default=0.4, help="Ø orifice (mm)")
    ap.add_argument("--L", type=float, default=1.0, help="longueur orifice (mm)")
    ap.add_argument("--pitch", type=float, default=5.0, help="pas (mm)")
    ap.add_argument("--pattern", choices=["hex", "square"], default="hex")
    ap.add_argument("--D", type=float, default=30.0, help="Ø palet (mm)")
    ap.add_argument("--ps", type=float, nargs="+", default=[50, 100, 200, 300])
    ap.add_argument("--mass", type=float, nargs="+", default=[2, 5, 10], help="g")
    ap.add_argument("--area", type=float, default=360.0,
                    help="côté de la zone percée (mm) pour le débit total")
    a = ap.parse_args()

    d, L, pitch, R = a.d * 1e-3, a.L * 1e-3, a.pitch * 1e-3, a.D * 0.5e-3
    n = hole_density(pitch, a.pattern)
    n_total = n * (a.area * 1e-3) ** 2
    print(f"trous sous le palet ≈ {n * np.pi * R**2:.0f} ; trous zone percée ≈ {n_total:.0f}")
    for ps in a.ps:
        q = q_hole(ps, d, L)
        cells = []
        for m in a.mass:
            w = m * 1e-3 * G
            try:
                h = brentq(lambda hh: load(hh, ps, d, L, n, R) - w, 3e-6, 1.5e-3, xtol=1e-8)
                cells.append(f"{m:g} g: h={h * 1e6:5.0f} µm")
            except ValueError:
                cells.append(f"{m:g} g: ne flotte pas")
        print(f"ps={ps:5.0f} Pa  Q_tot={q * n_total * 3600:5.1f} m³/h | " + " | ".join(cells))


if __name__ == "__main__":
    main()
