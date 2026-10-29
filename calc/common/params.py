"""Chargement des paramètres de conception (params/design.toml).

Usage :
    from calc.common.params import load_params, REPO_ROOT
    P = load_params()
    d = P["plate"]["orifice_d_mm"] * 1e-3

Les scripts doivent être lancés depuis la racine du dépôt :
    python3 -m calc.aero.film_model
ou bien directement (le chemin racine est ajouté automatiquement).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PARAMS_FILE = REPO_ROOT / "params" / "design.toml"


def load_params(path: Path | str | None = None) -> dict:
    """Retourne le dictionnaire des paramètres (lecture seule par convention)."""
    p = Path(path) if path else PARAMS_FILE
    with open(p, "rb") as f:
        return tomllib.load(f)


if __name__ == "__main__":
    import json
    print(json.dumps(load_params(), indent=2, ensure_ascii=False))
