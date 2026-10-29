"""Journal CSV horodaté de la télémétrie."""
from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .protocol import CSV_FIELDS, flatten

HEADER = ["time_utc", "t_host_s"] + list(CSV_FIELDS)


def default_log_path(prefix: str = "airtable", directory: str | Path = ".") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path(directory) / f"{prefix}_{stamp}.csv"


def utc_iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(time.time() if ts is None else ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


class CsvLogger:
    """Écrit une ligne par trame : horodatage UTC hôte + temps hôte monotone + champs aplatis.

    Le temps hôte est celui de la réception ; `t_ms` est l'horloge du firmware (millis()), plus
    régulière : l'utiliser pour les analyses de dérive, `time_utc` pour recaler avec d'autres
    appareils (caméra, etc.).
    """

    def __init__(self, path: str | Path | None = None, flush_every: int = 10):
        self.path = Path(path) if path else default_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "w", newline="", encoding="utf-8")
        self._w = csv.writer(self._f)
        self._w.writerow(HEADER)
        self._t0 = time.monotonic()
        self._n = 0
        self._flush_every = max(1, flush_every)

    def write(self, frame: dict, now_utc: float | None = None) -> None:
        flat = flatten(frame)
        row = [utc_iso(now_utc), f"{time.monotonic() - self._t0:.3f}"]
        for k in CSV_FIELDS:
            v = flat[k]
            row.append("" if v is None else v)
        self._w.writerow(row)
        self._n += 1
        if self._n % self._flush_every == 0:
            self._f.flush()

    def write_all(self, frames: Iterable[dict]) -> int:
        n = 0
        for fr in frames:
            self.write(fr)
            n += 1
        return n

    @property
    def rows(self) -> int:
        return self._n

    def close(self) -> None:
        if not self._f.closed:
            self._f.flush()
            self._f.close()

    def __enter__(self) -> "CsvLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
