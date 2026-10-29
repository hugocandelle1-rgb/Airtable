---
name: film-air-orifices
description: Physique et règles de dimensionnement des tables à coussin d'air et paliers à air à orifices — débit d'un orifice court, film d'air sous un palet (portance, raideur, entrefer), choix du diamètre/pas des trous, débit total, uniformité du plenum, diffuseurs, marteau pneumatique, jets libres. À utiliser pour tout calcul ou choix concernant des trous de soufflage, un plenum, un ventilateur de table à air, la flottaison d'un objet sur film d'air, ou pour vérifier une note de calcul aéraulique, même si la demande parle simplement de « faire flotter » ou « coussin d'air ».
---

# Film d'air et orifices — mémo de dimensionnement

## 1. Débit d'un trou court (orifice calibré)

Pour d = 0,3–0,6 mm, L/d = 1–5, Re = 100–2000 : régime mixte laminaire + pertes singulières.

    Δp = R_lam·q + K·(ρ/2)·(q/A)²      R_lam = 128·μ·L/(π·d⁴),  A = π·d²/4
    K ≈ 1,5 (entrée vive 0,5 + sortie 1,0), ajouter le terme de développement si L/d < 0,06·Re

Résolution : q = (−R_lam + √(R_lam² + 4aΔp)) / (2a), a = Kρ/(2A²).
Ordre de grandeur : d = 0,4 mm, L = 1 mm, Δp = 250 Pa → q ≈ 1,8·10⁻⁶ m³/s.
Compressibilité négligeable sous 1 kPa (Δp/p ≈ 1 %).

## 2. Film d'air sous un palet de rayon R (modèle à source répartie)

    (h³/12μ)·(1/r)·d/dr(r·dp/dr) = −n·q(ps − p),   p'(0) = 0,  p(R) = 0,  n = densité de trous (1/m²)

Portance W = ∫ 2πr·p dr ; équilibre W = m·g → entrefer h. Raideur k_z = −dW/dh.
Avec q linéaire, solution exacte : p = ps·[1 − I0(λr)/I0(λR)], λ² = 12μn/(h³R_h),
W = ps·πR²·[1 − 2·I1(λR)/(λR·I0(λR))].
Outil prêt à l'emploi : `python3 .claude/skills/film-air-orifices/scripts/quick_float.py --help`.

Seuil de décollage : ps > W/A (27,7 Pa pour 2 g, 139 Pa pour 10 g, Ø30 mm).
Plus ps augmente, plus h augmente (débit sous le palet ↑) ; le débit est imposé par
les trous, la pression par la masse.

## 3. Règles de conception éprouvées

- **Restriction en face supérieure** (orifice dans un voile mince, lamage par-dessous) :
  volume aval minimal ⇒ pas de marteau pneumatique ; la bavure de sortie tombe dans le lamage.
- **≥ 30 trous sous le palet** (pas ≤ 5 mm pour Ø30) pour lisser le crantage ; maille
  hexagonale plus isotrope que carrée.
- **Uniformité de plenum** : rapport (Δp orifices) / (pression dynamique dans le plenum)
  > 100 ⇒ non-uniformité < 1 %. Vitesse dans le plenum < 0,5 m/s.
- Ne jamais laisser le jet du ventilateur frapper la plaque : diffuseur (demi-angle ≤ 7°
  conique, ou entrée radiale + disque déflecteur) puis tôle perforée K ≈ 3–10 et chambre
  de tranquillisation.
- Courbe réseau quadratique (orifices) ⇒ le ventilateur reste au même point relatif de sa
  courbe quand on module la vitesse (lois de similitude : Q ∝ N, p ∝ N²). Plage de
  pression 1:10 ⇒ plage de vitesse 1:3,2 ; vérifier la vitesse PWM minimale.
- Filtrer l'air à l'aspiration : un orifice de 0,4 mm bouché crée un défaut de portance local.
- Isoler le ventilateur (manchon souple, plots) : la chaleur et les vibrations ne doivent
  pas atteindre la plaque.

## 4. Forces parasites dans le plan (à chiffrer, cible ≪ actionneurs)

| Source | Ordre de grandeur |
|---|---|
| Pente θ | F = m·g·θ (50 µrad, 10 g → 4,9 µN) |
| Basculement du palet α (support asymétrique) | F ≈ W·α |
| Crantage (position relative au réseau de trous) | via modèle 2D de Reynolds à sources ponctuelles |
| Amortissement visqueux (Couette) | c = μ·A/h ; τ = m/c (≈ 15–80 s pour 2–10 g à h = 100 µm) |
| Courants d'air du local | écran anti-courant d'air recommandé |

## 5. Pièges

- Le terme laminaire seul surestime fortement le débit dès Re > 200 : garder le terme K.
- Évaluer les forces avec les trous **réels** (2D) et pas seulement le modèle réparti.
- Le débit total est dominé par les trous **non couverts** : c'est lui qui dimensionne le ventilateur.
