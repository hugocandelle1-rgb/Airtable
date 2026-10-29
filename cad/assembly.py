"""Assemblage complet (cq.Assembly avec couleurs).

    python3 -m cad.assembly      # écrit cad/export/assemblage.step et affiche un résumé

Toutes les pièces sont construites directement dans le repère global (origine = centre de la
face supérieure de la plaque, Z vers le haut) : pas de contraintes, donc positions exactes.
"""
from __future__ import annotations

import cadquery as cq

from cad.common import EXPORT_DIR, PartSpec, get_params, make_assembly
from cad.parts import aero, frame, leveling, plate, plenum


def build_parts(P: dict, plate_mode: str = "light") -> list[PartSpec]:
    """Liste de toutes les pièces (plaque, plenum, chaîne aéraulique, nivellement, bâti, options)."""
    parts: list[PartSpec] = []
    for mod in (plate, plenum, aero, leveling, frame):
        parts += mod.build(P, plate_mode) if mod is plate else mod.build(P)
    names = [p.name for p in parts]
    assert len(names) == len(set(names)), "noms de pièces dupliqués"
    return parts


def build(P: dict | None = None) -> cq.Assembly:
    P = P or get_params()
    return make_assembly(build_parts(P))


if __name__ == "__main__":
    P = get_params()
    parts = build_parts(P)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    make_assembly(parts).export(str(EXPORT_DIR / "assemblage.step"))
    print(len(parts), "pièces ->", EXPORT_DIR / "assemblage.step")
