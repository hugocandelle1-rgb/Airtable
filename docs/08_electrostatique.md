# 08 — Compatibilité électrostatique palet / plaque — **REPORTÉ**

> Statut (2026-11-04) : **reporté** par l'utilisateur (matériaux alternatifs de plaque étudiés plus tard).
> **Hypothèse retenue d'ici là : aucune interaction électrostatique palet/plaque.** Aucun calcul ni script.

## Premières estimations (ordres de grandeur seulement, [P], non vérifiés, non sourcés en ligne)
Une force dans le plan F se lit comme une pente équivalente F/(m g) : 1 µrad ↔ 20 nN (2 g), 98 nN (10 g) (`docs/02_aeraulique.md` § 1).
1. **Plaque uniforme infinie** : la force d'image horizontale est nulle par invariance de translation. Il ne reste que la
   force verticale. Si elle est excentrée (électrode au bord, r = R), elle fait basculer le palet et donne une force latérale
   ≈ F_z·R/(2 k_θ/W) ≈ 1,3–1,4 % de F_z (k_θ/W = 0,52–0,58 m, § 3 de la note 02).
2. **Palet chargé** (Q sur sa face inférieure, C ≈ ε0A/h ≈ 63 pF à 100 µm) : force verticale Q²/(2ε0A) ≈ 80 µN pour 1 nC
   (0,4 % du poids d'un palet de 2 g), et Δh ≈ 0,4 µm (k_z = 206 N/m). Cette charge peut venir de la séparation au décollage
   (différence de potentiel de contact).
3. **Écran PMMA chargé** (σ ≈ 1 µC/m², à 0,1 m) : son gradient de champ peut tirer sur un palet neutre avec 0,1–1 µN,
   soit plusieurs µrad. La force croît en σ². C'est un argument pour un écran conducteur ou dissipatif mis à la terre.
4. **Orifices** : électrostatiquement, chaque orifice se comporte comme un dipôle (≈ ε0a³E²). Cela crée un crantage
   électrostatique sensible si une électrode à haute tension descend à moins de 0,3 mm de la plaque.
   Claquage de l'air (Paschen) ≈ 0,9 kV sous 0,1 mm.
5. **Anodisation** : c'est un isolant qui piège des charges, et sa croissance réduit les Ø0,30. Elle est déjà exclue
   (`docs/04_usinage_tolerances.md`, op. 110). Les pistes de remplacement sont l'aluminium nu, une conversion chimique
   conductrice, ou un nickel chimique haut phosphore (surfaçable au diamant ; il faut compenser son épaisseur sur les Ø).

## Questions à traiter plus tard
- Forces d'image verticale et horizontale en fonction de V, de l'entrefer et de la garde basse ; effets de bord (zone percée,
  bord de plaque, écran) ; raideur négative et stabilité du film ; dépendance F_act(h).
- Charge des palets : triboélectricité, contact, fuite par les ions de l'air ; neutralisation avant essai (ioniseur à arrêter
  pendant la mesure) ; humidité visée 40–50 % HR.
- Potentiel de la plaque : tresse de masse souple (pour ne pas perturber les appuis Kelvin), référence commune avec
  l'électronique des palets, potentiels de contact (patch potentials) ; choix du traitement de surface.
- Écran : verre ou PC dissipatif, ou couche conductrice mise à la terre ; distance au palet.
- Mesures : cage de Faraday + électromètre (charge Q des palets), voltmètre électrostatique sans contact, sonde de Kelvin,
  BME280 (HR) à journaliser.
- Données à obtenir de l'utilisateur : F_act, tension, géométrie des électrodes, durée d'une mesure.

Sources : notes internes 02 (§ 1, 3, 8), 04 (op. 110), `docs/reprise/00_coordination.md`. Physique de manuel (images,
ouverture de Bethe, loi de Paschen) **non vérifiée par recherche documentaire** : à sourcer à la reprise.
