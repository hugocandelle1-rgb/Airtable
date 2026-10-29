"""Outils communs aux calculs aérauliques (calc/aero).

- propriétés de l'air et géométrie du palet lues dans params/design.toml ;
- configuration de perçage (`HoleConfig`) : baseline lue dans design.toml,
  configuration recommandée lue dans results/recommended_hole.json si elle existe ;
- génération des positions de trous (maille hexagonale ou carrée) ;
- style graphique homogène (palette de référence validée, fond clair) ;
- écriture des résultats JSON.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict, replace
from pathlib import Path

import numpy as np

# Permet l'exécution directe d'un script (python3 calc/aero/xxx.py)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from calc.common.params import load_params, REPO_ROOT  # noqa: E402

AERO_DIR = REPO_ROOT / "calc" / "aero"
FIG_DIR = AERO_DIR / "figures"
RES_DIR = AERO_DIR / "results"
FIG_DIR.mkdir(parents=True, exist_ok=True)
RES_DIR.mkdir(parents=True, exist_ok=True)

P = load_params()
ENV = P["environment"]
RHO = float(ENV["air_rho"])        # kg/m³
MU = float(ENV["air_mu"])          # Pa·s
NU = MU / RHO                      # m²/s
G = float(ENV["g"])
P_ATM = 101325.0                   # Pa
CP_AIR = 1005.0                    # J/(kg·K)
K_AIR = 0.0257                     # W/(m·K)
PR_AIR = 0.71

R_PUCK = 0.5 * P["puck"]["diameter_mm"] * 1e-3   # m
A_PUCK = np.pi * R_PUCK**2
MASS_CASES_G = list(P["puck"]["mass_cases_g"])
PERF_SQUARE = P["zones"]["perforated_square_mm"] * 1e-3
WORK_SQUARE = P["zones"]["working_square_mm"] * 1e-3
PLATE_T = P["plate"]["thickness_mm"] * 1e-3


@dataclass(frozen=True)
class HoleConfig:
    """Géométrie d'un perçage et de la maille (unités SI).

    d      : diamètre de l'orifice calibré (m)
    L      : longueur de l'orifice = voile (m)
    pitch  : pas de la maille (m)
    pattern: "hex" ou "square"
    D_cb   : diamètre du perçage borgne d'alimentation (m)
    t      : épaisseur de plaque (m)
    K_c    : coefficient de perte « rideau » (sortie sous le palet)
    model  : loi d'orifice ("lichtarowicz", "shah_sharp", "shah_cone", "coord")
    cone_inlet : True si l'orifice débouche dans la pointe 118° du foret Ø D_cb
    """
    d: float = 0.40e-3
    L: float = 1.0e-3
    pitch: float = 5.0e-3
    pattern: str = "hex"
    D_cb: float = 2.0e-3
    t: float = 25e-3
    K_c: float = 0.5
    model: str = "lichtarowicz"
    cone_inlet: bool = False

    @property
    def A(self) -> float:
        return np.pi * self.d**2 / 4

    @property
    def r_h(self) -> float:
        return 0.5 * self.d

    @property
    def density(self) -> float:
        """Nombre de trous par m²."""
        if self.pattern == "hex":
            return 2.0 / (np.sqrt(3.0) * self.pitch**2)
        return 1.0 / self.pitch**2

    @property
    def L_bore(self) -> float:
        """Longueur du perçage borgne d'alimentation (m)."""
        return max(self.t - self.L, 0.0)

    def label(self) -> str:
        return (f"d={self.d*1e3:.2f} L={self.L*1e3:.2f} {self.pattern} "
                f"p={self.pitch*1e3:.1f}")

    def to_dict(self) -> dict:
        return asdict(self)

    def with_(self, **kw) -> "HoleConfig":
        return replace(self, **kw)


def baseline_config() -> HoleConfig:
    pl = P["plate"]
    return HoleConfig(d=pl["orifice_d_mm"] * 1e-3, L=pl["orifice_length_mm"] * 1e-3,
                      pitch=pl["pitch_mm"] * 1e-3, pattern=pl["pattern"],
                      D_cb=pl["counterbore_d_mm"] * 1e-3, t=PLATE_T)


