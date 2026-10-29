#!/usr/bin/env python3
"""Génère firmware/include/design_params.h à partir de params/design.toml.

Le firmware ne doit jamais recopier une valeur de conception en dur (règle 1 du projet) :
cet en-tête est la seule passerelle entre `params/design.toml` et le code embarqué.

Usage (depuis la racine du dépôt) :
    python3 firmware/tools/gen_design_params.py            # (ré)écrit l'en-tête
    python3 firmware/tools/gen_design_params.py --check    # code retour 1 si périmé
"""
from __future__ import annotations

import math
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "params" / "design.toml"
DST = ROOT / "firmware" / "include" / "design_params.h"


def render(p: dict) -> str:
    op, fan, puck = p["operating"], p["fan"], p["puck"]
    perf, env = p["performance_targets"], p["environment"]
    rng_urad = math.radians(perf["leveling_range_deg"]) * 1e6
    lines = [
        "// GÉNÉRÉ par firmware/tools/gen_design_params.py depuis params/design.toml — NE PAS ÉDITER.",
        f"// params/design.toml : version {p['meta']['version']} ({p['meta']['date']})",
        "#pragma once",
        "",
        "// Plage de pression plenum de consigne [Pa]",
        f"#define DESIGN_P_MIN_PA            {op['p_plenum_min_Pa']:.1f}f",
        f"#define DESIGN_P_MAX_PA            {op['p_plenum_max_Pa']:.1f}f",
        f"#define DESIGN_P_REGULATION_PA     {perf['pressure_regulation_Pa']:.2f}f   // stabilité visée",
        "// Ventilateur(s)",
        f"#define DESIGN_FAN_COUNT           {int(fan['count'])}",
        f"#define DESIGN_FAN_PWM_HZ          {int(fan['pwm_freq_Hz'])}",
        "// Palets",
        f"#define DESIGN_PUCK_MASS_MIN_G     {puck['mass_min_g']:.2f}f",
        f"#define DESIGN_PUCK_MASS_MAX_G     {puck['mass_max_g']:.2f}f",
        "// Nivellement",
        f"#define DESIGN_LEVEL_RES_URAD      {perf['leveling_resolution_urad']:.2f}f",
        f"#define DESIGN_LEVEL_RANGE_URAD    {rng_urad:.1f}f   // course ± ({perf['leveling_range_deg']} deg)",
        f"#define DESIGN_SLOPE_PEAK_URAD     {perf['residual_slope_peak_urad']:.1f}f",
        f"#define DESIGN_TILT_STABILITY_URAD {perf['tilt_stability_1h_urad']:.1f}f",
        f"#define DESIGN_THERMAL_GRADIENT_K  {perf['thermal_gradient_K']:.3f}f",
        "// Air",
        f"#define DESIGN_AIR_RHO             {env['air_rho']:.4f}f",
        f"#define DESIGN_G                   {env['g']:.3f}f",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    with open(SRC, "rb") as f:
        text = render(tomllib.load(f))
    if "--check" in sys.argv:
        ok = DST.exists() and DST.read_text() == text
        print("design_params.h à jour" if ok else "design_params.h PÉRIMÉ : relancer le générateur")
        return 0 if ok else 1
    DST.write_text(text)
    print(f"écrit {DST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
