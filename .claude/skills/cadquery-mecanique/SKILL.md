---
name: cadquery-mecanique
description: Bonnes pratiques pour créer des modèles CAO mécaniques paramétriques avec CadQuery (Python) — lecture des paramètres du projet, profilés aluminium, plaques percées de milliers de trous, assemblages, exports STEP/STL/SVG/DXF sans affichage, vérifications géométriques. À utiliser dès qu'il faut produire ou modifier une pièce, un assemblage ou une mise en plan en CAO dans ce dépôt (dossier cad/), même si l'utilisateur dit juste « dessine », « modélise » ou « fais le plan ».
---

# CAO paramétrique avec CadQuery

CadQuery 2.x est installé (`python3 -c "import cadquery"`). Aucun affichage graphique :
tout passe par des exports fichiers.

## Structure attendue dans `cad/`

    cad/
      common.py          # chargement params + helpers (profilés, trous, couleurs)
      parts/<piece>.py   # une fonction build(P) -> cq.Workplane / cq.Assembly par pièce
      assembly.py        # assemblage complet (cq.Assembly) avec couleurs
      build_all.py       # génère tous les exports dans cad/export/
      export/            # STEP, STL, SVG (vues), DXF (plans 2D)

- Lire **toutes** les cotes dans `params/design.toml` (`from calc.common.params import load_params`) ;
  les dérivées (positions d'appuis, nombre de trous) sont calculées dans le script.
- Lancer depuis la racine : `python3 -m cad.build_all`.

## Plaques à milliers de trous (≈ 6000 orifices)

Couper 6000 cylindres un par un est très lent (booléens OCC). Faire :
1. **Modèle « léger »** (par défaut) : la zone percée est représentée par une face
   marquée / quelques trous témoins ; utilisé dans l'assemblage.
2. **Modèle « complet »** (option `--full`) : un seul `pushPoints(pts).hole(d, depth)`
   par diamètre (un booléen composé), ou bien construire un solide « peigne » unique
   de tous les cylindres puis une seule soustraction. Prévoir plusieurs minutes.
3. Pour l'usinage, exporter surtout un **DXF 2D des centres** (cercles) + un CSV des
   coordonnées : c'est ce que le programmeur FAO utilise.

## Profilés aluminium

Modéliser la section réelle simplifiée (contour extérieur + rainures) en extrusion ;
fournir une fonction `profile(length, size=45, slot=10)` ; rapporter la longueur de coupe
dans une liste de débit (CSV) pour la nomenclature.

## Exports

```python
import cadquery as cq
cq.exporters.export(part, "cad/export/plate.step")
cq.exporters.export(part, "cad/export/plate.stl", tolerance=0.05)
cq.exporters.export(part, "cad/export/plate_top.svg", opt={"projectionDir": (0, 0, 1),
                    "showHidden": False, "width": 800, "height": 800})
cq.exporters.export(part.section(), "cad/export/plate_section.dxf")   # coupe 2D
assy.save("cad/export/assembly.step")
```

## Vérifications à faire après chaque génération

- `part.val().isValid()` ; volume et masse (ρ) cohérents avec les notes de calcul ;
- boîte englobante (`BoundingBox()`) = cotes attendues ;
- interférences de l'assemblage : intersection deux à deux des solides voisins de volume nul ;
- rendu PNG des vues (SVG → PNG via `cairosvg` si installé, sinon garder le SVG).
