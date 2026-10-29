"""airtable_host : client série, journalisation et calibrations du banc table à coussin d'air.

Modules :
  protocol           grammaire des commandes (miroir du parseur C++), lecture des réponses JSON
  client             AirtableClient (pyserial ou simulateur)
  logger             journal CSV horodaté de la télémétrie
  tilt_calibration   calibration de l'inclinomètre par retournement 180 degrés
  drift_calibration  calibration par palets lâchés : pente locale, carte, correction d'inclinaison
  sim                simulateur du firmware (tests, essais à vide : --port sim://)
  cli                interface en ligne de commande (python3 -m host.airtable_host ...)
"""
__version__ = "0.1.0"
