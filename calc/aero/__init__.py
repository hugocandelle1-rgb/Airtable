"""Calculs aérauliques et paliers à air (table à coussin d'air)."""
import os as _os

# Les petites matrices denses sont résolues bien plus vite en mono-thread
# (évite la sur-souscription BLAS observée sur certaines machines).
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    _os.environ.setdefault(_v, "1")