def recommended_config() -> HoleConfig:
    """Configuration recommandée (écrite par optimize.py) ou baseline à défaut."""
    f = RES_DIR / "recommended_hole.json"
    if f.exists():
        d = json.loads(f.read_text())
        return HoleConfig(**d["config"])
    return baseline_config()


def h_target() -> float:
    """Entrefer cible (m) : celui retenu par optimize.py, sinon 120 µm."""
    f = RES_DIR / "recommended_hole.json"
    if f.exists():
        return json.loads(f.read_text())["h_target_um"] * 1e-6
    return 120e-6


# ---------------------------------------------------------------------------
# Réseau de trous
# ---------------------------------------------------------------------------
def lattice_vectors(cfg: HoleConfig) -> tuple[np.ndarray, np.ndarray]:
    p = cfg.pitch
    if cfg.pattern == "hex":
        return np.array([p, 0.0]), np.array([0.5 * p, 0.5 * np.sqrt(3) * p])
    return np.array([p, 0.0]), np.array([0.0, p])


def holes_near(cfg: HoleConfig, center: np.ndarray, radius: float) -> np.ndarray:
    """Positions (relatives à `center`) des trous du réseau infini à < radius."""
    a1, a2 = lattice_vectors(cfg)
    nmax = int(np.ceil(radius / (0.5 * cfg.pitch))) + 3
    i, j = np.meshgrid(np.arange(-nmax, nmax + 1), np.arange(-nmax, nmax + 1))
    pts = i.reshape(-1, 1) * a1 + j.reshape(-1, 1) * a2
    rel = pts - np.asarray(center)
    r = np.hypot(rel[:, 0], rel[:, 1])
    return rel[r < radius]


def unit_cell_positions(cfg: HoleConfig, n: int) -> np.ndarray:
    """n×n positions du centre du palet couvrant la cellule primitive."""
    a1, a2 = lattice_vectors(cfg)
    u = (np.arange(n) + 0.5) / n
    U, V = np.meshgrid(u, u)
    return U.reshape(-1, 1) * a1 + V.reshape(-1, 1) * a2


def count_holes_square_zone(cfg: HoleConfig, side: float = PERF_SQUARE) -> int:
    """Nombre de trous dans la zone percée carrée (centrée sur un trou)."""
    a1, a2 = lattice_vectors(cfg)
    nmax = int(side / cfg.pitch) + 4
    i, j = np.meshgrid(np.arange(-2 * nmax, 2 * nmax + 1), np.arange(-nmax, nmax + 1))
    pts = i.reshape(-1, 1) * a1 + j.reshape(-1, 1) * a2
    s = 0.5 * side + 1e-9
    m = (np.abs(pts[:, 0]) <= s) & (np.abs(pts[:, 1]) <= s)
    return int(m.sum())


# ---------------------------------------------------------------------------
# Sorties
# ---------------------------------------------------------------------------
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    if isinstance(o, HoleConfig):
        return o.to_dict()
    return o


def save_json(name: str, data: dict) -> Path:
    f = RES_DIR / name
    f.write_text(json.dumps(_jsonable(data), indent=2, ensure_ascii=False))
    return f


def load_json(name: str) -> dict:
    return json.loads((RES_DIR / name).read_text())


# ---------------------------------------------------------------------------
# Style graphique (palette de référence validée, mode clair)
# ---------------------------------------------------------------------------
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300",
          "#6250d6", "#e34948"]
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SURFACE = "#fcfcfb"
CRITICAL = "#d03b3b"
GOOD = "#0ca30c"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95",
            "#0d366b"]


def setup_style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import cycler
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE, "axes.edgecolor": AXIS,
        "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
        "text.color": INK, "axes.titlecolor": INK, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "axes.spines.top": False,
        "axes.spines.right": False, "lines.linewidth": 2.0, "font.size": 9.5,
        "axes.titlesize": 10.5, "legend.frameon": False,
        "axes.prop_cycle": cycler(color=SERIES), "figure.dpi": 110,
        "savefig.dpi": 130, "savefig.bbox": "tight",
    })
    return plt


def diverging_cmap():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list(
        "bluered", ["#184f95", "#6da7ec", "#f0efec", "#ec8b8a", "#b52f2f"])


def seq_cmap():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list("blue", SEQ_BLUE)


def savefig(fig, name: str) -> Path:
    f = FIG_DIR / name
    fig.savefig(f)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return f
