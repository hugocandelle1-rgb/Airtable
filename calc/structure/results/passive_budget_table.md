| Poste | Plancher | Conception actuelle | θ = 5 µrad | θ = 10 µrad | θ = 20 µrad | θ = 30 µrad | θ = 50 µrad |
|---|---|---|---|---|---|---|---|
| Planéité de la face supérieure (forme + ondulation) | 5.4 | 30.5 | — | — | 11.6 | 17.6 | 30.5 |
| Crantage (lot aéro ; < 33 µrad ⇒ correction a posteriori) | 7.5 | 33.0 | — | — | 9.8 | 14.9 | 33.0 |
| Dispersion des orifices (lot aéro) | 3.4 | 8.5 | — | — | 7.6 | 11.5 | 8.5 |
| Balourd des palets (0,9 µrad/µm) | 1.8 | 9.0 | — | — | 6.9 | 10.5 | 9.0 |
| Courants d'air résiduels (lot aéro) | 1.0 | 5.0 | — | — | 6.9 | 10.5 | 5.0 |
| Réglage global (pas moteur, bruit et offset des ADXL355) | 0.5 | 1.4 | — | — | 1.4 | 1.4 | 1.4 |
| Stabilité du nivellement entre deux recalages (thermique du bâti) | 0.4 | 1.8 | — | — | 1.8 | 1.8 | 1.8 |
| Sol / bâtiment (dérive entre deux recalages) | 0.2 | 1.0 | — | — | 1.0 | 1.0 | 1.0 |
| Poids propre sur appuis (finition sur appuis, frottement) | 0.3 | 1.6 | — | — | 1.6 | 1.6 | 1.6 |
| Pression (écart à la pression de finition) | 0.2 | 2.0 | — | — | 2.0 | 2.0 | 2.0 |
| Thermique de la plaque (écart air/plaque, rampe du local) | 0.3 | 1.4 | — | — | 1.4 | 1.4 | 1.4 |
| **Somme quadratique** (cible θ) | 10.1 | 47.0 | **NR** | **NR** | 20.0 | 30.0 | 47.0 |

| Exigence | θ = 5 µrad | θ = 10 µrad | θ = 20 µrad | θ = 30 µrad | θ = 50 µrad |
|---|---|---|---|---|---|
| Crantage | — | — | correction a posteriori requise (résidu ≤ 10 µrad RMS) | correction a posteriori requise (résidu ≤ 15 µrad RMS) | brut acceptable |
| Planéité zone percée (µm) | — | — | 1.1 | 1.6 | 2.8 |
| Planéité par 100 × 100 (µm) | — | — | 0.21 | 0.31 | 0.54 |
| Procédé de finition | — | — | tournage diamant optique + passes de correction sur carte mesurée | tournage/fly-cut diamant mono-pointe sur machine ultra-précise | fly-cut diamant de précision sur appuis de service |
| Procédé — prestataires plausibles | — | — | grands opticiens (Safran Reosc, Winlight, Fraunhofer IOF) ; capacité 520 mm percée non confirmée | ateliers d'optique métallique : instituts Fraunhofer (IOF, IPT), fabricants de miroirs aluminium (plausibles, non contactés) | ateliers de fly-cut et de surfaçage de précision (Europe) ; référence actuelle |
| Équilibrage des palets (µm) | — | — | ≤ 7.7 | ≤ 11.7 | ≤ 10.0 |
| Tolérance Ø orifices (± µm) | — | — | 4.5 | 6.8 | 5.0 |
| Vitesse d'air au niveau des palets (mm/s) | — | — | ≤ 20 | ≤ 25 | ≤ 17 |
| Écart air soufflé / plaque (K) | — | — | ≤ 0.71 | ≤ 0.71 | ≤ 0.71 |
| Rampe du local (K/h) | — | — | ≤ 2.25 | ≤ 2.25 | ≤ 2.25 |
| Variation du local entre recalages (K) | — | — | ≤ 0.50 | ≤ 0.50 | ≤ 0.50 |
| Intervalle de recalage d'inclinaison (h) | — | — | 1.00 | 1.00 | 1.00 |
| Retournement des ADXL355 (toutes les … h) | — | — | 24 | 24 | 24 |
| Moyennage ADXL355 (s) | — | — | 112 | 112 | 112 |
| Verdict | non réalisable | non réalisable | à la limite : finition optique de pointe, postes près du plancher ; suppose la correction a posteriori du crantage | réalisable : finition optique (classe 1,5–2,8 µm) ; suppose la correction a posteriori du crantage | réalisable avec la conception actuelle (somme quadratique 47 µrad) |
| Coût relatif (finition + palets + installation ; référence 1) | ∞ | ∞ | 9.3 | 3.3 | 1.3 |

| θ (µrad) | a_par (µm/s²) | ½aT², T = 1 s (µm) | ½aT², T = 5 s (µm) | ½aT², T = 10 s (µm) | ½aT², T = 30 s (µm) | amorti 2 g / 10 g, T = 30 s (µm) |
|---|---|---|---|---|---|---|
| 5 | 49 | 24.5 | 613.1 | 2452.5 | 22072.5 | 13596 / 18949 |
| 10 | 98 | 49.0 | 1226.2 | 4905.0 | 44145.0 | 27193 / 37898 |
| 20 | 196 | 98.1 | 2452.5 | 9810.0 | 88290.0 | 54386 / 75797 |
| 30 | 294 | 147.2 | 3678.8 | 14715.0 | 132435.0 | 81579 / 113695 |
| 50 | 490 | 245.2 | 6131.2 | 24525.0 | 220725.0 | 135964 / 189492 |

| θ (µrad) | m (g) | F_par (µN) | F_par/F_act, F_act = 0.1 µN | F_par/F_act, F_act = 1 µN | F_par/F_act, F_act = 10 µN | F_par/F_act, F_act = 100 µN | F_par/F_act, F_act = 1000 µN | F_act min. pour 1 % (µN) |
|---|---|---|---|---|---|---|---|---|
| 5 | 2 | 0.098 | 0.98 | 0.098 | 0.0098 | 0.00098 | 9.8e-05 | 9.8 |
| 5 | 5 | 0.245 | 2.5 | 0.25 | 0.025 | 0.0025 | 0.00025 | 24.5 |
| 5 | 10 | 0.490 | 4.9 | 0.49 | 0.049 | 0.0049 | 0.00049 | 49.0 |
| 10 | 2 | 0.196 | 2 | 0.2 | 0.02 | 0.002 | 0.0002 | 19.6 |
| 10 | 5 | 0.490 | 4.9 | 0.49 | 0.049 | 0.0049 | 0.00049 | 49.0 |
| 10 | 10 | 0.981 | 9.8 | 0.98 | 0.098 | 0.0098 | 0.00098 | 98.1 |
| 20 | 2 | 0.392 | 3.9 | 0.39 | 0.039 | 0.0039 | 0.00039 | 39.2 |
| 20 | 5 | 0.981 | 9.8 | 0.98 | 0.098 | 0.0098 | 0.00098 | 98.1 |
| 20 | 10 | 1.962 | 20 | 2 | 0.2 | 0.02 | 0.002 | 196.2 |
| 30 | 2 | 0.589 | 5.9 | 0.59 | 0.059 | 0.0059 | 0.00059 | 58.9 |
| 30 | 5 | 1.472 | 15 | 1.5 | 0.15 | 0.015 | 0.0015 | 147.2 |
| 30 | 10 | 2.943 | 29 | 2.9 | 0.29 | 0.029 | 0.0029 | 294.3 |
| 50 | 2 | 0.981 | 9.8 | 0.98 | 0.098 | 0.0098 | 0.00098 | 98.1 |
| 50 | 5 | 2.452 | 25 | 2.5 | 0.25 | 0.025 | 0.0025 | 245.2 |
| 50 | 10 | 4.905 | 49 | 4.9 | 0.49 | 0.049 | 0.0049 | 490.5 |
